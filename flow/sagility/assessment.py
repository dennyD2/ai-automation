import re
from playwright.async_api import Page

async def run_assessment(page: Page):
    try:
        print("\n===== ASSESSMENT STAGE =====")

        print("🔹 Waiting for assessment page")

        await page.get_by_text(
            re.compile(
                "complete the assessment questionnaire",
                re.I
            )
        ).wait_for(timeout=15000)

        print("✅ Assessment page detected")

        print("🔹 Clicking Skip Assessment")

        await page.get_by_role(
            "button",
            name=re.compile(
                "skip assessment",
                re.I
            )
        ).click()

        print("✅ Skip Assessment clicked")

        print("🔹 Waiting for internet speed check")

        await page.get_by_text(
            re.compile(
                "checking your internet speed",
                re.I
            )
        ).wait_for(timeout=20000)

        print("✅ Internet speed check page loaded")

        body = await page.evaluate(
            "() => document.body.innerText"
        )

        print("\n===== INTERVIEW PAGE TEXT =====")

    except Exception as e:
        print(f"❌ ASSESSMENT ERROR: {e}")
        raise
