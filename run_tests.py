import asyncio
import os
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

# 🧠 AI decides NEXT step
def get_next_step(description, page_text, history):
    prompt = f"""
You are controlling a browser.

Test case:
{description}

Current page:
{page_text[:500]}

Steps already done:
{history}

Decide NEXT step.

Return JSON:
{{
  "action": "fill/click/done",
  "target": "visible text or placeholder",
  "value": "optional"
}}
"""
    res = llm.invoke(prompt).content

    import re, json
    match = re.search(r"\{.*\}", res, re.DOTALL)
    if match:
        return json.loads(match.group())

    return {"action": "done"}


# 🔧 Smart executor
async def execute_step(page, step):
    action = step.get("action")
    target = step.get("target", "")
    value = step.get("value", "")

    print(f"⚙️ {action} → {target}")

    try:
        if action == "fill":
            locator = (
                page.get_by_placeholder(target)
                or page.get_by_label(target)
                or page.locator(f'input[placeholder*="{target}"]')
                or page.locator("input")
            )
            await locator.first.fill(value)
            await locator.first.press("Tab")

        elif action == "click":
            locator = (
                page.get_by_role("button", name=target)
                or page.get_by_text(target)
                or page.locator("button")
            )
            await locator.first.click()

    except Exception as e:
        print("⚠️ Step failed:", e)


# ✅ Validation (deterministic)
def validate(expectation, text):
    return "PASS" if expectation.lower() in text.lower() else "FAIL"


# 🚀 MAIN LOOP
async def run_suite():
    df = pd.read_excel("Trajector Test cases.xlsx", sheet_name="Login")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for _, row in df.iterrows():
            print(f"\n🚀 {row['Test case ID']}")

            await page.goto(BASE_URL)
            await page.wait_for_timeout(2000)

            history = []

            for step_no in range(5):  # limit steps
                page_text = await page.inner_text("body")

                step = get_next_step(
                    row["Description"],
                    page_text,
                    history
                )

                if step.get("action") == "done":
                    break

                await execute_step(page, step)
                history.append(step)

                await page.wait_for_timeout(1000)

            # 🔍 Final state
            text = await page.inner_text("body")

            print("📄 TEXT:", text[:300])

            result = validate(row["Expectation"], text)

            print("👉 RESULT:", result)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_suite())
