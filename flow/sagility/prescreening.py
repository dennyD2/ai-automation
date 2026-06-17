import re
from playwright.async_api import Page
from pages.sagility.prescreening_page import PrescreeningPage
from services.screenshot_service import screenshot

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
        
        await page.wait_for_timeout(3000)

        # ── Second Section: Criminal Question ──────────────────────────────
        await prescreening.answer_criminal_question()
        await prescreening.submit_criminal_section()
        print("✅ Second section completed (Criminal)")
        
        await page.wait_for_timeout(3000)

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
        ).wait_for(timeout=15000)

        print("✅ Transition detected")

        # ── Wait for Assessment Page ──────────────────────────────────────────
        print("🔹 Waiting for assessment page...")

        # Wait for the page to stabilize
        await page.wait_for_timeout(5000)
        
        # Check for assessment page - use .first to avoid strict mode
        try:
            await page.get_by_text(
                re.compile(r"assessment|start|skip", re.IGNORECASE)
            ).first.wait_for(state="visible", timeout=30000)
            print("✅ Assessment page detected")
        except:
            # Fallback: wait for any visible button
            await page.locator("button").first.wait_for(state="visible", timeout=15000)
            print("✅ Assessment page detected via button")
        
        print("✅ Assessment stage reached")

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise
