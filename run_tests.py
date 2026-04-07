import asyncio
import os
import pandas as pd
from playwright.async_api import async_playwright
from langchain_openai import ChatOpenAI


BASE_URL = "https://trajector.bling-ai.com/trajector/login/"  # 🔴 CHANGE THIS


# ✅ LLM setup (DeepSeek works fine here)
llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0
)


async def get_steps_from_llm(description):
    prompt = f"""
Convert this test case into clear browser steps.

Test case:
{description}

Return steps like:
1. Open login page
2. Enter email ...
3. Click login
"""

    response = llm.invoke(prompt)
    return response.content


async def validate_result(description, expectation, page_content):
    prompt = f"""
You are a QA tester.

Test case:
{description}

Expected result:
{expectation}

Actual page content:
{page_content[:2000]}

Did the test PASS or FAIL?

Return:
PASS or FAIL with reason.
"""

    response = llm.invoke(prompt)
    return response.content


async def run_test(page, description):
    steps = await get_steps_from_llm(description)

    print("\n🧠 Steps generated:\n", steps)

    # 🔥 VERY SIMPLE execution logic (can improve later)
    if "empty" in description.lower():
        await page.fill('input[type="email"]', "")
        await page.fill('input[type="password"]', "")
    elif "valid" in description.lower():
        await page.fill('input[type="email"]', "test@example.com")
        await page.fill('input[type="password"]', "123456")

    await page.click('button[type="submit"]')

    await page.wait_for_timeout(2000)

    content = await page.content()
    return content


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

        for _, row in df.iterrows():
            test_id = row["Test case ID"]
            description = row["Description"]
            expectation = row["Expectation"]

            print(f"\n🚀 Running {test_id}")

            try:
                await page.goto(BASE_URL)

                content = await run_test(page, description)

                result = await validate_result(
                    description,
                    expectation,
                    content
                )

                results.append({
                    "id": test_id,
                    "result": result
                })

                print(f"✅ {test_id}: {result}")

            except Exception as e:
                print(f"❌ {test_id} failed: {e}")
                results.append({
                    "id": test_id,
                    "result": f"ERROR: {e}"
                })

        await browser.close()

    # 📊 Final report
    print("\n📊 FINAL REPORT:\n")

    for r in results:
        print(f"{r['id']} → {r['result']}")


if __name__ == "__main__":
    asyncio.run(run_suite())
