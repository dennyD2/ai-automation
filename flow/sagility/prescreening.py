import re
from playwright.async_api import Page
from pages.sagility.prescreening_page import PrescreeningPage

async def run_prescreening(page: Page):
    try:
        print("\n===== PRE-SCREENING STAGE =====")

        prescreening = PrescreeningPage(page)

        await page.get_by_text(
            re.compile(
                "before we move forward",
                re.I
            )
        ).wait_for(timeout=15000)

        print("✅ Pre-screening content detected")

        # Knockout Questions
        await prescreening.answer_student_question()
        await prescreening.answer_termination_question()
        await prescreening.answer_criminal_question()
        await prescreening.submit_knockout_questions()

        # Dropdown Questions
        await prescreening.select_job_fit()
        await prescreening.continue_job_fit()
        await prescreening.select_job_priority()
        await prescreening.continue_job_priority()

        print("🔹 Waiting for transition to next stage")

        await page.get_by_text(
            re.compile(
                "taking you to next stage",
                re.I
            )
        ).wait_for(timeout=10000)

        print("✅ Transition detected")

        print("🔹 Waiting for assessment page")

        await page.wait_for_function(
            """
            () => {
                const text = document.body.innerText.toLowerCase();
                return (
                    text.includes('start assessment') ||
                    text.includes('skip assessment') ||
                    text.includes('internet speed') ||
                    text.includes('microphone')
                );
            }
            """,
            timeout=30000
        )

        print("✅ Assessment stage detected")

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise
