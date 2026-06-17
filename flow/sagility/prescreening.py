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

        # ── Wait for the transition to complete ──────────────────────────────
        print("🔹 Waiting for transition animation to complete...")

        # Wait for the transition text to disappear
        try:
            await page.get_by_text(
                re.compile("taking you to next stage", re.I)
            ).first.wait_for(state="hidden", timeout=30000)
            print("✅ Transition complete - page has moved on")
        except:
            print("⚠️ Transition text still visible, waiting longer...")
            await page.wait_for_timeout(10000)

        # ── Wait for Assessment Page ──────────────────────────────────────────
        print("🔹 Waiting for assessment page to load...")
        await page.wait_for_timeout(5000)

        # Check if we're on the assessment page
        body = await page.evaluate("() => document.body.innerText")
        print(f"🔹 Current page content (first 500 chars):")
        print(body[:500] if body else "EMPTY")

        # Look for assessment page indicators
        if "assessment" in body.lower() or "skip" in body.lower() or "start" in body.lower():
            print("✅ Assessment page detected")
        else:
            # If not, wait some more
            print("🔹 Waiting additional time for assessment page...")
            await page.wait_for_timeout(10000)
            body = await page.evaluate("() => document.body.innerText")
            if "assessment" in body.lower() or "skip" in body.lower() or "start" in body.lower():
                print("✅ Assessment page detected after waiting")
            else:
                print("⚠️ Assessment page not detected, but continuing...")

        print("✅ Assessment stage reached")

    except Exception as e:
        print(f"❌ PRE-SCREENING ERROR: {e}")
        raise
