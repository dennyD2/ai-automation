from playwright.async_api import Page

class PrescreeningPage:
    def __init__(self, page: Page):
        self.page = page

    async def answer_student_question(self):
        """Answer 'Are you currently a full-time student?' -> No"""
        # XPath: //input[@id='_r_0_-prescreen-yn-no']
        await self.page.locator(
            "//input[@id='_r_0_-prescreen-yn-no']"
        ).click()
        print("✅ Student question answered (No)")

    async def answer_termination_question(self):
        """Answer 'Have you ever been terminated from a position?' -> No"""
        # XPath: //input[@id='_r_1_-prescreen-term-no']
        await self.page.locator(
            "//input[@id='_r_1_-prescreen-term-no']"
        ).click()
        print("✅ Terminated question answered (No)")

    async def submit_first_section(self):
        """Click Submit button for 1st module"""
        # XPath: //div[@id='pre-screening-checkbox-question']//button[@class='_submit_1pjtv_110']
        await self.page.locator(
            "//div[@id='pre-screening-checkbox-question']//button[@class='_submit_1pjtv_110']"
        ).click()
        print("✅ Submitted first section")

    async def answer_criminal_question(self):
        """Answer 'Have you ever been convicted of a criminal offense?' -> No"""
        # Wait for the criminal question to appear
        await self.page.wait_for_timeout(2000)
        
        # XPath: //div[@id='pre-screening-crime-question']//input[@id='_r_2_-prescreen-yn-no']
        await self.page.locator(
            "//div[@id='pre-screening-crime-question']//input[@id='_r_2_-prescreen-yn-no']"
        ).click()
        print("✅ Criminal offense question answered (No)")

    async def submit_criminal_section(self):
        """Click Submit button for 2nd module"""
        # XPath: //div[@id='pre-screening-crime-question']//button[@class='_submit_1pjtv_110']
        await self.page.locator(
            "//div[@id='pre-screening-crime-question']//button[@class='_submit_1pjtv_110']"
        ).click()
        print("✅ Submitted criminal section")

    async def select_job_fit(self):
        """Select 'Culture & team fit' from dropdown"""
        await self.page.wait_for_timeout(2000)
        
        # XPath: //div[@id='pre-screening-next-role-motivation']//select[@class='billi-inline-form-input']
        dropdown = self.page.locator(
            "//div[@id='pre-screening-next-role-motivation']//select[@class='billi-inline-form-input']"
        )
        
        await dropdown.wait_for()
        await dropdown.select_option(
            label="Culture & team fit"
        )
        print("✅ Selected Culture & team fit")
        
        await self.page.wait_for_timeout(1000)

        # XPath: //div[@id='pre-screening-next-role-motivation']//button[text()='Continue']
        continue_btn = self.page.locator(
            "//div[@id='pre-screening-next-role-motivation']//button[text()='Continue']"
        )
        
        await continue_btn.wait_for(state="visible", timeout=15000)
        await continue_btn.click()
        print("✅ Continued first dropdown")

    async def select_job_priority(self):
        """Select 'Brand name' from dropdown"""
        await self.page.wait_for_timeout(2000)
        
        # XPath: //div[@id='pre-screening-workplace-priority']//select[@class='billi-inline-form-input']
        dropdown = self.page.locator(
            "//div[@id='pre-screening-workplace-priority']//select[@class='billi-inline-form-input']"
        )
        
        await dropdown.wait_for()
        await dropdown.select_option(
            label="Brand name"
        )
        print("✅ Selected Brand name")
        
        await self.page.wait_for_timeout(1000)

        # XPath: //div[@id='pre-screening-workplace-priority']//button[text()='Continue']
        continue_btn = self.page.locator(
            "//div[@id='pre-screening-workplace-priority']//button[text()='Continue']"
        )
        
        await continue_btn.wait_for(state="visible", timeout=15000)
        await continue_btn.click()
        print("✅ Continued second dropdown")
