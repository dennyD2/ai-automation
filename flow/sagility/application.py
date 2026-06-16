# monitor_sagility.py — Sagility Production Flow Monitor
# No Excel needed. Follows the flow document step-by-step.
# Sends Discord alert immediately on any failure.
# Two isolated browser contexts: Context 1 = Gmail OTP, Context 2 = Candidate Portal

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional
from core.step_result import StepResult
from services.screenshot_service import screenshot
from flow.sagility.prescreening import run_prescreening
from flow.sagility.assessment import run_assessment


import urllib.request
import requests

from playwright.async_api import async_playwright, Page

# ── Configuration ─────────────────────────────────────────────────────────────

PORTAL_URL = os.getenv("PORTAL_URL")
HEADLESS = (
    os.getenv(
        "HEADLESS",
        "true"
    ).lower() == "true"
)
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
ARTIFACTS_DIR = "artifacts"

# Candidate test data (from flow document)
CANDIDATE_NAME  = "John Thomas"
CANDIDATE_PHONE = "+13479345919"
CANDIDATE_PIN   = "90001"

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(__file__)
    )
)

RESUME_PATH = os.path.join(
    BASE_DIR,
    "test_data",
    "resumes",
    "Resume_IST.pdf"
)

# Timeouts (from flow document)
TIMEOUT_WEBSITE   = 15_000   # ms
TIMEOUT_BOT       = 30_000   # ms
TIMEOUT_NAV       = 10_000   # ms
TIMEOUT_UPLOAD    = 15_000   # ms
TIMEOUT_VIDEO     = 10_000   # ms

