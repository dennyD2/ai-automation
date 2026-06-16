import re
from playwright.async_api import Page
from services.screenshot_service import screenshot

async def run_assessment(page: Page):
    try:
        print("\n===== ASSESSMENT STAGE =====")

        print("🔹 Waiting for assessment page...")
        
        # Wait for the page to load
        await page.wait_for_timeout(5000)
        
        # Take a screenshot for debugging
        await screenshot(page, "ASSESSMENT_PAGE_LOADED")
        
        # Check for the assessment text
        body = await page.evaluate("() => document.body.innerText")
        print(f"🔹 Page content (first 500 chars):")
        print(body[:500] if body else "EMPTY")
        
        # Wait for assessment content
        await page.get_by_text(
            re.compile(
                "assessment|next stage|start",
                re.I
            )
        ).wait_for(timeout=15000)
        print("✅ Assessment page detected")

        # Click Skip Assessment
        print("🔹 Clicking Skip Assessment (testing only)...")
        
        # Find the Skip Assessment button
        # Based on the image, it's the button with "Skip Assessment"
        skip_btn = page.get_by_role(
            "button",
            name=re.compile("skip assessment", re.I)
        )
        
        # If not found, try by text
        if await skip_btn.count() == 0:
            skip_btn = page.get_by_text(re.compile("skip assessment", re.I))
        
        await skip_btn.click(timeout=5000)
        print("✅ Skip Assessment clicked")
        
        # Wait for the next page
        print("🔹 Waiting for next stage...")
        await page.wait_for_timeout(5000)
        print("✅ Assessment stage completed")
        
    except Exception as e:
        print(f"❌ ASSESSMENT ERROR: {e}")
        raise
