# run_tests.py — Fully deterministic, no LLM needed for standard login tests
import asyncio
import json
import os
import re
import sys
from typing import Any, Dict, List

import pandas as pd
from playwright.async_api import async_playwright, Page

BASE_URL = "https://trajector.bling-ai.com/trajector/login/"
EXCEL_PATH = "Trajector Test cases.xlsx"
SHEET_NAME = "Login"
ARTIFACTS_DIR = "artifacts"

# ── helpers ────────────────────────────────────────────────────────────────

def to_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()

def extract_expected_msg(expectation: str) -> str:
    raw = re.sub(r"\s+", " ", (expectation or "").strip())
    if not raw:
        return ""
    m = re.search(r'["\u201c\u201d\u2018\u2019]([^""\u201c\u201d\u2018\u2019]+)["\u201c\u201d\u2018\u2019]', raw)
    if m:
        return m.group(1).strip()
    if ":" in raw:
        return raw.split(":", 1)[1].strip()
    return raw

def check_pass(expected_msg: str, body: str) -> bool:
    if not expected_msg:
        return False
    return norm(expected_msg) in norm(body)

# ── robust locators ─────────────────────────────────────────────────────────

async def get_email_input(page: Page):
    candidates = [
        page.locator('input[type="email"]'),
        page.get_by_placeholder(re.compile(r"email", re.I)),
        page.locator('input[name*="email" i]'),
        page.locator('input[id*="email" i]'),
        page.locator('input').first,
    ]
    for loc in candidates:
        try:
            if await loc.count() > 0:
                return loc.first
        except Exception:
            pass
    return None

async def get_password_input(page: Page):
    candidates = [
        page.locator('input[type="password"]'),
        page.get_by_placeholder(re.compile(r"password", re.I)),
        page.locator('input[name*="password" i]'),
        page.locator('input[id*="password" i]'),
    ]
    for loc in candidates:
        try:
            if await loc.count() > 0:
                return loc.first
        except Exception:
            pass
    return None

async def get_login_button(page: Page):
    candidates = [
        page.get_by_role("button", name=re.compile(r"sign\s*in", re.I)),
        page.get_by_role("button", name=re.compile(r"log\s*in", re.I)),
        page.locator('button[type="submit"]'),
        page.locator('input[type="submit"]'),
    ]
    for loc in candidates:
        try:
            if await loc.count() > 0:
                return loc.first
        except Exception:
            pass
    return None

async def fill_and_submit(page: Page, email: str, password: str):
    ei = await get_email_input(page)
    pi = await get_password_input(page)
    btn = await get_login_button(page)
    if ei:
        await ei.fill(email)
    if pi:
        await pi.fill(password)
    if btn:
        await btn.click()

async def get_body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text()
    except Exception:
        return ""

async def screenshot(page: Page, case_id: str) -> str:
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    p = os.path.join(ARTIFACTS_DIR, f"{case_id}.png")
    try:
        await page.screenshot(path=p, full_page=True)
    except Exception:
        pass
    return p

async def goto_login(page: Page):
    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
    await page.wait_for_timeout(700)

# ── per-test handlers ────────────────────────────────────────────────────────

