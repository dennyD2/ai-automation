import asyncio
import os
import json
import pandas as pd
from playwright.async_api import async_playwright
from langchain_openai import ChatOpenAI


# 🔴 CHANGE THIS
BASE_URL = "https://trajector.bling-ai.com/trajector/login/"


# ✅ LLM setup (DeepSeek)
llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0
)


# ✅ Step 1: AI extracts selectors from DOM
async def get_selectors_from_llm(description, html):
    prompt = f"""
You are a QA automation expert.

Here is the webpage HTML (trimmed):
{html[:4000]}

Test case:
{description}

Find the correct selectors for:
- Email input field
- Password input field
- Login button

Return ONLY JSON:

{{
  "email": "selector",
  "password": "selector",
  "button": "selector"
}}
"""

    response = llm.invoke(prompt)

    try:
        return json.loads(response.content)
    except:
        print("⚠️ Failed to parse selectors from AI")
        return {}


# ✅ Step 2: AI converts description → steps (optional debug)
async def get_steps_from_llm(description):
    prompt = f"""
Convert this test case into browser steps:

{description}
"""
    response = llm.invoke(prompt)
    return response.content


# ✅ Step 3: Validate result using AI
async def validate_result(description, expectation, html):
    prompt = f"""
You are a QA tester.

Test case:
{description}

Expected:
{expectation}

Actual page content:
{html[:2000]}

Did it PASS or FAIL? Give reason.
"""
    response = llm.invoke(prompt)
    return response.content


# ✅ Step 4: Execute test
async def run_test(page, description):
    html = await page.content()

    selectors = await get_selectors_from_llm(description, html)
    print("🤖 AI selectors:", selectors)

    email_selector = selectors.get("email", 'input[type="email"]')
    password_selector = selectors.get("password", 'input[type="password"]')
    button_selector = selectors.get("button", 'button')

    # Fill inputs safely
    try:
        await page.fill(email_selector, "test@example.com")
        print(f"✅ Filled email using {email_selector}")
    except:
        print("⚠️ Email field not found")

    try:
        await page.fill(password_selector, "123456")
        print(f"✅ Filled password using {password_selector}")
    except:
        print("⚠️ Password field not found")

    # Click button safely
    try:
        await page.click(button_selector)
        print(f"✅ Clicked button using {button_selector}")
    except:
        print("⚠️ Login button not found")

    await page.wait_for_timeout(2000)

    return await page.content()


# ✅ Main runner
async def run_suite():
    try:
        df = pd.read_excel(
            "Trajector Test cases.xlsx",
            sheet_name="Login",
            engine="openpyxl"
        )
    except Exception as e:
        print(f"❌ Excel read error: {e}")
        return

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for _, row in df.iterrows():
            test_id = row["Test case ID"]
            description = row["Description"]
            expectation = row["Expectation"]

            print(f"\n🚀 Running {test_id}")

            try:
                await page.goto(BASE_URL)
                await page.wait_for_load_state("networkidle")

                steps = await get_steps_from_llm(description)
                print("🧠 Steps:\n", steps)

                content = await run_test(page, description)

                result = await validate_result(description, expectation, content)

                results.append((test_id, result))

                print(f"✅ {test_id}: {result}")

            except Exception as e:
                print(f"❌ {test_id} failed: {e}")
                results.append((test_id, f"ERROR: {e}"))

        await browser.close()

    # 📊 Final report
    print("\n📊 FINAL REPORT\n")

    for test_id, result in results:
        print(f"{test_id} → {result}")


if __name__ == "__main__":
    asyncio.run(run_suite())
