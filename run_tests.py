# run_tests.py
import asyncio
import json
import os
import re
from typing import Any, Dict, List

import pandas as pd
from playwright.async_api import async_playwright
from langchain_openai import ChatOpenAI

BASE_URL = "https://trajector.bling-ai.com/trajector/login/"

EXCEL_PATH = "Trajector Test cases.xlsx"
SHEET_NAME = "Login"

ARTIFACTS_DIR = "artifacts"

# LLM (only used when we can't auto-derive a plan from the sheet)
llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)

FIELDS = {"email": ["email"], "password": ["password"]}


def to_str(x: Any) -> str:
    if x is None:
        return ""
    # pandas NA
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def try_auto_plan(description: str) -> List[Dict[str, Any]]:
    """
    Deterministic plan for common "leave field empty" style tests.
    Falls back to LLM when description doesn't match known patterns.
    """
    d = (description or "").lower()

    steps: List[Dict[str, Any]] = []

    # Fill email empty
    if "leave email" in d and "empty" in d:
        steps.append({"action": "fill", "field": "email", "value": ""})

    # Fill password empty
    if "leave password" in d and "empty" in d:
        steps.append({"action": "fill", "field": "password", "value": ""})

    # Click sign in / login
    if ("click" in d) and (("login" in d) or ("sign in" in d) or ("sign-in" in d)):
        steps.append({"action": "click", "button": "sign_in"})

    return steps


def extract_json(text: str) -> Dict[str, Any]:
    """
    Extract first {...} block and parse JSON.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


def get_plan(description: str, expectation: str, page_text: str) -> Dict[str, Any]:
    """
    Returns:
      { "steps": [ {action/fill/field/value} | {action/click/button} ] }
    """
    prompt = f"""
You control a browser.
You MUST follow the test case steps exactly. If the test says "leave ... empty",
then you must fill "" (empty string) for that field.

Test case:
{description}

Expected behavior (used for guidance only):
{expectation}

Current page text (may be truncated):
{page_text[:900]}

Return ONLY valid JSON:
{{
  "steps": [
    {{
      "action": "fill",
      "field": "email" | "password",
      "value": string
    }},
    {{
      "action": "click",
      "button": "sign_in"
    }}
  ]
}}

Rules:
- Use only fields: email, password.
- Only use button: sign_in.
- Do not add extra steps.
"""
    res = llm.invoke(prompt).content
    data = extract_json(res)
    if isinstance(data, dict) and "steps" in data and isinstance(data["steps"], list):
        return data
    return {"steps": []}


async def ensure_login_page_ready(page):
    # Try to wait for either the email input or at least an input
    try:
        await page.get_by_placeholder("Email").first.wait_for(timeout=5000)
        return
    except Exception:
        pass
    try:
        await page.locator("input").first.wait_for(timeout=5000)
        return
    except Exception:
        # Last resort
        await page.wait_for_timeout(500)


def field_locator(page, field: str):
    if field == "email":
        # Multiple fallback strategies for robustness
        return (
            page.get_by_label("Email")
            or page.get_by_placeholder("Email")
            or page.locator('input[type="email" i]')
            or page.locator('input[name*="email" i]')
        )
    if field == "password":
        return (
            page.get_by_label("Password")
            or page.get_by_placeholder("Password")
            or page.locator('input[type="password" i]')
            or page.locator('input[name*="password" i]')
        )
    raise ValueError(f"Unknown field: {field}")


async def execute_step(page, step: Dict[str, Any]):
    action = step.get("action")
    if action == "fill":
        field = step.get("field")
        value = to_str(step.get("value", ""))  # value for empty should become ""
        loc = field_locator(page, field)
        count = await loc.count()
        if count == 0:
            raise RuntimeError(f"No input found for field={field}")
        await loc.first.fill(value)

    elif action == "click":
        btn_name = step.get("button")
        if btn_name != "sign_in":
            raise ValueError(f"Unknown button: {btn_name}")

        # Prefer exact "Sign in" role button
