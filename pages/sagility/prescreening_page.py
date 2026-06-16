import re
from playwright.async_api import Page

async def run_prescreening(page: Page):
    try:
        print("\n===== PRE-SCREENING STAGE =====")

        prescreening = PrescreeningPage(page)

        # Wait for pre-screening content to load
        await page.get_by_text(
            re.compile(
                "before we move forward",
                re.I
            )
        ).wait_for(timeout=15000)

        print("✅ Pre-screening content detected")

        # ── First Section: Student + Termination Questions ──────────────────
        await prescreening.answer_student_question()
        await prescreening.answer_termination_question()
        await prescreening.submit_first_section()
        
        print("✅ First section completed (Student + Termination)")

        # ── Second Section: Criminal Question ──────────────────────────────
        await prescreening.answer_criminal_question()
        await prescreening.submit_criminal_section()
        
        print("✅ Second section completed (Criminal)")

        # ── Third Section: Job Fit Dropdown ────────────────────────────────
        await prescreening.select_job_fit()
        
        print("✅ Third section completed (Job Fit)")

        # ── Fourth Section: Job Priority Dropdown ──────────────────────────
        await prescreening.select_job_priority()
        
        print("✅ Fourth section completed (Job Priority)")

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
