from playwright.async_api import Page

class PrescreeningPage:
    def __init__(self, page: Page):
        self.page = page

    async def answer_student_question(self):
        """Answer 'Are you currently a full-time student?' -> No"""
        await self.page.locator(
            "//input[@id='_r_0_-prescreen-yn-no']"
        ).click()
        print("✅ Student question answered (No)")

    async def answer_termination_question(self):
        """Answer 'Have you ever been terminated from a position?' -> No"""
        await self.page.locator(
            "//input[@id='_r_1_-prescreen-term-no']"
        ).click()
        print("✅ Terminated question answered (No)")

    async def submit_first_section(self):
        """Click Submit button for 1st module"""
        await self.page.locator(
            "//div[@id='pre-screening-checkbox-question']//button[@class='_submit_1pjtv_110']"
        ).click()
        print("✅ Submitted first section")

    async def answer_criminal_question(self):
        """Answer 'Have you ever been convicted of a criminal offense?' -> No"""
        await self.page.wait_for_timeout(2000)
        await self.page.locator(
            "//div[@id='pre-screening-crime-question']//input[@id='_r_2_-prescreen-yn-no']"
        ).click()
        print("✅ Criminal offense question answered (No)")

    async def submit_criminal_section(self):
        """Click Submit button for 2nd module"""
        print("🔹 [submit_criminal_section] Looking for Submit button...")
        
        # Take screenshot before clicking
        await screenshot(self.page, "BEFORE_CRIMINAL_SUBMIT")
        
        # XPath for the Submit button in the criminal section
        submit_btn = self.page.locator(
            "//div[@id='pre-screening-crime-question']//button[@class='_submit_1pjtv_110']"
        )
        
        # Wait for it to be visible
        await submit_btn.wait_for(state="visible", timeout=10000)
        print("✅ Submit button found")
        
        # Click it
        await submit_btn.click()
        print("✅ Submitted criminal section")
        
        # Wait for the criminal section to disappear
        print("🔹 Waiting for criminal section to disappear...")
        await self.page.wait_for_timeout(3000)
        
        # Wait for the criminal question to be hidden or removed
        try:
            criminal_question = self.page.locator(
                "//div[@id='pre-screening-crime-question']"
            )
            await criminal_question.wait_for(state="hidden", timeout=10000)
            print("✅ Criminal section is no longer visible")
        except:
            # Take screenshot to see what's happening
            await screenshot(self.page, "CRIMINAL_STILL_VISIBLE")
            print("⚠️ Criminal section still visible, but continuing...")
            
    async def select_job_fit(self):
        """Select 'Culture & team fit' from dropdown"""
        print("🔹 [select_job_fit] Waiting for dropdown...")
        
        await self.page.wait_for_timeout(2000)
        
        # The select element itself has the ID
        dropdown = self.page.locator(
            "//select[@id='pre-screening-next-role-motivation']"
        )
        
        await dropdown.wait_for(state="visible", timeout=15000)
        await dropdown.select_option(
            label="Culture & team fit"
        )
        print("✅ Selected Culture & team fit")
        
        await self.page.wait_for_timeout(1000)

        # Find the Continue button
        continue_btn = self.page.locator(
            "//button[contains(text(), 'Continue')]"
        ).last
        
        await continue_btn.wait_for(state="visible", timeout=15000)
        await continue_btn.click()
        print("✅ Continued first dropdown")

    async def select_job_priority(self):
        """Select 'Work-life balance' from dropdown"""
        print("🔹 [select_job_priority] Waiting for dropdown...")
        
        await self.page.wait_for_timeout(2000)
        
        # The select element itself has the ID
        dropdown = self.page.locator(
            "//select[@id='pre-screening-next-role-motivation']"
        )
        
        await dropdown.wait_for(state="visible", timeout=15000)
        await dropdown.select_option(
            label="Work-life balance"
        )
        print("✅ Selected Work-life balance")
        
        await self.page.wait_for_timeout(1000)

        # Find the Continue button
        continue_btn = self.page.locator(
            "//button[contains(text(), 'Continue')]"
        ).last
        
        await continue_btn.wait_for(state="visible", timeout=15000)
        await continue_btn.click()
        print("✅ Continued second dropdown")
