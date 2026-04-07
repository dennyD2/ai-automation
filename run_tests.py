import asyncio
import os
import pandas as pd
from browser_use import Agent
from langchain_openai import ChatOpenAI


# ✅ Wrapper to fix async compatibility (THIS is key)
class AsyncCompatibleLLM:
    def __init__(self, llm):
        self.llm = llm

    async def ainvoke(self, input, config=None):
        return self.llm.invoke(input)

    def invoke(self, input, config=None):
        return self.llm.invoke(input)


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

    # ✅ DeepSeek via OpenAI-compatible API
    base_llm = ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0
    )

    llm = AsyncCompatibleLLM(base_llm)

    for index, row in df.iterrows():
        instruction = str(row.iloc[0])

        if not instruction or instruction.strip().lower() in ["nan", "none", ""]:
            continue

        print(f"\n🚀 Running Test Case {index + 1}: {instruction}")

        try:
            agent = Agent(
                task=instruction,
                llm=llm
            )

            await agent.run()

            print(f"✅ Test Case {index + 1} Passed")

        except Exception as e:
            print(f"❌ Test Case {index + 1} Failed: {e}")


if __name__ == "__main__":
    asyncio.run(run_suite())
