import asyncio
import os
import pandas as pd
from browser_use import Agent
from langchain.chat_models import ChatOpenAI


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

    # ✅ Proper DeepSeek via OpenAI-compatible API
    llm = ChatOpenAI(
        model="deepseek-chat",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com/v1",
        temperature=0
    )

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
