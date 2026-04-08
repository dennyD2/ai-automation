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


# ✅ STEP 1 — UI extraction
async def extract_ui_elements(page):
    return await page.evaluate("""
    () => ({
        inputs: Array.from(document.querySelectorAll('input')).map(e => ({
            placeholder: e.placeholder,
            id: e.id,
            name: e.name,
            type: e.type
        })),
        buttons: Array.from(document.querySelectorAll('button')).map(e => ({
            text: e.innerText,
            id: e.id
        }))
    })
    """)


# ✅ STEP 2 — AI selector detection with retry
def analyze_ui(ui):
    for attempt in range(3):
        prompt = f"""
Find selectors.

UI:
{ui}

Return JSON:
{{"email":"...","password":"...","button":"..."}}
"""
        res = llm.invoke(prompt)
        data = extract_json(res.content)

        if data.get("email") and data.get("button"):
            return data

    return {}  # fallback


# ✅ STEP 3 — fallback selectors
def fallback_selectors():
    return {
        "email": 'input[type="email"], input[name="email"]',
        "password": 'input[type="password"], input[name="password"]',
        "button": 'button:has-text("Sign in"), button'
    }


# ✅ STEP 4 — perform action with retry + blur fix
async def perform_login(page, selectors, description):
    email = selectors.get("email")
    password = selectors.get("password")
    button = selectors.get("button")

    print("🤖 Using selectors:", selectors)

    # 🔥 FIXED logic
    if "invalid" in description.lower():
        email_val = "testgmail.com"
        password_val = "123456"
    elif "valid" in description.lower():
        email_val = "test@example.com"
        password_val = "123456"
    else:
        email_val = ""
        password_val = ""

    try:
        if email:
            await page.fill(email, email_val)
            await page.press(email, "Tab")  # trigger validation
    except:
        print("⚠️ email fail")

    try:
        if password:
            await page.fill(password, password_val)
            await page.press(password, "Tab")
    except:
        print("⚠️ password fail")

    # 🔁 click retry
    for i in range(2):
        try:
            if button:
                await page.click(button)
                return
        except:
            print(f"⚠️ click retry {i+1}")

    print("❌ click failed completely")


# ✅ STEP 5 — validation
def validate_result(expectation, text):
    prompt = f"""
Expected:
{expectation}

Actual:
{text}

Rule:
If expected message is present → PASS else FAIL

Return only PASS or FAIL
"""
    res = llm.invoke(prompt)
    return res.content.strip()


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

        await page.goto(BASE_URL)
        await page.wait_for_timeout(3000)

        ui = await extract_ui_elements(page)
        selectors = analyze_ui(ui)

        if not selectors:
            print("⚠️ Using fallback selectors")
            selectors = fallback_selectors()

        print("🧠 Final selectors:", selectors)

        for _, row in df.iterrows():
            print(f"\n🚀 {row['Test case ID']}")

            await page.goto(BASE_URL)
            await page.wait_for_timeout(2000)

            await perform_login(page, selectors, row["Description"])

            try:
                await page.wait_for_selector("text=Please enter", timeout=3000)
            except:
                pass

            text = await page.inner_text("body")

            print("📄 PAGE TEXT:", text[:500])  # debug

            result = validate_result(row["Expectation"], text)

            print("👉 RESULT:", result)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_suite())
