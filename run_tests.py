import asyncio
import os
import json
import re
import pandas as pd
from playwright.async_api import async_playwright
from langchain_openai import ChatOpenAI

BASE_URL = "https://trajector.bling-ai.com/trajector/login/"

llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0
)


# 🔧 JSON extractor
def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except:
        return {}


# ✅ STEP 1 — Extract UI
async def extract_ui(page):
    return await page.evaluate("""
    () => {
        return Array.from(document.querySelectorAll('input, button, a')).map(el => ({
            tag: el.tagName,
            text: el.innerText,
            placeholder: el.placeholder,
            id: el.id,
            name: el.name,
            type: el.type
        }))
    }
    """)


# ✅ STEP 2 — AI decides actions
def get_actions(description, ui):
    prompt = f"""
You are an AI QA tester.

Test case:
{description}

UI elements:
{ui}

Decide steps to execute.

IMPORTANT:
- Use visible text like "Sign in", "Email"
- Do NOT use ids like signInBtn

Return ONLY JSON:

{{
  "steps": [
    {{"action": "fill", "target": "email", "value": ""}},
    {{"action": "fill", "target": "password", "value": ""}},
    {{"action": "click", "target": "Sign in"}}
  ]
}}
"""
    res = llm.invoke(prompt)
    return extract_json(res.content)


# ✅ STEP 3 — Smart locator translator
async def smart_find_and_act(page, action, target, value=""):
    target_lower = target.lower()

    try:
        if action == "fill":
            locator = (
                page.get_by_placeholder(target)
                or page.get_by_label(target)
                or page.locator(f'input[name*="{target_lower}"]')
                or page.locator(f'input[id*="{target_lower}"]')
            )
            await locator.first.fill(value)
            await locator.first.press("Tab")

        elif action == "click":
            locator = (
                page.get_by_role("button", name=target)
                or page.get_by_text(target)
                or page.locator(f'button[id*="{target_lower}"]')
                or page.locator("button")
            )
            await locator.first.click()

    except Exception as e:
        print(f"⚠️ Smart action failed: {action} {target} → {e}")


# ✅ STEP 4 — Execute steps
async def execute_steps(page, steps):
    for step in steps:
        action = step.get("action")
        target = step.get("target")
        value = step.get("value", "")

        print(f"⚙️ {action} → {target}")

        await smart_find_and_act(page, action, target, value)


# ✅ STEP 5 — Validation (deterministic)
def validate(expectation, text):
    if expectation.lower().strip() in text.lower():
        return "PASS"
    return "FAIL"


# ✅ MAIN
async def run_suite():
    df = pd.read_excel(
        "Trajector Test cases.xlsx",
        sheet_name="Login",
        engine="openpyxl"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for _, row in df.iterrows():
            test_id = row["Test case ID"]
            description = row["Description"]
            expectation = row["Expectation"]

            print(f"\n🚀 {test_id}")

            try:
                await page.goto(BASE_URL)
                await page.wait_for_timeout(3000)

                ui = await extract_ui(page)

                # 🔁 Retry AI
                actions = {}
                for i in range(3):
                    actions = get_actions(description, ui)
                    if actions.get("steps"):
                        break

                steps = actions.get("steps", [])

                if not steps:
                    print("⚠️ AI failed to generate steps")
                    continue

                await execute_steps(page, steps)

                await page.wait_for_timeout(2000)

                text = await page.inner_text("body")

                print("📄 TEXT:", text[:300])

                result = validate(expectation, text)

                print("👉 RESULT:", result)

            except Exception as e:
                print(f"❌ ERROR: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_suite())
