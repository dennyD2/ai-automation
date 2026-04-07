import asyncio
import os
import json
import re
import pandas as pd
from playwright.async_api import async_playwright
from langchain_google_genai import ChatGoogleGenerativeAI

# 🔴 Base URL
BASE_URL = "https://trajector.bling-ai.com/trajector/login/"

# ✅ Gemini LLM setup
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0
)


# 🔧 Robust JSON extraction
def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except:
        return {}


# ✅ STEP 1 — Extract UI elements
async def extract_ui_elements(page):
    return await page.evaluate("""
    () => Array.from(document.querySelectorAll('input, button, a')).map(el => ({
        tag: el.tagName,
        text: el.innerText,
        placeholder: el.placeholder,
        id: el.id,
        name: el.name,
        type: el.type
    }))
    """)


# ✅ STEP 2 — AI understands UI
def analyze_ui(elements):
    prompt = f"""
You are analyzing a login page UI.

Elements:
{elements}

Identify:
- email input field
- password input field
- login button

Return ONLY JSON:

{{
  "email": "selector",
  "password": "selector",
  "button": "selector"
}}
"""
    response = llm.invoke(prompt)
    return extract_json(response.content)


# ✅ STEP 3 — Perform action (AI-inferred)
async def perform_login(page, selectors, description):
    email_selector = selectors.get("email")
    password_selector = selectors.get("password")
    button_selector = selectors.get("button")

    print("🤖 Using selectors:", selectors)

    email_value = ""
    password_value = ""

    if "valid" in description.lower():
        email_value = "test@example.com"
        password_value = "123456"

    try:
        if email_selector:
            await page.fill(email_selector, email_value)
    except:
        print("⚠️ Email fill failed")

    try:
        if password_selector:
            await page.fill(password_selector, password_value)
    except:
        print("⚠️ Password fill failed")

    try:
        if button_selector:
            await page.click(button_selector)
    except:
        print("⚠️ Button click failed")

    await page.wait_for_timeout(2000)


# ✅ STEP 4 — CONTROLLED SMART VALIDATION
def validate_result(description, expectation, text):
    prompt = f"""
You are a QA tester.

Test case:
{description}

Expected result:
{expectation}

Actual UI text:
{text}

Instructions:

1. Use description to infer user action (e.g., login → assume click happened)
2. ONLY validate based on expected result
3. Do NOT evaluate UX improvements
4. Do NOT overthink

Rules:
- If expected message is present → PASS
- If not present → FAIL
- Allow small wording variation if meaning matches

Return:

Result: PASS or FAIL
Reason: Short explanation strictly based on expectation
"""
    response = llm.invoke(prompt)
    return response.content


# ✅ MAIN
async def run_suite():
    df = pd.read_excel(
        "Trajector Test cases.xlsx",
        sheet_name="Login",
        engine="openpyxl"
    )

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 🔥 Initial load
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        print("🌐 Page title:", await page.title())

        # 🔥 UI-first analysis
        elements = await extract_ui_elements(page)
        selectors = analyze_ui(elements)

        print("🧠 AI UI understanding:", selectors)

        for _, row in df.iterrows():
            test_id = row["Test case ID"]
            description = row["Description"]
            expectation = row["Expectation"]

            print(f"\n🚀 Running {test_id}")

            try:
                await page.goto(BASE_URL)
                await page.wait_for_timeout(2000)

                await perform_login(page, selectors, description)

                visible_text = await page.inner_text("body")

                result = validate_result(
                    description,
                    expectation,
                    visible_text
                )

                print(f"✅ {test_id}: {result}")
                results.append((test_id, result))

            except Exception as e:
                print(f"❌ {test_id} failed: {e}")
                results.append((test_id, f"ERROR: {e}"))

        await browser.close()

    print("\n📊 FINAL REPORT\n")
    for r in results:
        print(f"{r[0]} → {r[1]}")


if __name__ == "__main__":
    asyncio.run(run_suite())
