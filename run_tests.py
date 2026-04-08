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

def expected_message(expectation: Any) -> str:
    """
    Excel 'Expectation' cells often contain extra framing text like:
      Error message should display: "Please enter a correct email."
    We validate against the quoted message if present; otherwise fall back to the raw string.
    """
    raw = norm_space(to_str(expectation))
    if not raw:
        return ""

    # Prefer first quoted segment (supports "..." or '...').
    m = re.search(r"['\"]([^'\"]+)['\"]", raw)
    if m:
        return norm_space(m.group(1))

    # Fallback: take text after colon if it exists.
    if ":" in raw:
        return norm_space(raw.split(":", 1)[1])

    return raw


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
      "action": "fill" | "click",
      "field": "email" | "password",   // optional for known login fields
      "button": "sign_in",             // optional for known login button
      "target": string,                // generic visible label/text/placeholder
      "value": string                  // only for fill
    }}
  ]
}}

Rules:
- Follow the sheet steps exactly.
- For "leave empty", set value to "".
- Prefer known login keys when obvious:
  - Email -> field=email
  - Password -> field=password
  - Login/Sign in -> button=sign_in
- For non-login modules/pages, use target with visible text/label/placeholder.
- Do not invent credentials or extra actions.
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


def generic_locator(page, target: str):
    t = norm_space(target)
    if not t:
        return page.locator("input, textarea, [contenteditable='true'], button")
    escaped = re.escape(t)
    return (
        page.get_by_label(t)
        or page.get_by_placeholder(t)
        or page.get_by_role("button", name=re.compile(escaped, re.I))
        or page.get_by_text(re.compile(escaped, re.I))
        or page.locator(f'input[placeholder*="{t}"], textarea[placeholder*="{t}"]')
    )


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
        target = to_str(step.get("target", ""))
        value = to_str(step.get("value", ""))  # value for empty should become ""
        if field in ("email", "password"):
            loc = field_locator(page, field)
        else:
            loc = generic_locator(page, target)
        count = await loc.count()
        if count == 0:
            raise RuntimeError(f"No input found for field={field or target}")
        await loc.first.fill(value)
        # Many forms validate on blur; Tab triggers blur best-effort.
        try:
            await loc.first.press("Tab")
        except Exception:
            pass

    elif action == "click":
        btn_name = step.get("button")
        if btn_name == "sign_in":
            btn = page.get_by_role(
                "button",
                name=re.compile(r"^\s*Sign in\s*$", re.I),
            ).first
            if await btn.count() == 0:
                btn = page.get_by_role(
                    "button",
                    name=re.compile(r"Sign in|Login", re.I),
                ).first
        else:
            target = to_str(step.get("target", "")) or to_str(btn_name)
            btn = generic_locator(page, target).first
        await btn.click()

    else:
        raise ValueError(f"Unknown action: {action}")


def validate(expectation, text: str) -> str:
    exp = expected_message(expectation).lower()
    body = norm_space(text).lower()
    if not exp:
        return "FAIL"
    return "PASS" if exp in body else "FAIL"


async def wait_for_expected_text(page, expectation: str, timeout_ms: int = 7000) -> bool:
    expected = expected_message(expectation).lower()
    if not expected:
        return False

    end_time = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    while True:
        body = norm_space(await page.locator("body").inner_text()).lower()
        if expected in body:
            return True
        if asyncio.get_running_loop().time() >= end_time:
            return False
        await page.wait_for_timeout(300)


async def take_case_screenshot(page, case_id: str) -> str:
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    out_path = os.path.join(ARTIFACTS_DIR, f"{case_id}.png")
    await page.screenshot(path=out_path, full_page=True)
    return out_path


async def run_suite():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    results = []
    # Write a minimal artifact early so CI always has something to upload.
    out_results = os.path.join(ARTIFACTS_DIR, "results.json")
    with open(out_results, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(10000)

        for idx, row in df.iterrows():
            case_id = to_str(row.get("Test case ID", row.get("Test case", ""))) or f"row_{idx}"
            description = to_str(row.get("Description", ""))
            expectation = to_str(row.get("Expectation", ""))

            print(f"\n🚀 {case_id}")
            screenshot_path = ""

            try:
                await page.goto(BASE_URL)
                await ensure_login_page_ready(page)
                await page.wait_for_timeout(300)

                page_text = await page.locator("body").inner_text()

                # Deterministic: try auto-plan first; otherwise do a single LLM plan.
                steps = try_auto_plan(description)
                if not steps:
                    plan = get_plan(description, expectation, page_text)
                    steps = plan.get("steps", [])

                for step in steps[:10]:
                    await execute_step(page, step)
                    await page.wait_for_timeout(400)

                ok = await wait_for_expected_text(page, expectation, timeout_ms=7000)
                if not ok:
                    body = await page.locator("body").inner_text()
                    ok = validate(expectation, body) == "PASS"

                result = "PASS" if ok else "FAIL"
                body_preview = norm_space(await page.locator("body").inner_text())
                print("📄 TEXT:", body_preview[:220])
                print("👉 RESULT:", result)

                if not ok:
                    screenshot_path = await take_case_screenshot(page, case_id)
            except Exception as e:
                print("⚠️ Case failed with exception:", str(e))
                screenshot_path = await take_case_screenshot(page, case_id)
                result = "FAIL"
                body_preview = ""

            results.append(
                {
                    "case_id": case_id,
                    "description": description,
                    "expectation": expectation,
                    "result": result,
                    "screenshot": screenshot_path,
                    "body_preview": body_preview,
                }
            )

        await context.close()
        await browser.close()

    with open(out_results, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    asyncio.run(run_suite())
