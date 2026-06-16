import re
from playwright.async_api import Page

class PrescreeningPage:
    def __init__(self, page: Page):
        self.page = page

    async def answer_student_question(self):
        section = self.page.locator(
            "text=Are you currently a full-time student?"
        ).locator("xpath=..")

        await section.get_by_text(
            "No",
            exact=True
        ).click()

        print("✅ Student question answered")

    async def answer_termination_question(self):
        section = self.page.locator(
            "text=Have you ever been terminated from a position?"
        ).locator("xpath=..")

        await section.get_by_text(
            "No",
            exact=True
        ).click()

        print("✅ Terminated question answered")

    async def submit_first_section(self):
        section = self.page.locator(
            "text=Have you ever been terminated from a position?"
        ).locator("xpath=..").locator("xpath=..")

        await section.get_by_role(
            "button",
            name="Submit"
        ).click()

        print("✅ Submitted first section")

    async def answer_criminal_question(self):
        section = self.page.locator(
            "text=Have you ever been convicted of a criminal offense?"
        ).locator("xpath=..")

        await section.get_by_text(
            "No",
            exact=True
        ).click()

        print("✅ Criminal offense question answered")

    async def submit_criminal_section(self):
        section = self.page.locator(
            "text=Have you ever been convicted of a criminal offense?"
        ).locator("xpath=..").locator("xpath=..")

        await section.get_by_role(
            "button",
            name="Submit"
        ).click()

        print("✅ Submitted criminal section")

    async def select_job_fit(self):
        section = self.page.locator(
            "text=What would make this job a good fit for you?"
        ).locator("xpath=..")

        dropdown = section.locator("select")

        await dropdown.wait_for()

        await dropdown.select_option(
            label="Culture & team fit"
        )

        print("✅ Selected Culture & team fit")

        await section.get_by_role(
            "button",
            name="Continue"
        ).click()

        print("✅ Continued first dropdown")

    async def select_job_priority(self):
        section = self.page.locator(
            "text=What matters most to you when choosing a job?"
        ).locator("xpath=..")

        dropdown = section.locator("select")

        await dropdown.wait_for()

        await dropdown.select_option(
            label="Work-life balance"
        )

        print("✅ Selected Work-life balance")

        await section.get_by_role(
            "button",
            name="Continue"
        ).click()

        print("✅ Continued second dropdown")
