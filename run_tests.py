import asyncio
import os
import pandas as pd
from browser_use import Agent
from langchain_openai import ChatOpenAI


# ✅ Compatibility wrapper (FINAL stable version)
class AsyncCompatibleLLM:
    def __init__(self, llm):
        self.llm = llm
        self.provider = "openai"
        self.model = getattr(llm, "model", "deepseek-chat")
        self.model_name = getattr(llm, "model_name", self.model)

    async def ainvoke(self, *args, **kwargs):
        return self.llm.invoke(*args, **kwargs)

    def invoke(self, *args, **kwargs):
        return self.llm.invoke(*args, **kwargs)


async def run_suite():
    try:
        df = pd.read_excel(
            "Trajector Test cases.xlsx",
            sheet_name="Login",
            engine="openpyxl"
        )
    except Exception as e:
        print(f"❌ Error reading Excel: {e}")
        return

    # 🔥 Convert full sheet into readable test cases
    test_cases = ""

    for _, row in df.iterrows():
        test_cases += f"""
Test Case ID: {row['Test case ID']}
Description: {row['Description']}
Expected Result: {row['Expectation']}
---
"""

    BASE_URL = "https://your-login-page.com"  # ⚠️ CHANGE THIS

    # ✅ PHASE 1: EXECUTION TASK (no JSON forcing)
    task = f"""
You are an AI QA tester.

Open the website: {BASE_URL}

Execute the following test cases one by one.

For each test case:
- Perform the described steps
- Observe the result carefully
- Do NOT assume success

After executing all test cases, summarize what happened.

Test Cases:
{test_cases}
"""

    base_llm = ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0
    )

    llm = AsyncCompatibleLLM(base_llm)

    print("🚀 Running full test suite...\n")

    try:
        agent = Agent(task=task, llm=llm)

        execution_result = await agent.run()

        print("\n🧾 RAW EXECUTION OUTPUT:\n")
        print(execution_result)

    except Exception as e:
        print(f"❌ Agent execution failed: {e}")
        return

    # ✅ PHASE 2: REPORT GENERATION (LLM only, no browser)
    print("\n📊 Generating final report...\n")

    report_prompt = f"""
You are a QA expert.

Based on the execution output below, generate a structured report.

Format:
Test Case ID | Result (PASS/FAIL) | Reason

Be strict. If result is unclear, mark FAIL.

Execution Output:
{execution_result}
"""

    try:
        report = base_llm.invoke(report_prompt)

        print("\n✅ FINAL TEST REPORT:\n")
        print(report.content if hasattr(report, "content") else report)

    except Exception as e:
        print(f"❌ Report generation failed: {e}")


if __name__ == "__main__":
    asyncio.run(run_suite())
