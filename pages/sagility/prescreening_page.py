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
        await self.page.get_by_role(
            "button",
            name="Submit"
        ).first.click()
        print("✅ Submitted first section")

    async def answer_criminal_question(self):
        """Answer 'Have you ever been convicted of a criminal offense?' -> No"""
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
        await self.page.get_by_role(
            "button",
            name="Submit"
        ).first.click()
        print("✅ Submitted criminal section")

    async def select_job_fit(self):
        """Select 'Culture & team fit' from dropdown"""
        print("🔹 [select_job_fit] Starting...")
        
        await self.page.wait_for_timeout(2000)
        
        # Find and select from dropdown
        dropdown = self.page.locator(
            "text=What would make this job a good fit for you?"
        ).locator("xpath=..").locator("select")
        
        await dropdown.wait_for()
        await dropdown.select_option(
            label="Culture & team fit"
        )
        print("✅ Selected Culture & team fit")
        
        await self.page.wait_for_timeout(1500)

        # Get all Continue buttons
        continue_buttons = await self.page.get_by_role("button", name="Continue").all()
        print(f"🔹 [select_job_fit] Found {len(continue_buttons)} Continue buttons")
        
        # Click the second one (index 1) - the one for this section
        if len(continue_buttons) > 1:
            await continue_buttons[1].click(force=True)
        else:
            await continue_buttons[0].click(force=True)
        
        print("✅ Continued first dropdown")

    async def select_job_priority(self):
        """Select 'Brand name' from dropdown"""
        print("🔹 [select_job_priority] Starting...")
        
        await self.page.wait_for_timeout(2000)
        
        # Find and select from dropdown
        dropdown = self.page.locator(
            "text=What matters most to you when choosing a job?"
        ).locator("xpath=..").locator("select")
        
        await dropdown.wait_for()
        await dropdown.select_option(
            label="Brand name"
        )
        print("✅ Selected Brand name")
        
        await self.page.wait_for_timeout(1500)

        # Get all Continue buttons
        continue_buttons = await self.page.get_by_role("button", name="Continue").all()
        print(f"🔹 [select_job_priority] Found {len(continue_buttons)} Continue buttons")
        
        # Click the third one (index 2) - the one for this section
        if len(continue_buttons) > 2:
            await continue_buttons[2].click(force=True)
        else:
            await continue_buttons[-1].click(force=True)
        
        print("✅ Continued second dropdown")
