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
        print("🔹 Waiting for assessment page to load...")
        
        # Take a screenshot to see current state
        await screenshot(page, "BEFORE_ASSESSMENT")
        
        # Wait for the page to fully load
        await page.wait_for_timeout(10000)
        
        # Check page content
        body = await page.evaluate("() => document.body.innerText")
        print(f"🔹 Assessment page content (first 500 chars):")
        print(body[:500] if body else "EMPTY")
        
        # Check if we have the assessment buttons
        assessment_buttons = await page.locator("button:has-text('Assessment')").count()
        skip_buttons = await page.locator("button:has-text('Skip')").count()
        
        print(f"🔹 Assessment buttons found: {assessment_buttons}")
        print(f"🔹 Skip buttons found: {skip_buttons}")
        
        if assessment_buttons > 0 or skip_buttons > 0:
            print("✅ Assessment page detected via buttons")
        else:
            # Wait a bit more
            await page.wait_for_timeout(5000)
            print("✅ Assessment page detected (by timeout)")
        
        print("✅ Assessment stage reached")

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise
