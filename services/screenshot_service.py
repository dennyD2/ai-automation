import os

from playwright.async_api import Page

SCREENSHOT_DIR = "artifacts/screenshots"

os.makedirs(
SCREENSHOT_DIR,
exist_ok=True
)

async def screenshot(
page: Page,
name: str
) -> str:

path = os.path.join(
    SCREENSHOT_DIR,
    f"{name}.png"
)

try:

    if page.is_closed():

        print(
            "⚠️ Cannot take screenshot — page already closed"
        )

        return ""

    print(f"🔹 Taking screenshot: {path}")

    await page.screenshot(
        path=path,
        full_page=True
    )

    print(f"✅ Screenshot saved: {path}")

    return path

except Exception as e:

    print(f"❌ Screenshot failed: {e}")

    return ""
