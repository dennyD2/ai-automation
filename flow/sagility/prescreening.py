import re
from playwright.async_api import Page

async def run_prescreening(page: Page):
    try:
        print("\n===== PRE-SCREENING STAGE =====")

        await page.get_by_text(
            re.compile(
                "before we move forward",
                re.I
            )
        ).wait_for(timeout=15000)

        print("✅ Pre-screening content detected")

        body = await page.evaluate(
            "() => document.body.innerText"
        )

        print("\n===== PRE-SCREENING PAGE TEXT =====")
        print(body[:5000])
        print("===================================\n")

        # Question 1
        print("🔹 Answering full-time student question")

        student_section = page.locator(
            "text=Are you currently a full-time student?"
        )

        await student_section.locator(
            ".."
        ).get_by_text("No").click()

        print("✅ Student question answered")
        print("✅ Selected No")

        # Knockout Question:
        # Have you ever been terminated from a position?
        # MUST answer No

        terminated_section = page.locator(
            "text=Have you ever been terminated from a position?"
        )
        
        await terminated_section.locator(
            ".."
        ).get_by_text("No").click()
        
        print("✅ Terminated question answered")

        await page.get_by_role(
            "button",
            name="Submit"
        ).click()

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise

        # Knockout Question:
        # Have you ever been convicted of a criminal offense?
        # MUST answer No

        await page.get_by_text("No").nth(2).click()

        await page.get_by_role(
            "button",
            name="Submit"
        ).click()

        await page.locator("select").nth(0).select_option(
            label="Stability"
        )

        await page.get_by_role(
            "button",
            name="Continue"
        ).click()

        await page.locator("select").nth(1).select_option(
            label="Work-life balance"
        )

        await page.get_by_role(
            "button",
            name="Continue"
        ).click()

        await page.wait_for_timeout(3000)

        print("✅ Pre-screening completed")

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise
        
