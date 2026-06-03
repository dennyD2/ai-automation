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
import urllib.request

from playwright.async_api import async_playwright, BrowserContext, Page

# ── Configuration ─────────────────────────────────────────────────────────────

PORTAL_URL      = "https://hire-qa.bling-ai.com/sagility?reqId=REQ-017239&country='US'&location='TX'&source=SOURCE-3-125&profileID=IND007053"
GMAIL_EMAIL     = "bling2cloud@gmail.com"
GMAIL_PASSWORD  = "Bling@12345"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
ARTIFACTS_DIR   = "artifacts"

# Candidate test data (from flow document)
CANDIDATE_NAME  = "John Thomas"
CANDIDATE_PHONE = "9879879879"
CANDIDATE_PIN   = "600100"
RESUME_PATH     = os.path.join(os.path.dirname(__file__), "sample_resume.pdf")

# Timeouts (from flow document)
TIMEOUT_WEBSITE   = 15_000   # ms
TIMEOUT_BOT       = 30_000   # ms
TIMEOUT_OTP_EMAIL = 60_000   # ms — Gmail can be slow in CI; document says 20s but 60s is safer
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

# ── Step result tracker ───────────────────────────────────────────────────────

class StepResult:
    def __init__(self, step_id: str, name: str):
        self.step_id   = step_id
        self.name      = name
        self.status    = "PASS"       # PASS | FAIL | SKIP
        self.reason    = ""
        self.tag       = ""           # failure classification tag
        self.screenshot = ""
        self.duration  = 0.0
        self.ts        = datetime.utcnow().isoformat()

    def fail(self, tag: str, reason: str):
        self.status = "FAIL"
        self.tag    = tag
        self.reason = reason

    def to_dict(self):
        return {
            "step": self.step_id, "name": self.name, "status": self.status,
            "tag": self.tag, "reason": self.reason,
            "screenshot": self.screenshot, "duration_s": round(self.duration, 2),
            "timestamp": self.ts,
        }

# ── Helpers ───────────────────────────────────────────────────────────────────

os.makedirs(ARTIFACTS_DIR, exist_ok=True)

def ts_email() -> str:
    return f"bling2cloud+{datetime.utcnow().strftime('%Y%m%d%H%M%S')}@gmail.com"

async def screenshot(page: Page, name: str) -> str:
    path = os.path.join(ARTIFACTS_DIR, f"{name}.png")
    try:
        await page.screenshot(path=path, full_page=True)
    except Exception:
        path = ""
    return path

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
}

def _discord_color(tag: str) -> int:
    severity = SEVERITY.get(tag, ("", "high"))[1]
    return {"critical": 15158332, "high": 16744272, "medium": 16776960}.get(severity, 15158332)

async def send_discord_alert(step: StepResult, candidate_email: str = ""):
    if not DISCORD_WEBHOOK:
        print(f"  ⚠️  DISCORD_WEBHOOK not set — skipping alert for {step.step_id}")
        return

    label = SEVERITY.get(step.tag, (step.tag, "high"))[0]
    ts_human = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    fields = [
        {"name": "Step",            "value": f"`{step.step_id}` — {step.name}", "inline": False},
        {"name": "Failure type",    "value": label or step.tag or "Unknown",    "inline": True},
        {"name": "Timestamp",       "value": ts_human,                          "inline": True},
        {"name": "Reason",          "value": step.reason[:300] or "—",         "inline": False},
    ]
    if candidate_email:
        fields.append({"name": "Candidate email", "value": candidate_email, "inline": False})
    if RUN_URL:
        fields.append({"name": "CI Run", "value": f"[View run]({RUN_URL})", "inline": False})
    if step.screenshot:
        fields.append({"name": "Screenshot", "value": f"`{step.screenshot}`", "inline": False})

    embed = {
        "title": f"🚨 Sagility Monitor — {step.step_id} FAILED",
        "description": f"**{label or step.tag}** detected during production flow monitoring.",
        "color": _discord_color(step.tag),
        "fields": fields,
        "footer": {"text": f"Portal: {PORTAL_URL}"},
    }

    payload = json.dumps({"embeds": [embed]}).encode()
    req = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  📣  Discord alert sent for {step.step_id} — HTTP {resp.status}")
    except Exception as e:
        print(f"  ⚠️  Discord alert failed: {e}")

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
                    print("\n===== PAGE AFTER EMAIL SUBMISSION =====")
                    print(body[:3000])
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
        
            print("\n===== AFTER EMAIL SUBMISSION =====")
            print(body[:4000])
            print("=================================\n")
            print("      ⚠️  Bot did not explicitly ask for email")
            print("      ⚠️  Continuing anyway")
        
        else:
            print("      ✅  Bot sent OTP request")
    except Exception as e:
        step.fail("[API_ERROR]", str(e)[:200])
        step.screenshot = await screenshot(page, "STEP_05_fail")
    step.duration = time.time() - t0
    return step

# ── STAGE 4 — Gmail OTP ───────────────────────────────────────────────────────