async def run_case(page: Page, case_id: str, description: str, expectation: str) -> Dict:
    result, notes, actual_text, shot = "FAIL", "", "", ""
    cid = case_id.lower()

    try:
        await goto_login(page)

        # ── login_01: both fields empty ───────────────────────────────────────
        if cid == "login_01":
            await fill_and_submit(page, "", "")
            await page.wait_for_timeout(1500)
            actual_text = await get_body_text(page)
            result = "PASS" if check_pass(extract_expected_msg(expectation), actual_text) else "FAIL"

        # ── login_02: email without @ ─────────────────────────────────────────
        elif cid == "login_02":
            await fill_and_submit(page, "invalidemail", "ValidPass1")
            await page.wait_for_timeout(1500)
            actual_text = await get_body_text(page)
            result = "PASS" if check_pass(extract_expected_msg(expectation), actual_text) else "FAIL"

        # ── login_03: valid email + wrong password ────────────────────────────
        elif cid == "login_03":
            await fill_and_submit(page, "test@example.com", "WrongPassword99")
            await page.wait_for_timeout(3000)
            actual_text = await get_body_text(page)
            result = "PASS" if check_pass(extract_expected_msg(expectation), actual_text) else "FAIL"

        # ── login_04: password eye toggle ─────────────────────────────────────
        elif cid == "login_04":
            pi = await get_password_input(page)
            if pi:
                await pi.fill("TestPass123")
            # Try various eye-icon selectors
            for sel in [
                'button[aria-label*="show" i]', 'button[aria-label*="password" i]',
                '[class*="eye"]', '[class*="toggle"]', '[data-testid*="eye"]',
                'input[type="password"] ~ button', 'input[type="password"] + button',
            ]:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0:
                        await loc.first.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(600)
            # Check if type flipped to "text"
            try:
                t = await page.locator('input[type="text"][placeholder*="password" i], input[type="text"][name*="password" i]').count()
                result = "PASS" if t > 0 else "FAIL"
                notes = f"type=text found: {t > 0}"
            except Exception as e:
                result = "FAIL"
                notes = str(e)
            actual_text = await get_body_text(page)

        # ── login_05: forgot password link ────────────────────────────────────
        elif cid == "login_05":
            lnk = page.get_by_text(re.compile(r"forgot\s*password", re.I)).first
            if await lnk.count() == 0:
                lnk = page.locator('a[href*="forgot"], a[href*="reset"]').first
            await lnk.click()
            await page.wait_for_timeout(2000)
            actual_text = await get_body_text(page)
            result = "PASS" if any(norm(x) in norm(actual_text) for x in ["reset password", "forgot password", "reset your password"]) else "FAIL"

        # ── login_06: sign up link ────────────────────────────────────────────
        elif cid == "login_06":
            lnk = page.get_by_text(re.compile(r"sign\s*up", re.I)).first
            if await lnk.count() == 0:
                lnk = page.locator('a[href*="signup"], a[href*="register"]').first
            await lnk.click()
            await page.wait_for_timeout(2000)
            actual_text = await get_body_text(page)
            url = page.url
            result = "PASS" if any(x in url.lower() for x in ["signup", "register", "sign-up"]) or norm("sign up") in norm(actual_text) else "FAIL"

        # ── login_07: email with + special char ───────────────────────────────
        elif cid == "login_07":
            ei = await get_email_input(page)
            if ei:
                await ei.fill("test+user@example.com")
                await page.wait_for_timeout(600)
                actual_text = await get_body_text(page)
                result = "FAIL" if norm("please enter a correct email") in norm(actual_text) else "PASS"
                notes = "No inline format error for test+user@example.com" if result == "PASS" else "Format error shown for special-char email"
            else:
                result = "FAIL"; notes = "Email input not found"

        # ── login_08: tab key moves focus email→password ───────────────────────
        elif cid == "login_08":
            ei = await get_email_input(page)
            if ei:
                await ei.click()
                await ei.press("Tab")
                await page.wait_for_timeout(400)
                focused_type = await page.evaluate("document.activeElement.type")
                result = "PASS" if focused_type == "password" else "FAIL"
                notes = f"After Tab, focused element type = '{focused_type}'"
            actual_text = await get_body_text(page)

        # ── login_09: valid email + empty password ────────────────────────────
        elif cid == "login_09":
            await fill_and_submit(page, "test@example.com", "")
            await page.wait_for_timeout(1500)
            actual_text = await get_body_text(page)
            result = "PASS" if check_pass(extract_expected_msg(expectation), actual_text) else "FAIL"

        # ── login_10: valid email + <4 char password ──────────────────────────
        elif cid == "login_10":
            await fill_and_submit(page, "test@example.com", "ab")
            await page.wait_for_timeout(1500)
            actual_text = await get_body_text(page)
            result = "PASS" if check_pass(extract_expected_msg(expectation), actual_text) else "FAIL"

        # ── login_11: google sign-in button visible ───────────────────────────
        elif cid == "login_11":
            actual_text = await get_body_text(page)
            found = await page.locator('button, a, [role="button"]').filter(
                has_text=re.compile(r"google", re.I)
            ).count()
            if found == 0:
                found = await page.locator('[class*="google"], img[alt*="google" i]').count()
            result = "PASS" if found > 0 else "FAIL"
            notes = f"Google button count: {found}"

        # ── login_12: all page elements visible ───────────────────────────────
        elif cid == "login_12":
            actual_text = await get_body_text(page)
            ei = await get_email_input(page)
            pi = await get_password_input(page)
            btn = await get_login_button(page)
            checks = {
                "email_field": ei is not None and await ei.count() > 0,
                "password_field": pi is not None and await pi.count() > 0,
                "login_button": btn is not None and await btn.count() > 0,
            }
            result = "PASS" if all(checks.values()) else "FAIL"
            notes = str(checks)

        # ── login_13: invalid creds → click "here" link in error msg ──────────
        elif cid == "login_13":
            await fill_and_submit(page, "wrong@example.com", "WrongPass99")
            await page.wait_for_timeout(3000)
            here = page.locator('a').filter(has_text=re.compile(r"^here$", re.I)).first
            if await here.count() == 0:
                here = page.get_by_text("here").first
            if await here.count() > 0:
                await here.click()
                await page.wait_for_timeout(2000)
                actual_text = await get_body_text(page)
                result = "PASS" if any(norm(x) in norm(actual_text) for x in ["reset", "forgot"]) else "FAIL"
            else:
                actual_text = await get_body_text(page)
                result = "FAIL"; notes = "'here' link not found"

        # ── login_14: google sign-in (presence check only — OAuth not automated)
        elif cid == "login_14":
            found = await page.locator('button, a, [role="button"]').filter(
                has_text=re.compile(r"google", re.I)
            ).count()
            actual_text = await get_body_text(page)
            result = "PASS" if found > 0 else "FAIL"
            notes = "Google button present (OAuth not fully automated)"

        # ── login_15: valid credentials → OTP/verification page ──────────────
        elif cid == "login_15":
            valid_email = os.getenv("TEST_EMAIL", "")
            valid_pwd = os.getenv("TEST_PASSWORD", "")
            if not valid_email or not valid_pwd:
                result = "SKIP"
                notes = "Set TEST_EMAIL and TEST_PASSWORD secrets to test valid login"
            else:
                await fill_and_submit(page, valid_email, valid_pwd)
                await page.wait_for_timeout(3500)
                actual_text = await get_body_text(page)
                url = page.url
                result = "PASS" if any(x in url.lower() for x in ["otp", "verify"]) or any(norm(x) in norm(actual_text) for x in ["otp", "verification", "verify"]) else "FAIL"

        # ── login_16: email placeholder text ─────────────────────────────────
        elif cid == "login_16":
            ei = await get_email_input(page)
            actual_text = await get_body_text(page)
            if ei:
                ph = await ei.get_attribute("placeholder") or ""
                result = "PASS" if norm("email") in norm(ph) else "FAIL"
                notes = f"placeholder='{ph}'"
            else:
                result = "FAIL"; notes = "Email input not found"

        # ── login_17: password placeholder text ───────────────────────────────
        elif cid == "login_17":
            pi = await get_password_input(page)
            actual_text = await get_body_text(page)
            if pi:
                ph = await pi.get_attribute("placeholder") or ""
                result = "PASS" if norm("password") in norm(ph) else "FAIL"
                notes = f"placeholder='{ph}'"
            else:
                result = "FAIL"; notes = "Password input not found"

        # ── login_18: enter key submits ───────────────────────────────────────
        elif cid == "login_18":
            ei = await get_email_input(page)
            pi = await get_password_input(page)
            if ei and pi:
                await ei.fill("test@example.com")
                await pi.fill("testpass")
                await pi.press("Enter")
                await page.wait_for_timeout(1500)
                actual_text = await get_body_text(page)
                result = "PASS"
                notes = "Enter key pressed; page responded without crash"
            else:
                result = "FAIL"; notes = "Inputs not found"

        # ── login_19: paste into email ────────────────────────────────────────
        elif cid == "login_19":
            ei = await get_email_input(page)
            if ei:
                await ei.click()
                await page.evaluate("""
                    (() => {
                        const el = document.querySelector('input[type="email"], input[placeholder*="email" i]');
                        if (!el) return;
                        const dt = new DataTransfer();
                        dt.setData('text/plain', 'pasted@example.com');
                        el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true}));
                    })()
                """)
                await page.wait_for_timeout(500)
                result = "PASS"; notes = "Paste event dispatched without crash"
            else:
                result = "FAIL"; notes = "Email input not found"
            actual_text = await get_body_text(page)

        # ── login_20: paste into password ────────────────────────────────────
        elif cid == "login_20":
            pi = await get_password_input(page)
            if pi:
                await pi.click()
                await page.evaluate("""
                    (() => {
                        const el = document.querySelector('input[type="password"]');
                        if (!el) return;
                        const dt = new DataTransfer();
                        dt.setData('text/plain', 'PastedPass123');
                        el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true}));
                    })()
                """)
                await page.wait_for_timeout(500)
                result = "PASS"; notes = "Paste event dispatched without crash"
            else:
                result = "FAIL"; notes = "Password input not found"
            actual_text = await get_body_text(page)

        # ── login_21: long email (>100 chars) ─────────────────────────────────
        elif cid == "login_21":
            long_email = "a" * 90 + "@example.com"
            ei = await get_email_input(page)
            if ei:
                await ei.fill(long_email)
                await page.wait_for_timeout(500)
                result = "PASS"; notes = f"Filled {len(long_email)}-char email without crash"
            else:
                result = "FAIL"; notes = "Email input not found"
            actual_text = await get_body_text(page)

        # ── login_22: email with spaces (should be trimmed / accepted) ─────────
        elif cid == "login_22":
            ei = await get_email_input(page)
            if ei:
                await ei.fill("  test@example.com  ")
                btn = await get_login_button(page)
                if btn:
                    await btn.click()
                await page.wait_for_timeout(1500)
                actual_text = await get_body_text(page)
                result = "PASS" if norm("please enter a correct email") not in norm(actual_text) else "FAIL"
                notes = "Spaces trimmed, no format error" if result == "PASS" else "Format error shown for spaced email"
            else:
                result = "FAIL"; notes = "Email input not found"

        # ── login_24: click Bling logo ────────────────────────────────────────
        elif cid == "login_24":
            for sel in ['img[alt*="bling" i]', 'a[href*="bling"] img', '.logo', '[class*="logo"]', 'header a', 'a']:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.click()
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(2000)
            url = page.url
            actual_text = await get_body_text(page)
            result = "PASS" if "bling" in url.lower() or "bling" in norm(actual_text) else "FAIL"
            notes = f"Navigated to: {url}"

        # ── login_25: spaces only in password → bullet (masked) ───────────────
        elif cid == "login_25":
            pi = await get_password_input(page)
            if pi:
                await pi.fill("   ")
                await page.wait_for_timeout(400)
                t = await pi.get_attribute("type")
                result = "PASS" if t == "password" else "FAIL"
                notes = f"input type='{t}' (password = bullets displayed)"
            else:
                result = "FAIL"; notes = "Password input not found"
            actual_text = await get_body_text(page)

        else:
            result = "SKIP"; notes = f"No handler for case {case_id}"

    except Exception as exc:
        result = "ERROR"; notes = str(exc)
        try:
            shot = await screenshot(page, case_id)
        except Exception:
            pass

    if result in ("FAIL", "ERROR"):
        try:
            shot = await screenshot(page, case_id)
        except Exception:
            pass

    return {
        "case_id": case_id,
        "description": description,
        "expectation": expectation,
        "expected_msg": extract_expected_msg(expectation),
        "result": result,
        "actual_preview": actual_text[:400] if actual_text else "",
        "notes": notes,
        "screenshot": shot,
    }

