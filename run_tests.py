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


# 🔧 Extract JSON safely
def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except:
        return {}


# ✅ STEP 1 — Extract UI elements (generic)
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


# ✅ STEP 2 — AI decides actions (GENERIC)
def get_actions(description, ui):
    prompt = f"""
You are an AI QA tester.

Test case:
{description}

UI elements:
{ui}

Decide steps to execute.

Return ONLY JSON:

{{
  "steps": [
    {{"action": "fill", "target": "email", "value": "test@gmail.com"}},
    {{"action": "fill", "target": "password", "value": "123456"}},
    {{"action": "click", "target": "Sign in"}}
  ]
}}
"""
    res = llm.invoke(prompt)
    return extract_json(res.content)


# ✅ STEP 3 — Execute dynamically
async def execute_steps(page, steps):
    for step in steps:
        action = step.get("action")
        target = step.get("target")
        value = step.get("value", "")

        print(f"⚙️ {action} → {target}")

        try:
            if action == "fill":
                locator = (
                    page.get_by_placeholder(target)
                    or page.get_by_label(target)
                    or page.locator(f'input[name="{target}"]')
                )
                await locator.first.fill(value)
                await locator.first.press("Tab")

            elif action == "click":
                locator = page.get_by_text(target)
                await locator.first.click()

        except Exception as e:
            print(f"⚠️ Step failed: {e}")


# ✅ STEP 4 — Simple validation (no AI needed)
def validate(expectation, text):
    if expectation.lower() in text.lower():
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

                # wait for validation
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