# GitHub Actions run URL (auto-built from env vars)
def _ci_run_url() -> str:
    srv = os.getenv("GITHUB_SERVER_URL", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if srv and repo and run_id:
        return f"{srv}/{repo}/actions/runs/{run_id}"
    return ""

RUN_URL = _ci_run_url()


# ── Helpers ───────────────────────────────────────────────────────────────────

os.makedirs(ARTIFACTS_DIR, exist_ok=True)

def ts_email() -> str:
    return f"bling2cloud+{datetime.utcnow().strftime('%d%H%M%S')}@gmail.com"

async def wait_for_bot_text(page: Page, keywords: list[str], timeout_ms: int = TIMEOUT_BOT) -> bool:
    """Wait until any of the keywords appear in the chat section."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            body = await page.evaluate("() => document.body.innerText")
            if any(kw.lower() in body.lower() for kw in keywords):
                return True
        except Exception:
            pass
        await page.wait_for_timeout(500)
    return False

async def detect_blank_or_spinner(page: Page) -> Optional[str]:
    """Returns failure tag string if blank page or spinner detected, else None."""
    try:
        result = await page.evaluate("""() => {
            const blank = document.body.innerText.trim().length < 30;
            const spinners = Array.from(document.querySelectorAll(
                '[class*="spinner" i],[class*="loader" i],[class*="loading" i],[aria-label*="loading" i]'
            )).filter(e => e.offsetParent !== null).length;
            return { blank, spinners };
        }""")
        if result["blank"]:
            return "[BLANK_PAGE]"
        if result["spinners"] > 0:
            return "[INFINITE_LOADER]"
    except Exception:
        pass
    return None

# ── Discord alert ─────────────────────────────────────────────────────────────

SEVERITY = {
    "[BLANK_PAGE]":       ("🌑 Blank Page",       "critical"),
    "[INFINITE_LOADER]":  ("⏳ Infinite Loader",   "critical"),
    "[BOT_NO_RESPONSE]":  ("🤖 Bot No Response",   "critical"),
    "[NAV_BROKEN]":       ("🔗 Nav Broken",         "critical"),
    "[API_ERROR]":        ("🔌 API Error",          "critical"),
    "[OTP_FAILURE]":      ("📧 OTP Failure",        "critical"),
    "[GMAIL_FAILURE]":    ("📬 Gmail Failure",      "critical"),
    "[UPLOAD_FAILURE]":   ("📎 Upload Failure",     "high"),
    "[VIDEO_MISSING]":    ("🎬 Video Missing",      "medium"),
    "[ELEMENT_MISSING]":  ("🔍 Element Missing",    "high"),
    "[TIMEOUT]":          ("⏱ Timeout",            "high"),
    "[DUPLICATE_EMAIL]":  ("📛 Duplicate Candidate","critical"),
    "[GLOBAL_FAILURE]":   ("💥 Global Failure",     "critical"),
}

def _discord_color(tag: str) -> int:
    severity = SEVERITY.get(tag, ("", "high"))[1]
    return {"critical": 15158332, "high": 16744272, "medium": 16776960}.get(severity, 15158332)

async def send_discord_alert(step: StepResult, candidate_email: str = ""):
    # ── DEBUG: Webhook validation ──────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"🔔 [DISCORD DEBUG] send_discord_alert called")
    print(f"   step_id     : {step.step_id}")
    print(f"   step.name   : {step.name}")
    print(f"   step.status : {step.status}")
    print(f"   step.tag    : {step.tag}")
    print(f"   step.reason : {step.reason}")
    print(f"   step.screenshot : {step.screenshot}")
    print(f"   candidate_email : {candidate_email}")

    if not DISCORD_WEBHOOK:
        print(f"  ❌ [DISCORD DEBUG] DISCORD_WEBHOOK env var is NOT SET — cannot send alert for {step.step_id}")
        print(f"{'─'*50}\n")
        return

    # Mask webhook for safe logging (show first 60 chars only)
    masked_hook = DISCORD_WEBHOOK[:60] + "..." if len(DISCORD_WEBHOOK) > 60 else DISCORD_WEBHOOK
    print(f"   webhook     : {masked_hook}")

    # Basic format sanity check
    if not DISCORD_WEBHOOK.startswith("https://discord.com/api/webhooks/"):
        print(f"  ⚠️  [DISCORD DEBUG] Webhook URL looks malformed! Expected 'https://discord.com/api/webhooks/...'")

    # ── Build embed ────────────────────────────────────────────────────────────
    is_success = step.status == "PASS" or step.step_id == "SUCCESS"
    label = SEVERITY.get(step.tag, (step.tag, "high"))[0] if step.tag else "Unknown"
    ts_human = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    fields = [
        {"name": "Step", "value": f"`{step.step_id}` — {step.name}", "inline": False},
        {"name": "Status", "value": step.status, "inline": True},
        {"name": "Timestamp", "value": ts_human, "inline": True},
    ]

    if step.tag:
        fields.append({"name": "Failure type", "value": label or step.tag, "inline": True})
    if step.reason:
        fields.append({"name": "Reason", "value": step.reason[:300] or "—", "inline": False})
    if candidate_email:
        fields.append({"name": "Candidate email", "value": candidate_email, "inline": False})
    if RUN_URL:
        fields.append({"name": "CI Run", "value": RUN_URL, "inline": False})
    if step.screenshot:
        fields.append({"name": "Screenshot", "value": f"`{step.screenshot}`", "inline": False})

    # ── Screenshot attachment (must be set BEFORE serializing payload_json) ──
    screenshot_file = None
    attach_filename = None

    print(f"🔹 [DISCORD DEBUG] step.screenshot = {step.screenshot!r}")

    if step.screenshot:
        if os.path.exists(step.screenshot):
            attach_filename = os.path.basename(step.screenshot)
            file_size = os.path.getsize(step.screenshot)
            print(f"🔹 [DISCORD DEBUG] Screenshot file found: {step.screenshot} ({file_size} bytes)")
        else:
            print(f"  ⚠️  [DISCORD DEBUG] Screenshot path set but FILE NOT FOUND: {step.screenshot}")
    else:
        print(f"  ℹ️  [DISCORD DEBUG] No screenshot to attach")

    embed = {
        "title": (
            "✅ Sagility Monitor — SUCCESS"
            if is_success
            else f"🚨 Sagility Monitor — {step.step_id} FAILED"
        ),
        "description": (
            "Production monitoring completed successfully."
            if is_success
            else f"**{label or step.tag}** detected during production flow monitoring."
        ),
        "color": 5763719 if is_success else _discord_color(step.tag),
        "fields": fields,
        "footer": {"text": f"Portal: {PORTAL_URL}"},
    }

    # BUG FIX: embed["image"] must be set BEFORE json.dumps(payload)
    if attach_filename:
        embed["image"] = {"url": f"attachment://{attach_filename}"}
        print(f"🔹 [DISCORD DEBUG] embed['image'] set to attachment://{attach_filename}")

    payload = {"embeds": [embed]}
    payload_json_str = json.dumps(payload)
    print(f"🔹 [DISCORD DEBUG] payload_json length = {len(payload_json_str)} chars")

    # ── Send via requests in executor (non-blocking, no extra dependencies) ──
    def _do_post():
        """Runs in a thread via run_in_executor so it doesn't block the event loop."""
        if attach_filename:
            with open(step.screenshot, "rb") as f:
                files_payload = {
                    "payload_json": (None, payload_json_str, "application/json"),
                    "file": (attach_filename, f, "image/png"),
                }
                print(f"🔹 [DISCORD DEBUG] Sending multipart POST (with screenshot) to Discord...")
                return requests.post(DISCORD_WEBHOOK, files=files_payload, timeout=20)
        else:
            print(f"🔹 [DISCORD DEBUG] Sending JSON POST (no screenshot) to Discord...")
            return requests.post(
                DISCORD_WEBHOOK,
                data=payload_json_str,
                headers={"Content-Type": "application/json"},
                timeout=20,
            )

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _do_post)

        print(f"🔹 [DISCORD DEBUG] HTTP response status : {response.status_code}")
        print(f"🔹 [DISCORD DEBUG] HTTP response body   : {response.text[:500]}")

        if response.status_code in (200, 204):
            print(f"✅ [DISCORD DEBUG] Alert delivered successfully for {step.step_id}")
        elif response.status_code == 429:
            retry_after = response.json().get("retry_after", "?")
            print(f"  ⚠️  [DISCORD DEBUG] Rate-limited by Discord! retry_after={retry_after}s")
        elif response.status_code == 401:
            print(f"  ❌ [DISCORD DEBUG] 401 Unauthorized — webhook token is invalid or revoked")
        elif response.status_code == 404:
            print(f"  ❌ [DISCORD DEBUG] 404 Not Found — webhook URL is deleted or wrong")
        else:
            print(f"  ⚠️  [DISCORD DEBUG] Unexpected status {response.status_code}: {response.text[:300]}")

    except requests.Timeout:
        print(f"  ❌ [DISCORD DEBUG] Request timed out after 20s")
    except requests.ConnectionError as e:
        print(f"  ❌ [DISCORD DEBUG] Connection error (network/DNS issue?): {e}")
    except Exception as e:
        print(f"  ❌ [DISCORD DEBUG] Unexpected error during Discord send: {type(e).__name__}: {e}")

    print(f"{'─'*50}\n")

# ── HTML report ───────────────────────────────────────────────────────────────

def write_report(results: list[StepResult], candidate_email: str, duration_s: float):
    passed  = sum(1 for r in results if r.status == "PASS")
    failed  = sum(1 for r in results if r.status == "FAIL")
    overall = "✅ PASSED" if failed == 0 else "❌ FAILED"
    color   = "#22c55e" if failed == 0 else "#ef4444"

    rows = ""
    for r in results:
        sc = f'<a href="../{r.screenshot}" target="_blank">📷</a>' if r.screenshot else ""
        sc_bg = {"PASS": "#f0fdf4", "FAIL": "#fef2f2", "SKIP": "#fffbeb"}.get(r.status, "#fff")
        tag_html = f'<span style="background:#fef2f2;color:#b91c1c;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:600">{r.tag}</span> ' if r.tag else ""
        rows += f"""<tr style="background:{sc_bg}">
          <td style="white-space:nowrap;font-family:monospace;font-size:12px">{r.step_id}</td>
          <td style="font-size:13px">{r.name}</td>
          <td style="font-size:12px">{tag_html}{r.reason or "—"}</td>
          <td style="font-size:11px;color:#64748b">{r.duration:.1f}s</td>
          <td style="font-weight:700;color:{"#22c55e" if r.status=="PASS" else "#ef4444"};font-size:16px;text-align:center">{r.status}</td>
          <td style="text-align:center">{sc}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Sagility Monitor Report</title>
<style>
  body{{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#1e293b}}
  .header{{display:flex;align-items:center;gap:16px;margin-bottom:20px}}
  .overall{{font-size:24px;font-weight:700;color:{color}}}
  .meta{{color:#64748b;font-size:13px}}
  .summary{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}}
  .badge{{padding:8px 16px;border-radius:8px;color:#fff;font-weight:600;font-size:13px}}
  table{{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 6px #00000015}}
  th{{background:#1e293b;color:#fff;padding:10px 8px;font-size:12px;text-align:left}}
  td{{padding:8px;border-bottom:1px solid #e2e8f0;vertical-align:middle;font-size:13px}}
</style></head><body>
<div class="header">
  <div>
    <div class="overall">{overall}</div>
    <div class="meta">Sagility Candidate Portal — Production Monitor</div>
    <div class="meta">Run at {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")} &nbsp;|&nbsp; Duration: {duration_s:.1f}s &nbsp;|&nbsp; Candidate: {candidate_email}</div>
    {f'<div class="meta"><a href="{RUN_URL}">GitHub Actions Run →</a></div>' if RUN_URL else ""}
  </div>
</div>
<div class="summary">
  <div class="badge" style="background:#22c55e">✅ PASS: {passed}</div>
  <div class="badge" style="background:#ef4444">❌ FAIL: {failed}</div>
  <div class="badge" style="background:#64748b">📋 TOTAL: {len(results)}</div>
</div>
<table>
  <tr><th>Step ID</th><th>Name</th><th>Reason / Tag</th><th>Duration</th><th>Status</th><th>📷</th></tr>
  {rows}
</table></body></html>"""

    path = os.path.join(ARTIFACTS_DIR, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path

# ── STAGE 1 — Portal Launch ────────────────────────────────────────────────────

async def stage1_portal_launch(page: Page, candidate_email: str) -> StepResult:
    step = StepResult("STEP_01", "Portal Launch — open candidate portal")
    t0 = time.time()
    try:
        await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=TIMEOUT_WEBSITE)
        await page.wait_for_timeout(5000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)
        # check blank / infinite loader
        health = await detect_blank_or_spinner(page)
        if health:
            step.fail(health, f"Portal loaded but {health} detected immediately")
            step.screenshot = await screenshot(page, "STEP_01_fail")
            step.duration = time.time() - t0
            return step

        # Validate expected elements
        body = await page.evaluate("() => document.body.innerText")
        checks = {
            "Start My Application button": "start my application",
        }
        missing = [name for name, kw in checks.items() if kw.lower() not in body.lower()]
        if missing:
            step.fail("[ELEMENT_MISSING]", f"Missing on portal load: {', '.join(missing)}")
            step.screenshot = await screenshot(page, "STEP_01_fail")
        else:
            print("      ✅  Portal loaded — Start My Application visible")

    except Exception as e:
        tag = "[TIMEOUT]" if "timeout" in str(e).lower() else "[BLANK_PAGE]"
        step.fail(tag, str(e)[:300])
        step.screenshot = await screenshot(page, "STEP_01_fail")

    step.duration = time.time() - t0
    return step

# ── STAGE 2 — Consent ─────────────────────────────────────────────────────────

async def stage2_consent(page: Page, candidate_email: str) -> list[StepResult]:
    results = []

    # Step 2 — tick consent checkbox
    step2 = StepResult("STEP_02", "Consent — tick consent checkbox")
    t0 = time.time()
    try:
        checkbox_locs = [
            page.locator('input[type="checkbox"]').first,
            page.get_by_role("checkbox").first,
            page.locator('[class*="consent" i] input').first,
        ]
        clicked = False
        for loc in checkbox_locs:
            try:
                if await loc.count() > 0:
                    await loc.check(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            step2.fail("[ELEMENT_MISSING]", "Consent checkbox not found or not clickable")
            step2.screenshot = await screenshot(page, "STEP_02_fail")
        else:
            print("      ✅  Consent checkbox ticked")
    except Exception as e:
        step2.fail("[ELEMENT_MISSING]", str(e)[:200])
        step2.screenshot = await screenshot(page, "STEP_02_fail")
    step2.duration = time.time() - t0
    results.append(step2)

    if step2.status == "FAIL":
        return results

    # Step 3 — click Start My Application
    step3 = StepResult("STEP_03", "Consent — click Start My Application")
    t0 = time.time()
    try:
        btn_locs = [
            page.get_by_role("button", name=re.compile("start my application", re.I)),
            page.get_by_text(re.compile("start my application", re.I)),
            page.locator('button:has-text("Start")'),
        ]
        clicked = False
        for loc in btn_locs:
            try:
                if await loc.count() > 0:
                    await loc.first.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            step3.fail("[ELEMENT_MISSING]", '"Start My Application" button not found or disabled')
            step3.screenshot = await screenshot(page, "STEP_03_fail")
        else:
            # Wait for bot to ask for email
            appeared = await wait_for_bot_text(page, ["email", "enter your email", "please provide"], TIMEOUT_BOT)
            if not appeared:
                step3.fail(
                    "[BOT_NO_RESPONSE]",
                    "Bot did not ask for email after clicking Start My Application"
                )
                step3.screenshot = await screenshot(page, "STEP_03_fail")
            else:
                print("      ✅  Bot requested email")
    except Exception as e:
        step3.fail("[NAV_BROKEN]", str(e)[:200])
        step3.screenshot = await screenshot(page, "STEP_03_fail")
    step3.duration = time.time() - t0
    results.append(step3)

    return results

# ── STAGE 3 — Email Submission ────────────────────────────────────────────────

async def stage3_email(page: Page, candidate_email: str) -> StepResult:
    step = StepResult("STEP_05", "Email Verification — submit candidate email")
    t0 = time.time()
    try:
        # Find chat input and type email
        input_locs = [
            page.get_by_placeholder(re.compile("type|message|email", re.I)),
            page.locator('[class*="chat" i] input[type="text"]').first,
            page.locator('[class*="input" i] input').first,
            page.locator('input[type="text"]:visible').first,
            page.locator('textarea:visible').first,
        ]
        filled = False
        for loc in input_locs:
            try:
                if await loc.count() > 0:
                    await loc.first.fill(candidate_email)
                    await loc.first.press("Enter")
                    await page.wait_for_timeout(5000)
                    body = await page.evaluate("() => document.body.innerText")
                    #print("\n===== PAGE AFTER EMAIL SUBMISSION =====")
                    #print(body[:3000])
                    print("=======================================\n")
                    filled = True
                    break
            except Exception:
                continue

        if not filled:
            step.fail("[ELEMENT_MISSING]", "Chat input field not found to submit email")
            step.screenshot = await screenshot(page, "STEP_05_fail")
        else:
            # Wait for OTP request
            appeared = await wait_for_bot_text(
                page,
                ["otp", "verification code", "code sent", "check your email", "verify"],
                TIMEOUT_BOT
            )
        if not appeared:
            body = await page.evaluate("() => document.body.innerText")
        
            #print("\n===== AFTER EMAIL SUBMISSION =====")
            #print(body[:4000])
            #print("=================================\n")
            print("      ⚠️  Bot did not explicitly ask for email")
            print("      ⚠️  Continuing anyway")
        
        else:
            print("      ✅  Bot sent OTP request")
    except Exception as e:
        step.fail("[API_ERROR]", str(e)[:200])
        step.screenshot = await screenshot(page, "STEP_05_fail")
    step.duration = time.time() - t0
    return step
    
# ── STAGE 4 — Static OTP ─────────────────────────────────────────────────────

async def stage4_static_otp(page: Page, candidate_email: str) -> tuple[StepResult, str]:

    step = StepResult("STEP_06", "OTP Verification — use static OTP")
    t0 = time.time()

    otp = "123456"

    try:

        print(f"      ✅  Using static OTP: {otp}")

        body = await page.evaluate("() => document.body.innerText")

        #print("\n===== BEFORE OTP SUBMISSION =====")
        #print(body[:3000])
        #print("=================================\n")

        step.status = "PASS"

    except Exception as e:

        step.fail(
            "[OTP_FAILURE]",
            f"Static OTP generation failed: {str(e)[:200]}"
        )

        step.screenshot = await screenshot(
            page,
            "STEP_06_fail"
        )

    step.duration = time.time() - t0

    return step, otp


# ── STAGE 4 (cont.) — Submit OTP ─────────────────────────────────────────────

async def stage4_submit_otp(page: Page, otp: str, candidate_email: str) -> StepResult:
    step = StepResult("STEP_09", "Email Verification — submit OTP in portal")
    t0 = time.time()
    try:
        input_locs = [
            page.get_by_placeholder(re.compile("otp|code|enter code", re.I)),
            page.locator('input[type="number"]:visible').first,
            page.locator('input[maxlength="6"]:visible').first,
            page.locator('input[maxlength="4"]:visible').first,
            page.get_by_placeholder(re.compile("type|message", re.I)).first,
            page.locator('input[type="text"]:visible').first,
        ]
        filled = False
        for loc in input_locs:
            try:
                if await loc.count() > 0:
                    await loc.first.fill(otp)
                    await loc.first.press("Enter")
                    filled = True
                    break
            except Exception:
                continue

        if not filled:
            step.fail("[ELEMENT_MISSING]", "OTP input field not found in portal")
            step.screenshot = await screenshot(page, "STEP_09_fail")
        else:
            appeared = await wait_for_bot_text(
                page,
                ["verified", "name", "full name", "what is your name", "your name"],
                TIMEOUT_BOT
            )
            if not appeared:
                health = await detect_blank_or_spinner(page)
                step.fail(
                    health or "[BOT_NO_RESPONSE]",
                    "Bot did not confirm OTP verification or ask for name"
                )
                step.screenshot = await screenshot(page, "STEP_09_fail")
            else:
                print("      ✅  OTP verified — bot asking for name")
    except Exception as e:
        step.fail("[API_ERROR]", str(e)[:200])
        step.screenshot = await screenshot(page, "STEP_09_fail")
    step.duration = time.time() - t0
    return step

# ── STAGE 5 — Candidate Information ──────────────────────────────────────────

async def _send_chat_message(page: Page, message: str) -> bool:
    """Type and send a message in the chat input. Returns True on success."""
    locs = [
        page.get_by_placeholder(re.compile("type|message", re.I)),
        page.locator('[class*="chat" i] input[type="text"]').first,
        page.locator('input[type="text"]:visible').first,
        page.locator('textarea:visible').first,
    ]
    for loc in locs:
        try:
            if await loc.count() > 0:
                await loc.first.fill(message)
                await loc.first.press("Enter")
                return True
        except Exception:
            continue
    return False

async def stage5_candidate_info(page: Page, candidate_email: str) -> list[StepResult]:
    results = []

    steps_data = [
        ("STEP_10", "Candidate Info — enter full name",   CANDIDATE_NAME,  ["phone", "mobile", "number"],          "[BOT_NO_RESPONSE]"),
        ("STEP_11", "Candidate Info — enter phone number",CANDIDATE_PHONE, ["pin", "pincode", "postal", "zip"],     "[BOT_NO_RESPONSE]"),
        ("STEP_12", "Candidate Info — enter pincode",     CANDIDATE_PIN,   ["age", "18", "confirm", "years old"],   "[BOT_NO_RESPONSE]"),
        ("STEP_13", "Candidate Info — confirm age (Yes)", "Yes",           ["question", "company", "anything else", "do you have"], "[BOT_NO_RESPONSE]"),
        ("STEP_14", "Candidate Info — company questions (No)", "No",       ["resume", "upload", "cv", "attach"],    "[BOT_NO_RESPONSE]"),
    ]

    for step_id, name, value, next_keywords, fail_tag in steps_data:
        step = StepResult(step_id, name)
        t0 = time.time()
        try:
            sent = await _send_chat_message(page, value)
            if not sent:
                step.fail("[ELEMENT_MISSING]", f"Chat input not found when trying to send: {value}")
                step.screenshot = await screenshot(page, f"{step_id}_fail")
            else:
                await page.wait_for_timeout(5000)
                
                body = await page.evaluate(
                    "() => document.body.innerText"
                )
                
                #print(f"\n===== AFTER SUBMITTING: {value} =====")
                #print(body[:3000])
                #print("=====================================\n")
                
                appeared = await wait_for_bot_text(
                    page,
                    next_keywords,
                    TIMEOUT_BOT
                )

                if not appeared:
                
                    await page.wait_for_timeout(5000)
                
                    current_url = page.url
                
                    body = await page.evaluate(
                        "() => document.body.innerText"
                    )
                
                    #print(f"\n===== DEBUG AFTER SUBMITTING: {value} =====")
                    #print(f"Current URL: {current_url}")
                    #print(body[:5000])
                    #print("===========================================\n")
                
                    html = await page.content()
                
                    debug_html = os.path.join(
                        ARTIFACTS_DIR,
                        f"{step_id}_debug.html"
                    )
                
                    with open(debug_html, "w", encoding="utf-8") as f:
                        f.write(html)
                
                    print(f"✅ Debug HTML saved: {debug_html}")
                
                    health = await detect_blank_or_spinner(page)
                
                    step.fail(
                        health or fail_tag,
                        f"Bot did not respond with next question after submitting '{value}'"
                    )
                
                    step.screenshot = await screenshot(
                        page,
                        f"{step_id}_fail"
                    )

                    step.fail(
                        health or fail_tag,
                        f"Bot did not respond with next question after submitting '{value}'"
                    )
                    step.screenshot = await screenshot(page, f"{step_id}_fail")

                else:

                    print(f"      ✅  {name}")

                    if value.lower() == "no":

                        print("🔹 Waiting for final completion message")

                        await page.wait_for_timeout(8000)

                        final_text_found = await wait_for_bot_text(
                            page,
                            [
                                "uploading your resume",
                                "next steps",
                                "prescreening",
                                "you're all set"
                            ],
                            20000
                        )

                        body = await page.evaluate(
                            "() => document.body.innerText"
                        )

                        #print("\n===== FINAL BOT MESSAGE =====")
                        ##print(body[:5000])
                        print("================================\n")

                        print(f"✅ Final message detected: {final_text_found}")

        except Exception as e:
            step.fail("[API_ERROR]", str(e)[:200])
            step.screenshot = await screenshot(page, f"{step_id}_fail")
        step.duration = time.time() - t0
        results.append(step)

        if step.status == "FAIL":
            break   # stop at first failure in this stage

    return results

# ── STAGE 6 — Resume Upload ───────────────────────────────────────────────────

async def stage6_resume(page: Page, candidate_email: str) -> list[StepResult]:
    results = []

    # Step 15 — upload
    step15 = StepResult("STEP_15", "Resume Upload — upload resume file")
    t0 = time.time()
    try:
        # Look for file input
        file_locs = [
            page.locator('input[type="file"]').first,
            page.locator('[class*="upload" i] input[type="file"]').first,
        ]
        uploaded = False
        for loc in file_locs:
            try:
                if await loc.count() > 0:
                    if os.path.exists(RESUME_PATH):
                        await loc.first.set_input_files(RESUME_PATH, timeout=TIMEOUT_UPLOAD)
                        uploaded = True
                        break
                    else:
                        step15.fail("[UPLOAD_FAILURE]",f"Resume file not found at: {RESUME_PATH}")
                        step15.screenshot = await screenshot(page, "STEP_15_fail")
                        step15.duration = time.time() - t0
                        results.append(step15)
                        return results
            except Exception:
                continue

        if not uploaded and step15.status != "FAIL":
        
            body = await page.evaluate(
                "() => document.body.innerText"
            )
        
            #print("\n===== RESUME PAGE DEBUG =====")
            #print(body[:5000])
            #print("================================\n")
        
            html = await page.content()
        
            debug_html = os.path.join(
                ARTIFACTS_DIR,
                "resume_debug.html"
            )
        
            with open(debug_html, "w", encoding="utf-8") as f:
                f.write(html)
        
            print(f"✅ Resume debug HTML saved: {debug_html}")
        
            inputs = await page.locator("input").count()
        
            print(f"🔹 TOTAL INPUT ELEMENTS: {inputs}")
        
            file_inputs = await page.locator(
                'input[type="file"]'
            ).count()
        
            print(f"🔹 FILE INPUTS FOUND: {file_inputs}")
        
            buttons = await page.locator("button").all_inner_texts()
        
            print("🔹 BUTTONS FOUND:")
            print(buttons)
        
            step15.fail(
                "[ELEMENT_MISSING]",
                "File input for resume upload not found"
            )
        
            step15.screenshot = await screenshot(
                page,
                "STEP_15_fail"
            )

        elif uploaded:
            await page.wait_for_timeout(2000)
            body = await page.evaluate("() => document.body.innerText")
            if any(kw in body.lower() for kw in ["upload failed", "invalid file", "unsupported"]):
                step15.fail("[UPLOAD_FAILURE]", "File rejected — upload failed or unsupported format")
                step15.screenshot = await screenshot(page, "STEP_15_fail")
            else:
                print("      ✅  Resume uploaded")
    except Exception as e:
        step15.fail("[UPLOAD_FAILURE]", str(e)[:200])
        step15.screenshot = await screenshot(page, "STEP_15_fail")
    step15.duration = time.time() - t0
    results.append(step15)

    if step15.status == "FAIL":
        return results

    # Step 16 — submit resume
    step16 = StepResult("STEP_16", "Resume Upload — click Submit")
    t0 = time.time()
    try:
        btn_locs = [
            page.get_by_role("button", name=re.compile("submit", re.I)),
            page.get_by_text(re.compile("submit", re.I)),
            page.locator('button:has-text("Submit")'),
        ]
        clicked = False
        for loc in btn_locs:
            try:
                if await loc.count() > 0:
                    await loc.first.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            step16.fail("[ELEMENT_MISSING]", "Submit button not found after resume upload")
            step16.screenshot = await screenshot(page, "STEP_16_fail")
        else:
            appeared = await wait_for_bot_text(
                page,
                ["video", "marketing", "watch", "proceed", "next step"],
                TIMEOUT_NAV
            )
            if not appeared:
                health = await detect_blank_or_spinner(page)
                step16.fail(
                    health or "[NAV_BROKEN]",
                    "Marketing video section did not load after resume submit"
                )
                step16.screenshot = await screenshot(page, "STEP_16_fail")
            else:
                print("      ✅  Resume submitted — video section loading")
    except Exception as e:
        step16.fail("[API_ERROR]", str(e)[:200])
        step16.screenshot = await screenshot(page, "STEP_16_fail")
    step16.duration = time.time() - t0
    results.append(step16)

    return results

# ── STAGE 7 — Marketing Video ─────────────────────────────────────────────────

async def stage7_video(page: Page, candidate_email: str) -> list[StepResult]:
    results = []

    # Step 17 — validate video
    step17 = StepResult("STEP_17", "Marketing Video — video player visible")
    t0 = time.time()
    try:
        print("🔹 Waiting for marketing video section to load")
    
        await page.wait_for_load_state("networkidle")
    
        await page.wait_for_timeout(10000)
    
        body = await page.evaluate(
            "() => document.body.innerText"
        )

        #print("\n===== VIDEO PAGE DEBUG =====")
        #print(body[:5000])
        #print("================================\n")

        video_found = await page.evaluate("""() => {
            const vid = document.querySelector('video');
            const iframe = document.querySelector('iframe[src*="youtube"],iframe[src*="vimeo"],iframe[src*="video"]');
            const cls = Array.from(document.querySelectorAll('[class*="video" i],[class*="player" i]')).filter(e => e.offsetParent !== null).length;
            return { vid: !!vid, iframe: !!iframe, cls: cls > 0 };
        }""")
        if not any(video_found.values()):
            step17.fail("[VIDEO_MISSING]", "No video player (video/iframe/player element) found on page")
            step17.screenshot = await screenshot(page, "STEP_17_fail")
        else:
            print("      ✅  Video player visible")
    except Exception as e:
        step17.fail("[VIDEO_MISSING]", str(e)[:200])
        step17.screenshot = await screenshot(page, "STEP_17_fail")
    step17.duration = time.time() - t0
    results.append(step17)

    # Step 18 — proceed to pre-screening
    step18 = StepResult("STEP_18", "Marketing Video — click Proceed to Next Step")
    t0 = time.time()
    try:
        btn_locs = [
            page.get_by_role("button", name=re.compile("proceed|next step|continue", re.I)),
            page.get_by_text(re.compile("proceed to next|next step", re.I)),
        ]

        await page.wait_for_load_state("networkidle")
        
        await page.wait_for_timeout(8000)
        
        body = await page.evaluate(
            "() => document.body.innerText"
        )
        
        #print("\n===== BEFORE PROCEED BUTTON =====")
        #print(body[:5000])
        #print("=================================\n")

        clicked = False
        for loc in btn_locs:
            try:
                if await loc.count() > 0:
                    await loc.first.click(timeout=TIMEOUT_VIDEO)
                    print("🔹 Waiting for pre-screening transition")
                    
                    await page.get_by_text(
                        re.compile(
                            "before we move forward",
                            re.I
                        )
                    ).wait_for(timeout=15000)
                    
                    print("✅ Pre-screening page loaded")
                    clicked = True
                    
                    break
            except Exception:
                continue

        if not clicked:
            step18.fail("[ELEMENT_MISSING]", '"Proceed to Next Step" button not found')
            step18.screenshot = await screenshot(page, "STEP_18_fail")
        else:
            appeared = await wait_for_bot_text(
                page,
                ["pre-screening", "prescreening", "screening", "completed", "introduction"],
                TIMEOUT_NAV
            )
            if not appeared:
                health = await detect_blank_or_spinner(page)
                step18.fail(
                    health or "[NAV_BROKEN]",
                    "Pre-screening section did not load after proceeding from video"
                )
                step18.screenshot = await screenshot(page, "STEP_18_fail")
            else:
                print("      ✅  Reached pre-screening stage")
    except Exception as e:
        step18.fail("[NAV_BROKEN]", str(e)[:200])
        step18.screenshot = await screenshot(page, "STEP_18_fail")
    step18.duration = time.time() - t0
    results.append(step18)

    return results

# ── Main orchestrator ─────────────────────────────────────────────────────────

async def run_monitor():
    browser = None
    portal_page = None
    candidate_email = "unknown"
    all_results: list[StepResult] = []
    
    try:
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
        start_time = time.time()
        failed_step: Optional[StepResult] = None

        print(f"\n{'='*60}")
        print(f"  🚀  Sagility Production Monitor")
        candidate_email = ts_email()
        print(f"  📧  Candidate email : {candidate_email}")
        print(f"  🌐  Portal URL      : {PORTAL_URL}")

        # ── Discord startup diagnostic ──────────────────────────────────────
        print(f"\n  🔔  Discord webhook configured : {'YES' if DISCORD_WEBHOOK else 'NO ❌'}")
        if DISCORD_WEBHOOK:
            masked = DISCORD_WEBHOOK[:60] + "..." if len(DISCORD_WEBHOOK) > 60 else DISCORD_WEBHOOK
            print(f"  🔔  Webhook (masked)           : {masked}")
            if not DISCORD_WEBHOOK.startswith("https://discord.com/api/webhooks/"):
                print(f"  ⚠️  WARNING: Webhook URL format looks wrong!")
        else:
            print(f"  ❌  Set DISCORD_WEBHOOK env var to enable Discord alerts")
        # ───────────────────────────────────────────────────────────────────

        print(f"{'='*60}\n")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=HEADLESS)

            # Two isolated contexts
            portal_ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
            portal_page = await portal_ctx.new_page()
            portal_page.set_default_timeout(15000)

            def _add(step_or_list):
                nonlocal failed_step
                items = step_or_list if isinstance(step_or_list, list) else [step_or_list]
                for s in items:
                    all_results.append(s)
                    emoji = "✅" if s.status == "PASS" else "❌"
                    print(f"  {emoji}  [{s.step_id}] {s.name} — {s.status}"
                          + (f"  {s.tag} {s.reason[:80]}" if s.status == "FAIL" else ""))
                    if s.status == "FAIL" and not failed_step:
                        failed_step = s

            async def _run_or_skip(coro_factory, label: str):
                """Run stage. If previous stage already failed, emit SKIP for this stage."""
                if failed_step:
                    skip = StepResult(label, f"Skipped — previous failure in {failed_step.step_id}")
                    skip.status = "SKIP"
                    all_results.append(skip)
                    return None
                return await coro_factory()

            # ── Execute all stages ─────────────────────────────────────────────────

            print("── STAGE 1: Portal Launch")
            r = await stage1_portal_launch(portal_page, candidate_email)
            _add(r)
            if r.status == "FAIL":
                raise Exception(f"STEP_01 FAILED: {r.reason}")

            print("\n── STAGE 2: Consent")
            r = await _run_or_skip(
                lambda: stage2_consent(portal_page, candidate_email), "STAGE_2")
            if r:
                _add(r)
                if isinstance(r, list):
                    for step in r:
                        if step.status == "FAIL":
                            raise Exception(f"STAGE_2 FAILED: {step.reason}")

            print("\n── STAGE 3: Email Submission")
            r = await _run_or_skip(
                lambda: stage3_email(portal_page, candidate_email),
                "STEP_03"
            )
            if r:
                _add(r)
                if r.status == "FAIL":
                    raise Exception(f"STEP_03 FAILED: {r.reason}")

            print("\n── STAGE 4: Static OTP")
            otp = ""
            if not failed_step:
                otp_step, otp = await stage4_static_otp(
                    portal_page,
                    candidate_email
                )
                _add(otp_step)
                if otp_step.status == "FAIL":
                    raise Exception(f"STEP_06 FAILED: {otp_step.reason}")
            
            print("\n── STAGE 4 (cont.): Submit OTP in Portal")
            if not failed_step and otp:
                r = await stage4_submit_otp(
                    portal_page,
                    otp,
                    candidate_email
                )
                _add(r)
                if r.status == "FAIL":
                    raise Exception(f"STEP_09 FAILED: {r.reason}")

            print("\n── STAGE 5: Candidate Information")
            r = await _run_or_skip(
                lambda: stage5_candidate_info(portal_page, candidate_email),
                "STAGE_5"
            )
            if r:
                _add(r)
                if isinstance(r, list):
                    for step in r:
                        if step.status == "FAIL":
                            raise Exception(f"STAGE_5 FAILED at {step.step_id}: {step.reason}")

            print("\n── STAGE 6: Resume Upload")
            r = await _run_or_skip(
                lambda: stage6_resume(portal_page, candidate_email),
                "STAGE_6"
            )
            if r:
                _add(r)
                if isinstance(r, list):
                    for step in r:
                        if step.status == "FAIL":
                            raise Exception(f"STAGE_6 FAILED at {step.step_id}: {step.reason}")

            print("\n── STAGE 7: Marketing Video → Pre-Screening")
            r = await _run_or_skip(
                lambda: stage7_video(portal_page, candidate_email),
                "STAGE_7"
            )
            if r:
                _add(r)
                if isinstance(r, list):
                    for step in r:
                        if step.status == "FAIL":
                            raise Exception(f"STAGE_7 FAILED at {step.step_id}: {step.reason}")
            
            # Pre-screening (raises exception on failure)
            print("\n── STAGE 8: Pre-Screening")
            await run_prescreening(portal_page)
            print("✅ Pre-screening completed successfully")
            
            # Assessment (raises exception on failure)
            print("\n── STAGE 9: Assessment")
            await run_assessment(portal_page)
            print("✅ Assessment completed successfully")

            # ── Reports ────────────────────────────────────────────────────────────────
            duration = time.time() - start_time
            passed = sum(1 for r in all_results if r.status == "PASS")
            failed = sum(1 for r in all_results if r.status == "FAIL")
        
            results_json = os.path.join(ARTIFACTS_DIR, "results.json")
            with open(results_json, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in all_results], f, indent=2)
        
            report_path = write_report(all_results, candidate_email, duration)
        
            print(f"\n{'='*60}")
            print(f"  📊  {passed} passed  /  {failed} failed  /  {len(all_results)} total")
            print(f"  ⏱   Duration: {duration:.1f}s")
            print(f"  📄  Report  : {report_path}")
            print(f"  📄  JSON    : {results_json}")
        
            # ── SUCCESS: Send Discord Notification ────────────────────────────────────
            
            if DISCORD_WEBHOOK:
                print("\n✅ Sending SUCCESS notification to Discord")
                
                success_result = StepResult(
                    "SUCCESS",
                    "Sagility candidate journey completed successfully"
                )
                success_result.status = "PASS"
                success_result.screenshot = await screenshot(
                    portal_page,
                    "SUCCESS_FINAL"
                )
                
                print(f"✅ Success screenshot saved: {success_result.screenshot}")
                
                await send_discord_alert(
                    success_result,
                    candidate_email
                )
                
                print("\n  ✅  ALL STEPS PASSED — Sagility candidate journey is healthy")

    except Exception as e:
        # ── GLOBAL FAILURE HANDLER ──────────────────────────────────────────────────
        print(f"\n❌ GLOBAL FAILURE: {e}")

        failure_screenshot = ""

        # Take screenshot on failure
        try:
            if portal_page:
                failure_screenshot = await screenshot(
                    portal_page,
                    "GLOBAL_FAILURE"
                )
                print(f"✅ Failure screenshot saved: {failure_screenshot}")
        except Exception as ss_error:
            print(f"❌ Screenshot failed: {ss_error}")

        # Create StepResult for global failure
        global_failure = StepResult(
            "GLOBAL_FAILURE",
            "Global workflow failure"
        )
        global_failure.status = "FAIL"
        global_failure.tag = "[GLOBAL_FAILURE]"
        global_failure.reason = str(e)[:500]
        global_failure.screenshot = failure_screenshot

        # Send Discord alert on failure
        try:
            if DISCORD_WEBHOOK:
                await send_discord_alert(
                    global_failure,
                    candidate_email
                )
                print("✅ Discord failure alert sent")
            else:
                print("⚠️ DISCORD_WEBHOOK not set — skipping Discord alert")
        except Exception as discord_error:
            print(f"❌ Discord failed: {discord_error}")

        # Re-raise to fail the workflow
        raise

    finally:
        # ── CLEANUP ──────────────────────────────────────────────────────────────────
        if browser:
            await browser.close()
            print("🔹 Browser closed")


if __name__ == "__main__":
    asyncio.run(run_monitor())
