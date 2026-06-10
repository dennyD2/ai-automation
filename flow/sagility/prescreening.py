from playwright.async_api import Page

async def run_prescreening(page: Page):
    print("\n===== PRE-SCREENING STAGE =====")

    # Question:
    # Are you currently a full-time student?
    # Safe Answer: No

    await page.get_by_text("No").nth(0).click()

    await page.get_by_role(
        "button",
        name="Submit"
    ).click()

    # Knockout Question:
    # Have you ever been terminated from a position?
    # MUST answer No

    await page.get_by_text("No").nth(1).click()

    await page.get_by_role(
        "button",
        name="Submit"
    ).click()

    # Knockout Question:
    # Have you ever been convicted of a criminal offense?
    # MUST answer No

    await page.get_by_text("No").nth(2).click()

    await page.get_by_role(
        "button",
        name="Submit"
    ).click()

    await page.locator("select").nth(0).select_option(
        label="Stability"
    )

    await page.get_by_role(
        "button",
        name="Continue"
    ).click()

    await page.locator("select").nth(1).select_option(
        label="Work-life balance"
    )

    await page.get_by_role(
        "button",
        name="Continue"
    ).click()

    await page.wait_for_timeout(3000)

    print("✅ Pre-screening completed")
