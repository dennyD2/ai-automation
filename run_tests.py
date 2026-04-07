import asyncio
import os
import pandas as pd
from browser_use import Agent
from langchain_openai import ChatOpenAI


class AsyncCompatibleLLM:
    def __init__(self, llm):
        self.llm = llm
        self.provider = "openai"
        self.model = getattr(llm, "model", "deepseek-chat")
        self.model_name = getattr(llm, "model_name", self.model)

    async def ainvoke(self, input, **kwargs):  # ✅ accept anything
        return self.llm.invoke(input)

    def invoke(self, input, **kwargs):  # ✅ accept anything
        return self.llm.invoke(input)


async def run_suite():
    df = pd.read_excel(
        "Trajector Test cases.xlsx",
        sheet_name="Login",
        engine="openpyxl"
    )

    # 🔥 Convert entire sheet into structured test cases
    test_cases = ""

    for _, row in df.iterrows():
        test_cases += f"""
Test Case ID: {row['Test case ID']}
Description: {row['Description']}
Expected Result: {row['Expectation']}
---
"""

    BASE_URL = "https://your-login-page.com"  # ⚠️ CHANGE THIS

    # 🔥 SINGLE MASTER PROMPT
    task = f"""
You are an expert QA automation tester.

Open the website: {BASE_URL}

You are given a list of test cases.

Execute ALL test cases one by one.

For each test case:
1. Perform the steps described
2. Validate the expected result
3. Decide PASS or FAIL

Finally, generate a report in this format:

Test Case ID | Result (PASS/FAIL) | Reason

Test Cases:
{test_cases}
"""

    llm = AsyncCompatibleLLM(
        ChatOpenAI(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            temperature=0
        )
    )

    print("🚀 Running full test suite...")

    agent = Agent(task=task, llm=llm)

    result = await agent.run()

    print("\n📊 FINAL TEST REPORT:\n")
    print(result)


if __name__ == "__main__":
    asyncio.run(run_suite())
