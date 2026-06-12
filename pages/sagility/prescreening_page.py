from playwright.async_api import Page

class PrescreeningPage:
    def __init__(self, page: Page):
        self.page = page

    async def answer_student_question(self):
        section = self.page.locator(
            "text=Are you currently a full-time student?"
        )

        await section.locator(
            ".."
        ).get_by_text("No").click()

        print("✅ Student question answered")

    async def answer_termination_question(self):
        section = self.page.locator(
            "text=Have you ever been terminated from a position?"
        )

        await section.locator(
            ".."
        ).get_by_text("No").click()

        print("✅ Terminated question answered")

    async def answer_criminal_question(self):
        section = self.page.locator(
            "text=Have you ever been convicted of a criminal offense?"
        )

        await section.locator(
            ".."
        ).get_by_text("No").click()

        print("✅ Criminal offense question answered")

    async def submit_knockout_questions(self):
        await self.page.get_by_role(
            "button",
            name="Submit"
        ).nth(1).click()

        print("✅ Submitted criminal offense section")

    async def select_job_fit(self):
        await self.page.locator(
            "select"
        ).nth(0).select_option(
            label="Stability"
        )

        print("✅ Selected Stability")

    async def continue_job_fit(self):
        await self.page.get_by_role(
            "button",
            name="Continue"
        ).nth(0).click()

        print("✅ Continued first dropdown")

    async def select_job_priority(self):
        await self.page.locator(
            "select"
        ).nth(1).select_option(
            label="Work-life balance"
        )

        print("✅ Selected Work-life balance")

    async def continue_job_priority(self):
        await self.page.get_by_role(
            "button",
            name="Continue"
        ).nth(1).click()

        print("✅ Continued second dropdown")