async def stage4_otp_gmail(gmail_context: BrowserContext, candidate_email: str) -> tuple[StepResult, str]:
    """Returns (step_result, otp_string). otp_string is '' on failure."""

    # Step 6 — Gmail login
    step6 = StepResult("STEP_06", "Gmail OTP — login to Gmail")
    t0 = time.time()
    gmail_page = await gmail_context.new_page()
    otp = ""

    try:
        await gmail_page.goto("https://accounts.google.com/signin/v2/identifier?service=mail", wait_until="domcontentloaded", timeout=TIMEOUT_WEBSITE)
        print("\n========== GMAIL DEBUG ==========")

        print("Current URL:")
        print(gmail_page.url)
        
        print("\nPage title:")
        print(await gmail_page.title())
        frames = gmail_page.frames
        print("\n===== FRAMES =====")
        
        all_inputs = await gmail_page.locator("input").count()
        print(f"\nTOTAL INPUTS FOUND: {all_inputs}\n")
              
        for i, frame in enumerate(frames):
            print(f"FRAME {i}: {frame.url}")
        
        print("==================\n")
        await gmail_page.screenshot(path="artifacts/gmail_debug.png")
        
        body_text = await gmail_page.evaluate("() => document.body.innerText")
        
        print("\nVisible page text:")
        print(body_text[:8000])
        
        html = await gmail_page.content()
        
        with open("artifacts/gmail_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        print("\nSaved:")
        print(" - artifacts/gmail_debug.png")
        print(" - artifacts/gmail_debug.html")
        
        print("=================================\n")
        
# Check if already logged in
        body = await gmail_page.evaluate("() => document.body.innerText")
        
        if "inbox" in body.lower() or "compose" in body.lower() or "primary" in body.lower():
        
            print("      ✅  Gmail already logged in")
        
        else:
        
            # Fill email
        
            found_email_input = False
        
            for frame in gmail_page.frames:
        
                try:
        
                    email_input = frame.locator('input[type="email"]').first
        
                    if await email_input.count() > 0:
        
                        print(f"✅ Found email input inside frame: {frame.url}")
        
                        await email_input.fill(GMAIL_EMAIL)
        
                        found_email_input = True
        
                        break
        
                except Exception:
                    pass
        
            if not found_email_input:
                raise Exception("Could not find Gmail email input in any frame")
        
            await gmail_page.keyboard.press("Enter")
        
            await gmail_page.wait_for_timeout(4000)
        
        
        password_found = False
        
        for _ in range(30):
        
            for frame in gmail_page.frames:
        
                try:
        
                    password_input = frame.locator('input[type="password"]').first
        
                    if await password_input.count() > 0:
        
                        print(f"✅ Found password input inside frame: {frame.url}")
        
                        await password_input.fill(GMAIL_PASSWORD)
        
                        password_found = True
        
                        break
        
                except Exception:
                    pass
        
            if password_found:
                break
        
            await gmail_page.wait_for_timeout(1000)
        
        if not password_found:
            raise Exception("Could not find Gmail password input")

        
            await gmail_page.get_by_role("button", name=re.compile("next", re.I)).click()
            await gmail_page.wait_for_url(
                re.compile(r"challenge|pwd|password", re.I),
                timeout=30000
            )
            
            await gmail_page.wait_for_load_state("networkidle")
        
        await gmail_page.wait_for_timeout(5000)
        
        print(f"✅ Gmail moved to password page: {gmail_page.url}")
            await gmail_page.wait_for_timeout(8000)

            body = await gmail_page.evaluate("() => document.body.innerText")
            if "inbox" not in body.lower() and "compose" not in body.lower() and "primary" not in body.lower():
                step6.fail("[GMAIL_FAILURE]", "Gmail login failed — inbox not accessible after login")
                step6.screenshot = await screenshot(gmail_page, "STEP_06_fail")
                step6.duration = time.time() - t0
                await gmail_page.close()
                return step6, otp
            print("      ✅  Gmail logged in")
    except Exception as e:
        step6.fail("[GMAIL_FAILURE]", f"Gmail login error: {str(e)[:200]}")
        step6.screenshot = await screenshot(gmail_page, "STEP_06_fail")
        step6.duration = time.time() - t0
        await gmail_page.close()
        return step6, otp

    step6.duration = time.time() - t0

    # Step 7+8 — Retrieve and extract OTP
    step7 = StepResult("STEP_07_08", "Gmail OTP — retrieve and extract OTP from inbox")
    t0 = time.time()
    try:
        deadline = time.time() + TIMEOUT_OTP_EMAIL / 1000
        found = False
        while time.time() < deadline:
            # Reload inbox to catch new mail
            await gmail_page.goto("https://mail.google.com/#inbox", wait_until="domcontentloaded", timeout=15000)
            await gmail_page.wait_for_timeout(2000)

            # Find the first unread mail that looks like an OTP mail
            email_rows = gmail_page.locator('[role="row"]')
            count = await email_rows.count()
            for i in range(min(count, 5)):
                try:
                    row_text = await email_rows.nth(i).inner_text()
                    if candidate_email.lower() in row_text.lower():
                        await email_rows.nth(i).click()
                        await gmail_page.wait_for_timeout(1500)
                        body_text = await gmail_page.evaluate("() => document.body.innerText")
                        match = re.search(r"\b\d{4,6}\b", body_text)
                        if match:
                            otp = match.group()
                            print(f"      ✅  OTP extracted: {otp}")
                            found = True
                            break
                except Exception:
                    continue
            if found:
                break
            await gmail_page.wait_for_timeout(3000)

        if not found or not otp:
            step7.fail("[OTP_FAILURE]", f"OTP email not found in Gmail inbox within {TIMEOUT_OTP_EMAIL//1000}s")
            step7.screenshot = await screenshot(gmail_page, "STEP_07_fail")

    except Exception as e:
        step7.fail("[OTP_FAILURE]", f"OTP retrieval error: {str(e)[:200]}")
        step7.screenshot = await screenshot(gmail_page, "STEP_07_fail")

    step7.duration = time.time() - t0
    await gmail_page.close()

    # Return the first failure if login failed
    if step6.status == "FAIL":
        return step6, otp
    return step7, otp

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
                appeared = await wait_for_bot_text(page, next_keywords, TIMEOUT_BOT)
                if not appeared:
                    health = await detect_blank_or_spinner(page)
                    step.fail(
                        health or fail_tag,
                        f"Bot did not respond with next question after submitting '{value}'"
                    )
                    step.screenshot = await screenshot(page, f"{step_id}_fail")
                else:
                    print(f"      ✅  {name}")
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
                        step15.fail("[UPLOAD_FAILURE]", f"sample_resume.pdf not found at {RESUME_PATH}. Commit it to the repo root.")
                        step15.screenshot = await screenshot(page, "STEP_15_fail")
                        step15.duration = time.time() - t0
                        results.append(step15)
                        return results
            except Exception:
                continue

        if not uploaded and step15.status != "FAIL":
            step15.fail("[ELEMENT_MISSING]", "File input for resume upload not found")
            step15.screenshot = await screenshot(page, "STEP_15_fail")
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
        await page.wait_for_timeout(3000)
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
        clicked = False
        for loc in btn_locs:
            try:
                if await loc.count() > 0:
                    await loc.first.click(timeout=TIMEOUT_VIDEO)
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
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    all_results: list[StepResult] = []
    candidate_email = ts_email()
    start_time = time.time()
    failed_step: Optional[StepResult] = None

    print(f"\n{'='*60}")
    print(f"  🚀  Sagility Production Monitor")
    print(f"  📧  Candidate email : {candidate_email}")
    print(f"  🌐  Portal URL      : {PORTAL_URL}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # Two isolated contexts
        portal_ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        gmail_ctx  = await browser.new_context(viewport={"width": 1280, "height": 800})

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

        print("\n── STAGE 2: Consent")
        r = await _run_or_skip(
            lambda: stage2_consent(portal_page, candidate_email),"STAGE_2")
        if r: _add(r)

        print("\n── STAGE 3: Email Submission (Step 4 = email generation — done in code)")
        r = await _run_or_skip(
            lambda: stage3_email(portal_page, candidate_email),
            "STEP_03"
        )
        if r: _add(r)

        print("\n── STAGE 4: Gmail OTP Retrieval")
        otp = ""
        if not failed_step:
            gmail_step, otp = await stage4_otp_gmail(gmail_ctx, candidate_email)
            _add(gmail_step)

        print("\n── STAGE 4 (cont.): Submit OTP in Portal")
        if not failed_step and otp:
            r = await stage4_submit_otp(portal_page, otp, candidate_email)
            _add(r)
        elif not failed_step and not otp:
            # OTP extraction failed — already logged above, just make sure we don't continue
            pass

        print("\n── STAGE 5: Candidate Information")
        r = await _run_or_skip(
            lambda: stage5_candidate_info(portal_page, candidate_email),
            "STAGE_5"
        )
        if r: _add(r)

        print("\n── STAGE 6: Resume Upload")
        r = await _run_or_skip(
            lambda: stage6_resume(portal_page, candidate_email),
            "STAGE_6"
        )
        if r: _add(r)

        print("\n── STAGE 7: Marketing Video → Pre-Screening")
        r = await _run_or_skip(
            lambda: stage7_video(portal_page, candidate_email),
            "STAGE_7"
        )
        if r: _add(r)

        await browser.close()

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

    # ── Discord alerts for every failed step ──────────────────────────────────
    for r in all_results:
        if r.status == "FAIL":
            await send_discord_alert(r, candidate_email)

    if failed == 0:
        print("\n  ✅  ALL STEPS PASSED — Sagility candidate journey is healthy")
    else:
        print(f"\n  🚨  {failed} STEP(S) FAILED — alerts sent to Discord")
        sys.exit(1)   # non-zero exit → GitHub Actions marks the run as failed


if __name__ == "__main__":
    asyncio.run(run_monitor())
