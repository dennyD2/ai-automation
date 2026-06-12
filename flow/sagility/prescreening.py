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

        # Knockout Question:
        # Have you ever been convicted of a criminal offense?
        # MUST answer No

        criminal_section = page.locator(
            "text=Have you ever been convicted of a criminal offense?"
        )

        await criminal_section.locator(
            ".."
        ).get_by_text("No").click()

        print("✅ Criminal offense question answered")

        await page.get_by_role(
            "button",
            name="Submit"
        ).nth(1).click()

        print("✅ Submitted criminal offense section")

        # Job fit dropdown

        await page.locator("select").nth(0).select_option(
            label="Stability"
        )

        print("✅ Selected Stability")

        await page.get_by_role(
            "button",
            name="Continue"
        ).nth(0).click()

        print("✅ Continued first dropdown")

        # Job priorities dropdown

        await page.locator("select").nth(1).select_option(
            label="Work-life balance"
        )

        print("✅ Selected Work-life balance")

        await page.get_by_role(
            "button",
            name="Continue"
        ).nth(1).click()

        print("✅ Continued second dropdown")
        print("🔹 Waiting for transition to next stage")

        await page.wait_for_function(
            """
            () => {
                const text = document.body.innerText.toLowerCase();
                return (
                    text.includes('start assessment') ||
                    text.includes('skip assessment') ||
                    text.includes('internet speed') ||
                    text.includes('microphone') ||
                    text.includes('camera access')
                );
            }
            """,
            timeout=30000
        )

        print("✅ Transition detected")

        print("🔹 Waiting for assessment page")

        await page.wait_for_function(
            """
            () => {
                const text = document.body.innerText.toLowerCase();
                return (
                    text.includes('start assessment') ||
                    text.includes('skip assessment')
                );
            }
            """,
            timeout=20000
        )
        
        print("✅ Assessment buttons detected")
        print("✅ Assessment stage reached")

        print("🔹 Waiting for assessment page")
        
        await page.get_by_text(
            re.compile(
                "complete the assessment questionnaire",
                re.I
            )
        ).wait_for(timeout=15000)
        
        print("✅ Assessment stage reached")

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise
