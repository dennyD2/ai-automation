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


# ✅ STEP 1 — Minimal UI extraction
async def extract_ui_elements(page):
    return await page.evaluate("""
    () => {
        return {
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
        }
    }
    """)


# ✅ STEP 2 — SIMPLE AI (no overthinking)
def analyze_ui(ui):
    prompt = f"""
Find selectors.

UI:
{ui}

Return JSON only:

{{
 "email": "...",
 "password": "...",
 "button": "..."
}}
"""
    res = llm.invoke(prompt)
    return extract_json(res.content)


# ✅ STEP 3 — ACTION (mostly deterministic)
async def perform_login(page, selectors, description):
    email = selectors.get("email")
    password = selectors.get("password")
    button = selectors.get("button")

    email_val = ""
    password_val = ""

    if "valid" in description.lower():
        email_val = "test@example.com"
        password_val = "123456"

    try:
        if email:
            await page.fill(email, email_val)
    except:
        print("⚠️ email fail")

    try:
        if password:
            await page.fill(password, password_val)
    except:
        print("⚠️ password fail")

    try:
        if button:
            await page.click(button)
    except:
        print("⚠️ click fail")

    await page.wait_for_timeout(2000)


# ✅ STEP 4 — SIMPLE VALIDATION (controlled)
def validate_result(expectation, text):
    prompt = f"""
Expected:
{expectation}

Actual:
{text}

Rules:
- If expected message is present → PASS
- Else → FAIL

Return:

PASS or FAIL
"""
    res = llm.invoke(prompt)
    return res.content


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

        print("🤖 selectors:", selectors)

        for _, row in df.iterrows():
            print(f"\n🚀 {row['Test case ID']}")

            await page.goto(BASE_URL)
            await page.wait_for_timeout(2000)

            await perform_login(page, selectors, row["Description"])

            text = await page.inner_text("body")

            result = validate_result(row["Expectation"], text)

            print("👉", result)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_suite())