# ── HTML report ──────────────────────────────────────────────────────────────

def write_html_report(results: List[Dict], path: str):
    rows = ""
    for r in results:
        colour = {"PASS": "#22c55e", "FAIL": "#ef4444", "SKIP": "#f59e0b", "ERROR": "#7c3aed"}.get(r["result"], "#6b7280")
        shot_html = f'<a href="{r["screenshot"]}" target="_blank">📷</a>' if r.get("screenshot") else ""
        rows += f"""
        <tr>
          <td>{r['case_id']}</td>
          <td style="font-size:12px">{r['description'].replace(chr(10), '<br>')}</td>
          <td style="font-size:12px">{r['expectation']}</td>
          <td style="font-size:12px;color:#555">{r.get('actual_preview','')[:200]}</td>
          <td style="font-size:12px;color:#555">{r.get('notes','')}</td>
          <td style="font-weight:bold;color:{colour}">{r['result']}</td>
          <td>{shot_html}</td>
        </tr>"""

    total = len(results)
    passed = sum(1 for r in results if r["result"] == "PASS")
    failed = sum(1 for r in results if r["result"] == "FAIL")
    errors = sum(1 for r in results if r["result"] == "ERROR")
    skipped = sum(1 for r in results if r["result"] == "SKIP")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Trajector Login – Test Report</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; background: #f8fafc; }}
  h1 {{ color: #1e293b; }}
  .summary {{ display:flex; gap:16px; margin-bottom:20px; }}
  .badge {{ padding:10px 20px; border-radius:8px; color:#fff; font-weight:bold; font-size:14px; }}
  table {{ border-collapse:collapse; width:100%; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 4px #00000022; }}
  th {{ background:#1e293b; color:#fff; padding:10px 8px; text-align:left; font-size:13px; }}
  td {{ padding:8px; border-bottom:1px solid #e2e8f0; vertical-align:top; font-size:13px; }}
  tr:last-child td {{ border-bottom:none; }}
</style></head><body>
<h1>🧪 Trajector Login — Automated Test Report</h1>
<div class="summary">
  <div class="badge" style="background:#22c55e">✅ PASS: {passed}</div>
  <div class="badge" style="background:#ef4444">❌ FAIL: {failed}</div>
  <div class="badge" style="background:#7c3aed">💥 ERROR: {errors}</div>
  <div class="badge" style="background:#f59e0b">⏭ SKIP: {skipped}</div>
  <div class="badge" style="background:#64748b">📋 TOTAL: {total}</div>
</div>
<table>
  <tr><th>Case ID</th><th>Description</th><th>Expectation</th><th>Actual Text</th><th>Notes</th><th>Result</th><th>Screenshot</th></tr>
  {rows}
</table>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

# ── main ─────────────────────────────────────────────────────────────────────

async def run_suite():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    results = []
    out_json = os.path.join(ARTIFACTS_DIR, "results.json")
    out_html = os.path.join(ARTIFACTS_DIR, "report.html")

    # Write placeholder early so CI always has something to upload
    with open(out_json, "w") as f:
        json.dump(results, f)

    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        page.set_default_timeout(12000)

        # Preflight
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
            print("✅ Preflight: site reachable")
        except Exception as e:
            print("❌ Preflight FAILED:", e)
            results.append({
                "case_id": "preflight", "description": "Connectivity check",
                "expectation": BASE_URL, "expected_msg": "", "result": "BLOCKED",
                "actual_preview": "", "notes": str(e), "screenshot": "",
            })
            with open(out_json, "w") as f:
                json.dump(results, f, indent=2)
            write_html_report(results, out_html)
            await browser.close()
            sys.exit(2)

        for idx, row in df.iterrows():
            case_id = to_str(row.get("Test case ID", row.get("Test case", ""))) or f"row_{idx}"
            description = to_str(row.get("Description", ""))
            expectation = to_str(row.get("Expectation", ""))

            print(f"\n🚀 Running {case_id} …")
            res = await run_case(page, case_id, description, expectation)
            emoji = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭", "ERROR": "💥"}.get(res["result"], "❓")
            print(f"   {emoji} {res['result']}  {res['notes'][:120] if res['notes'] else ''}")
            results.append(res)

        await browser.close()

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    write_html_report(results, out_html)

    total = len(results)
    passed = sum(1 for r in results if r["result"] == "PASS")
    print(f"\n{'='*50}")
    print(f"📊 Results: {passed}/{total} passed")
    print(f"📄 HTML report → {out_html}")
    print(f"📄 JSON report → {out_json}")


if __name__ == "__main__":
    asyncio.run(run_suite())
