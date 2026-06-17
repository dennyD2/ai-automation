import re
from playwright.async_api import Page
from services.screenshot_service import screenshot

async def run_assessment(page: Page):
    try:
        print("\n===== ASSESSMENT STAGE =====")

        print("🔹 Waiting for assessment page to load (up to 30 seconds)...")
        
        # Wait for the page to fully load
        await page.wait_for_timeout(5000)
        
        # Take a screenshot for debugging
        await screenshot(page, "ASSESSMENT_PAGE_LOADED")
        
        # Check page content
        body = await page.evaluate("() => document.body.innerText")
        print(f"🔹 Assessment page content (first 500 chars):")
        print(body[:500] if body else "EMPTY")
        
        # Wait for assessment content with longer timeout
        try:
            await page.get_by_text(
                re.compile(r"assessment|skip|start", re.IGNORECASE)
            ).first.wait_for(state="visible", timeout=30000)
            print("✅ Assessment page detected")
        except:
            # If text not found, wait for any button
            try:
                await page.locator("button").first.wait_for(state="visible", timeout=20000)
                print("✅ Assessment page detected via button")
            except:
                # Wait and hope the page loads
                await page.wait_for_timeout(10000)
                print("✅ Assessment page detected via timeout")

        # Click Skip Assessment (testing only)
        print("🔹 Clicking Skip Assessment...")
        
        # Try multiple ways to find and click Skip Assessment
        clicked = False
        
        # Method 1: By role
        try:
            skip_btn = page.get_by_role(
                "button",
                name=re.compile(r"skip assessment", re.IGNORECASE)
            )
            await skip_btn.wait_for(state="visible", timeout=15000)
            await skip_btn.click()
            clicked = True
            print("✅ Skip Assessment clicked (by role)")
        except Exception as e:
            print(f"⚠️ Role selector failed: {e}")
        
        # Method 2: By text
        if not clicked:
            try:
                skip_btn = page.get_by_text(
                    re.compile(r"skip assessment", re.IGNORECASE)
                ).first
                await skip_btn.wait_for(state="visible", timeout=10000)
                await skip_btn.click()
                clicked = True
                print("✅ Skip Assessment clicked (by text)")
            except Exception as e:
                print(f"⚠️ Text selector failed: {e}")
        
        # Method 3: By class
        if not clicked:
            try:
                skip_btn = page.locator("button.billi-action-button").nth(1)
                await skip_btn.wait_for(state="visible", timeout=10000)
                await skip_btn.click()
                clicked = True
                print("✅ Skip Assessment clicked (by class)")
            except Exception as e:
                print(f"⚠️ Class selector failed: {e}")
        
        # Method 4: By contains text
        if not clicked:
            try:
                skip_btn = page.locator("button:has-text('Skip')")
                await skip_btn.click(timeout=10000)
                clicked = True
                print("✅ Skip Assessment clicked (by contains)")
            except Exception as e:
                print(f"⚠️ Contains selector failed: {e}")
        
        # Method 5: Click Start Assessment as fallback
        if not clicked:
            try:
                start_btn = page.get_by_role(
                    "button",
                    name=re.compile(r"start assessment", re.IGNORECASE)
                )
                await start_btn.wait_for(state="visible", timeout=10000)
                await start_btn.click()
                clicked = True
                print("✅ Start Assessment clicked (fallback)")
            except Exception as e:
                print(f"⚠️ Start Assessment fallback failed: {e}")
        
        # Method 6: Click any button with "Start" or "Skip" text
        if not clicked:
            try:
                # Find all buttons
                buttons = await page.locator("button").all()
                print(f"🔹 Found {len(buttons)} buttons on the page")
                
                for i, btn in enumerate(buttons):
                    try:
                        text = await btn.text_content()
                        print(f"🔹 Button {i}: {text}")
                        if text and ("Start" in text or "Skip" in text):
                            await btn.click()
                            clicked = True
                            print(f"✅ Clicked button: {text}")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"⚠️ Button iteration failed: {e}")
        
        if not clicked:
            print("⚠️ No assessment button found, continuing anyway...")

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
