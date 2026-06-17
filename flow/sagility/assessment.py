import re
from playwright.async_api import Page
from services.screenshot_service import screenshot

async def run_assessment(page: Page):
    try:
        print("\n===== ASSESSMENT STAGE =====")

        print("🔹 Waiting for assessment page to load...")
        
        # Wait for the page to load
        await page.wait_for_timeout(5000)
        
        # Take a screenshot for debugging
        await screenshot(page, "ASSESSMENT_PAGE_LOADED")
        
        # Check page content
        body = await page.evaluate("() => document.body.innerText")
        print(f"🔹 Assessment page content (first 500 chars):")
        print(body[:500] if body else "EMPTY")
        
        # Wait for assessment content - use .first to avoid strict mode violation
        try:
            await page.get_by_text(
                re.compile(r"assessment|start|skip", re.IGNORECASE)
            ).first.wait_for(state="visible", timeout=30000)
            print("✅ Assessment page detected")
        except:
            # If text not found, wait for any button
            await page.locator("button").first.wait_for(state="visible", timeout=15000)
            print("✅ Assessment page detected via button")

        # Click Skip Assessment (testing only)
        print("🔹 Clicking Skip Assessment...")
        
        # Try multiple ways to find and click Skip Assessment
        try:
            # Try by role
            skip_btn = page.get_by_role(
                "button",
                name=re.compile(r"skip assessment", re.IGNORECASE)
            )
            await skip_btn.click(timeout=5000)
            print("✅ Skip Assessment clicked (by role)")
        except:
            try:
                # Try by text - use .first
                skip_btn = page.get_by_text(
                    re.compile(r"skip assessment", re.IGNORECASE)
                ).first
                await skip_btn.click(timeout=5000)
                print("✅ Skip Assessment clicked (by text)")
            except:
                try:
                    # Try by class (second button)
                    skip_btn = page.locator("button.billi-action-button").nth(1)
                    await skip_btn.click(timeout=5000)
                    print("✅ Skip Assessment clicked (by class)")
                except:
                    # Fallback: click any button with "Skip" text
                    skip_btn = page.locator("button:has-text('Skip')")
                    await skip_btn.click(timeout=5000)
                    print("✅ Skip Assessment clicked (by contains)")

        # Wait for the next page
        print("🔹 Waiting for transition after assessment...")
        await page.wait_for_timeout(5000)
        
        # Check the next page
        body = await page.evaluate("() => document.body.innerText")
        print(f"🔹 After assessment page content (first 500 chars):")
        print(body[:500] if body else "EMPTY")
        
        print("✅ Assessment stage completed")
        
    except Exception as e:
        print(f"❌ ASSESSMENT ERROR: {e}")
        raise
