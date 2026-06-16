import re
from playwright.async_api import Page

class PrescreeningPage:
    def __init__(self, page: Page):
        self.page = page

    async def answer_student_question(self):
        """Answer 'Are you currently a full-time student?' -> No"""
        section = self.page.locator(
            "text=Are you currently a full-time student?"
        ).locator("xpath=..")

        await section.get_by_text(
            "No",
            exact=True
        ).click()

        print("✅ Student question answered (No)")

    async def answer_termination_question(self):
        """Answer 'Have you ever been terminated from a position?' -> No"""
        section = self.page.locator(
            "text=Have you ever been terminated from a position?"
        ).locator("xpath=..")

        await section.get_by_text(
            "No",
            exact=True
        ).click()

        print("✅ Terminated question answered (No)")

    async def submit_first_section(self):
        """Click Submit button after termination question"""
        section = self.page.locator(
            "text=Have you ever been terminated from a position?"
        ).locator("xpath=..").locator("xpath=..")

        await section.get_by_role(
            "button",
            name="Submit"
        ).click()

        print("✅ Submitted first section")

    async def answer_criminal_question(self):
        """Answer 'Have you ever been convicted of a criminal offense?' -> No"""
        # Wait for the criminal question to appear
        await self.page.wait_for_timeout(2000)
        
        section = self.page.locator(
            "text=Have you ever been convicted of a criminal offense?"
        ).locator("xpath=..")

        await section.get_by_text(
            "No",
            exact=True
        ).click()

        print("✅ Criminal offense question answered (No)")

    async def submit_criminal_section(self):
        """Click Submit button after criminal question"""
        section = self.page.locator(
            "text=Have you ever been convicted of a criminal offense?"
        ).locator("xpath=..").locator("xpath=..")

        await section.get_by_role(
            "button",
            name="Submit"
        ).click()

        print("✅ Submitted criminal section")

    async def select_job_fit(self):
        """Select 'Culture & team fit' from dropdown"""
        # Wait for the question to appear
        await self.page.wait_for_timeout(2000)
        
        # Find the section containing the question
        section = self.page.locator(
            "text=What would make this job a good fit for you?"
        ).locator("xpath=..")
    
        # Find and select from dropdown within the section
        dropdown = section.locator("select")
        await dropdown.wait_for()
        await dropdown.select_option(
            label="Culture & team fit"
        )
        print("✅ Selected Culture & team fit")
    
        # Click Continue button - try multiple approaches
        try:
            # Approach 1: Find Continue button within the section
            await section.get_by_role(
                "button",
                name="Continue"
            ).click()
        except Exception:
            # Approach 2: Find Continue button on the page (not scoped)
            await self.page.get_by_role(
                "button",
                name="Continue"
            ).click()
        
        print("✅ Continued first dropdown")
        
    async def select_job_priority(self):
        """Select 'Brand name' from dropdown"""
        # Wait for the question to appear
        await self.page.wait_for_timeout(2000)
        
        section = self.page.locator(
            "text=What matters most to you when choosing a job?"
        ).locator("xpath=..")

        dropdown = section.locator("select")

        await dropdown.wait_for()

        await dropdown.select_option(
            label="Brand name"
        )

        print("✅ Selected Brand name")

        await section.get_by_role(
            "button",
            name="Continue"
        ).click()

        print("✅ Continued second dropdown")
