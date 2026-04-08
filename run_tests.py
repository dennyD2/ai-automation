# run_tests.py — Generic AI-Agentic Test Runner
# Works for ANY website, ANY test case sheet, ANY module.
# AI reads each test case, looks at the live page, decides actions one-by-one,
# executes them, observes the result, and loops — no hardcoded steps ever.

import asyncio
import json
import os
import re
import sys
from typing import Any, Dict, List

import pandas as pd
from playwright.async_api import async_playwright, Page

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL   = os.getenv("BASE_URL",   "https://trajector.bling-ai.com/trajector/login/")
EXCEL_PATH = os.getenv("EXCEL_PATH", "Trajector Test cases.xlsx")
ARTIFACTS  = "artifacts"
MAX_STEPS  = 10        # max AI actions per test case before forced verify
MODEL      = "deepseek-chat"
API_URL    = "https://api.deepseek.com/v1/chat/completions"
API_KEY    = os.getenv("DEEPSEEK_API_KEY", "")

# ── AI call (stdlib only, no langchain) ───────────────────────────────────────

async def call_ai(messages: List[Dict]) -> str:
    import urllib.request
    payload = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 500,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def extract_json(text: str) -> Dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}

# ── Page snapshot: what the AI sees ──────────────────────────────────────────

async def page_snapshot(page: Page) -> Dict:
    """Returns a structured, AI-readable summary of the live page."""
    try:
        data = await page.evaluate("""() => {
            function labelFor(el) {
                if (el.id) {
                    const lb = document.querySelector('label[for="' + el.id + '"]');
                    if (lb) return lb.innerText.trim().slice(0,60);
                }
                const prev = el.previousElementSibling;
                if (prev && ['LABEL','SPAN','P','DIV'].includes(prev.tagName))
                    return prev.innerText.trim().slice(0,60);
                return '';
            }
            const inputs = Array.from(
                document.querySelectorAll('input:not([type=hidden]),textarea,select')
            ).filter(e => e.offsetParent !== null).map(e => ({
                type:        e.type || e.tagName.toLowerCase(),
                placeholder: (e.placeholder || '').trim(),
                label:       labelFor(e),
                name:        (e.name  || '').trim(),
                id:          (e.id    || '').trim(),
                value: e.type === 'password' ? '(hidden)' : (e.value || '').trim().slice(0,80),
            }));

            const buttons = Array.from(document.querySelectorAll(
                'button,[role=button],input[type=submit],input[type=button]'
            )).filter(e => e.offsetParent !== null)
              .map(e => (e.innerText || e.value || '').trim().replace(/\\s+/g,' '))
              .filter(t => t.length > 0 && t.length < 100);

            const links = Array.from(document.querySelectorAll('a[href]'))
                .filter(e => e.offsetParent !== null)
                .map(e => ({ text: e.innerText.trim().replace(/\\s+/g,' ').slice(0,60), href: e.href }))
                .filter(l => l.text.length > 0)
                .slice(0, 20);

            const alerts = Array.from(document.querySelectorAll(
                '[role=alert],[class*=error i],[class*=toast i],[class*=message i],[class*=notification i],[class*=snack i],[class*=warning i]'
            )).filter(e => e.offsetParent !== null)
              .map(e => e.innerText.trim().replace(/\\s+/g,' ').slice(0, 300))
              .filter(t => t.length > 0);

            return {
                inputs,
                buttons,
                links,
                alerts,
                bodyText: document.body.innerText.replace(/\\s+/g,' ').trim().slice(0, 2500),
            };
        }""")
        data["url"]   = page.url
        data["title"] = await page.title()
        return data
    except Exception as e:
        return {
            "url": page.url, "title": "", "inputs": [], "buttons": [],
            "links": [], "alerts": [], "bodyText": "", "error": str(e),
        }


def snapshot_to_text(snap: Dict) -> str:
    parts = [
        f"URL   : {snap.get('url','')}",
        f"Title : {snap.get('title','')}",
    ]
    if snap.get("alerts"):
        parts.append("⚠️  Alerts/errors visible on page:")
        for a in snap["alerts"]:
            parts.append(f"    \"{a}\"")
    if snap.get("inputs"):
        parts.append("📝 Input fields available:")
        for inp in snap["inputs"]:
            desc = inp.get("placeholder") or inp.get("label") or inp.get("name") or inp.get("id") or inp.get("type","?")
            parts.append(f"    [{inp.get('type','input')}] placeholder/label=\"{desc}\"  current-value=\"{inp.get('value','')}\"")
    if snap.get("buttons"):
        parts.append("🔘 Buttons: " + " | ".join(f'"{b}"' for b in snap["buttons"][:15]))
    if snap.get("links"):
        parts.append("🔗 Links : " + " | ".join(f'"{l["text"]}"' for l in snap["links"][:15]))
    parts.append(f"\n📄 Full page text (truncated to 1500 chars):\n{snap.get('bodyText','')[:1500]}")
    return "\n".join(parts)

# ── Execute one AI action ─────────────────────────────────────────────────────

async def execute_action(page: Page, action: Dict) -> str:
    act = action.get("action", "").lower()
    el  = str(action.get("element") or action.get("target") or "").strip()
    val = str(action.get("value", ""))

    # FILL ─────────────────────────────────────────────────────────────────────
    if act == "fill":
        candidates = []
        if el:
            safe = re.escape(el)
            candidates = [
                page.get_by_placeholder(re.compile(safe, re.I)),
                page.get_by_label(re.compile(safe, re.I)),
                page.locator(f'input[name*="{el}" i],textarea[name*="{el}" i]'),
                page.locator(f'input[id*="{el}" i]'),
                page.get_by_role("textbox", name=re.compile(safe, re.I)),
            ]
        candidates.append(page.locator("input:visible,textarea:visible").first)
        for loc in candidates:
            try:
                if await loc.count() > 0:
                    await loc.first.fill(val)
                    try:
                        await loc.first.press("Tab")
                    except Exception:
                        pass
                    return f"Filled \"{el}\" → \"{val[:50]}\""
            except Exception:
                continue
        return f"WARN: could not find input \"{el}\""

    # CLICK ────────────────────────────────────────────────────────────────────
    elif act == "click":
        candidates = []
        if el:
            safe = re.escape(el)
            candidates = [
                page.get_by_role("button", name=re.compile(safe, re.I)),
                page.get_by_role("link",   name=re.compile(safe, re.I)),
                page.get_by_text(re.compile(safe, re.I)),
                page.locator(f'[aria-label*="{el}" i],[title*="{el}" i],[placeholder*="{el}" i]'),
                page.locator(f'[class*="eye"],[class*="toggle"],[class*="show-pass"]'),
            ]
        for loc in candidates:
            try:
                if await loc.count() > 0:
                    await loc.first.click()
                    await page.wait_for_timeout(600)
                    return f"Clicked \"{el}\""
            except Exception:
                continue
        return f"WARN: could not find clickable \"{el}\""

    # PRESS KEY ────────────────────────────────────────────────────────────────
    elif act == "press_key":
        key = action.get("key", "Enter")
        if el:
            safe = re.escape(el)
            for loc in [
                page.get_by_placeholder(re.compile(safe, re.I)),
                page.get_by_label(re.compile(safe, re.I)),
            ]:
                try:
                    if await loc.count() > 0:
                        await loc.first.press(key)
                        await page.wait_for_timeout(400)
                        return f"Pressed {key} on \"{el}\""
                except Exception:
                    continue
        await page.keyboard.press(key)
        await page.wait_for_timeout(400)
        return f"Pressed {key} globally"

    # NAVIGATE ─────────────────────────────────────────────────────────────────
    elif act == "navigate":
        url = action.get("url", BASE_URL)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(700)
        return f"Navigated to {url}"

    # WAIT ─────────────────────────────────────────────────────────────────────
    elif act == "wait":
        ms = int(action.get("ms", 1000))
        await page.wait_for_timeout(ms)
        return f"Waited {ms}ms"

    else:
        return f"Unknown action \"{act}\" — skipped"

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are an autonomous web test automation agent. You execute test cases on a live website by taking one browser action at a time, observing the result, and deciding the next action.

You will receive:
1. The test case ID, description, and expected outcome
2. The CURRENT live page state: URL, visible inputs, buttons, links, alerts, page text
3. A log of actions already taken in this test

You must respond with EXACTLY ONE JSON object — no prose, no markdown, just the raw JSON.

Available actions:
  {{"action":"fill",      "element":"<placeholder or label text>",      "value":"<text>"}}
  {{"action":"click",     "element":"<button text, link text, or label>"}}
  {{"action":"press_key", "element":"<field placeholder or label>",     "key":"Tab|Enter|Escape|Backspace"}}
  {{"action":"navigate",  "url":"<full URL>"}}
  {{"action":"wait",      "ms":1000}}
  {{"action":"verify",    "result":"PASS|FAIL|SKIP",                    "reason":"<one sentence>"}}

Critical rules:
- Identify elements by VISIBLE placeholder, label, or button text — never by CSS or ID.
- "Leave field empty" → fill with value "".
- After completing all described steps, always use "verify" to declare PASS or FAIL.
- Verify by comparing what is actually visible on the page to the expected outcome.
- If the test needs real credentials not given, return verify SKIP with a reason.
- Maximum {MAX_STEPS} actions total — you must verify before hitting the limit.
"""

# ── Agentic test loop ─────────────────────────────────────────────────────────

async def run_case(page: Page, case_id: str, description: str, expectation: str) -> Dict:
    result, reason, shot = "FAIL", "", ""
    step_log = []

    # Navigate to start page
    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(700)
    except Exception as e:
        return {
            "case_id": case_id, "description": description,
            "expectation": expectation, "result": "BLOCKED",
            "reason": str(e), "steps": [], "screenshot": "",
        }

    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
    history_lines: List[str] = []

    for step_num in range(MAX_STEPS):
        snap  = await page_snapshot(page)
        state = snapshot_to_text(snap)
        hist  = ("\n\nActions taken so far:\n" + "\n".join(history_lines)) if history_lines else ""

        user_content = (
            f"Test ID: {case_id}\n"
            f"Description:\n{description}\n\n"
            f"Expected outcome:\n{expectation}"
            f"{hist}\n\n"
            f"Current page state:\n{state}\n\n"
            f"What is your next action?"
        )

        try:
            ai_raw = await call_ai(conversation + [{"role": "user", "content": user_content}])
        except Exception as e:
            step_log.append({"step": step_num+1, "action": "ai_error", "outcome": str(e)})
            result = "ERROR"
            reason = f"AI call failed: {e}"
            break

        action = extract_json(ai_raw)
        act_type = action.get("action", "")
        print(f"      [{step_num+1}] {ai_raw[:150].strip()}")

        # ── verify ────────────────────────────────────────────────────────────
        if act_type == "verify":
            result = action.get("result", "FAIL").upper()
            reason = action.get("reason", "")
            step_log.append({
                "step": step_num+1, "action": "verify",
                "outcome": f"{result}: {reason}",
            })
            break

        # ── execute ───────────────────────────────────────────────────────────
        outcome = await execute_action(page, action)
        await page.wait_for_timeout(500)

        step_log.append({
            "step": step_num+1,
            "action": act_type,
            "element": action.get("element",""),
            "value": action.get("value",""),
            "outcome": outcome,
        })
        history_lines.append(f"  Step {step_num+1}: {act_type}({action.get('element','') or action.get('url','')}) → {outcome}")

        # Keep rolling conversation so AI remembers context
        conversation.append({"role": "user",      "content": user_content})
        conversation.append({"role": "assistant", "content": ai_raw})

    else:
        # Forced verify at step limit
        snap  = await page_snapshot(page)
        state = snapshot_to_text(snap)
        forced = (
            f"Step limit reached. Verify now.\n"
            f"Test: {description}\nExpected: {expectation}\n"
            f"Page state:\n{state}"
        )
        try:
            ai_raw = await call_ai(conversation + [{"role": "user", "content": forced}])
            action = extract_json(ai_raw)
            result = action.get("result", "FAIL").upper()
            reason = action.get("reason", "Step limit reached")
        except Exception:
            result = "FAIL"
            reason = "Step limit reached; AI verify failed"

    # Screenshot on non-pass
    if result in ("FAIL", "ERROR", "BLOCKED"):
        os.makedirs(ARTIFACTS, exist_ok=True)
        shot = os.path.join(ARTIFACTS, f"{case_id}.png")
        try:
            await page.screenshot(path=shot, full_page=True)
        except Exception:
            shot = ""

    return {
        "case_id":     case_id,
        "description": description,
        "expectation": expectation,
        "result":      result,
        "reason":      reason,
        "steps":       step_log,
        "screenshot":  shot,
    }

# ── HTML report ───────────────────────────────────────────────────────────────

def write_html_report(results: List[Dict], path: str):
    colour = {
        "PASS":"#22c55e","FAIL":"#ef4444","SKIP":"#f59e0b",
        "ERROR":"#7c3aed","BLOCKED":"#6b7280",
    }
    rows = ""
    for r in results:
        c = colour.get(r.get("result","FAIL"), "#6b7280")
        steps_html = "<ol>" + "".join(
            f"<li><b>{s.get('action','')}</b>"
            + (f" [{s.get('element','')}]" if s.get('element') else "")
            + (f" = \"{s.get('value','')}\"" if s.get('value') else "")
            + f" → <i>{s.get('outcome','')}</i></li>"
            for s in r.get("steps", [])
        ) + "</ol>"
        shot_html = (
            f'<a href="../{r["screenshot"]}" target="_blank">📷</a>'
            if r.get("screenshot") else ""
        )
        rows += f"""<tr>
          <td style="white-space:nowrap">{r['case_id']}</td>
          <td style="font-size:12px;white-space:pre-wrap">{r.get('description','')}</td>
          <td style="font-size:12px">{r.get('expectation','')}</td>
          <td style="font-size:12px;color:#444">{r.get('reason','')}</td>
          <td style="font-size:11px">{steps_html}</td>
          <td style="font-weight:bold;color:{c};font-size:18px;text-align:center">{r.get('result','')}</td>
          <td style="text-align:center">{shot_html}</td>
        </tr>"""

    total  = len(results)
    passed = sum(1 for r in results if r.get("result")=="PASS")
    failed = sum(1 for r in results if r.get("result")=="FAIL")
    errors = sum(1 for r in results if r.get("result") in ("ERROR","BLOCKED"))
    skipped= sum(1 for r in results if r.get("result")=="SKIP")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>AI Test Report</title>
<style>
  body{{font-family:Arial,sans-serif;margin:24px;background:#f8fafc;color:#1e293b}}
  h1{{margin-bottom:8px}}
  .meta{{color:#64748b;font-size:13px;margin-bottom:16px}}
  .summary{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}}
  .badge{{padding:10px 18px;border-radius:8px;color:#fff;font-weight:bold;font-size:14px}}
  table{{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;
         overflow:hidden;box-shadow:0 1px 6px #00000018}}
  th{{background:#1e293b;color:#fff;padding:10px 8px;font-size:13px;text-align:left}}
  td{{padding:8px;border-bottom:1px solid #e2e8f0;vertical-align:top;font-size:13px}}
  tr:hover{{background:#f1f5f9}}
  ol{{margin:4px 0;padding-left:18px}}li{{margin-bottom:2px}}
</style></head><body>
<h1>🤖 AI Agentic Test Report</h1>
<p class="meta">File: <b>{os.path.basename(EXCEL_PATH)}</b> &nbsp;|&nbsp; Site: <b>{BASE_URL}</b></p>
<div class="summary">
  <div class="badge" style="background:#22c55e">✅ PASS: {passed}</div>
  <div class="badge" style="background:#ef4444">❌ FAIL: {failed}</div>
  <div class="badge" style="background:#7c3aed">💥 ERROR/BLOCKED: {errors}</div>
  <div class="badge" style="background:#f59e0b">⏭ SKIP: {skipped}</div>
  <div class="badge" style="background:#64748b">📋 TOTAL: {total}</div>
</div>
<table>
  <tr>
    <th>Case ID</th><th>Description</th><th>Expected</th>
    <th>AI Reasoning</th><th>Steps Taken by AI</th><th>Result</th><th>📷</th>
  </tr>
  {rows}
</table></body></html>"""

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)

# ── helpers ───────────────────────────────────────────────────────────────────

def to_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()

# ── entry point ───────────────────────────────────────────────────────────────

async def main():
    if not API_KEY:
        print("❌  DEEPSEEK_API_KEY is not set.")
        print("    Export it:  export DEEPSEEK_API_KEY=sk-...")
        sys.exit(1)

    os.makedirs(ARTIFACTS, exist_ok=True)
    all_results: List[Dict] = []
    out_json = os.path.join(ARTIFACTS, "results.json")
    out_html = os.path.join(ARTIFACTS, "report.html")

    # Write placeholder so CI always has an artifact to upload
    with open(out_json, "w") as fh:
        json.dump([], fh)

    # Load all sheets
    xl = pd.ExcelFile(EXCEL_PATH)
    print(f"📂  Excel: {EXCEL_PATH}")
    print(f"📋  Sheets: {xl.sheet_names}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page    = await context.new_page()
        page.set_default_timeout(12000)

        # ── Preflight ─────────────────────────────────────────────────────────
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25000)
            print(f"\n✅  Preflight OK — {BASE_URL}")
        except Exception as exc:
            print(f"\n❌  Preflight FAILED: {exc}")
            all_results.append({
                "case_id": "preflight", "description": "Connectivity check",
                "expectation": BASE_URL, "result": "BLOCKED",
                "reason": str(exc), "steps": [], "screenshot": "",
            })
            with open(out_json, "w") as fh:
                json.dump(all_results, fh, indent=2)
            write_html_report(all_results, out_html)
            await browser.close()
            sys.exit(2)

        # ── Run every sheet ───────────────────────────────────────────────────
        for sheet in xl.sheet_names:
            print(f"\n{'='*60}")
            print(f"  Sheet: {sheet}")
            print(f"{'='*60}")
            try:
                df = pd.read_excel(EXCEL_PATH, sheet_name=sheet)
            except Exception as exc:
                print(f"  ⚠️  Skipping sheet '{sheet}': {exc}")
                continue

            for idx, row in df.iterrows():
                case_id     = to_str(row.get("Test case ID", row.get("Test case", ""))) or f"{sheet}_row{idx}"
                description = to_str(row.get("Description", ""))
                expectation = to_str(row.get("Expectation", ""))

                if not description:
                    continue  # blank row

                print(f"\n  🚀  {case_id}")
                print(f"      📝  {description[:120].replace(chr(10),' ')}")

                res = await run_case(page, case_id, description, expectation)

                emoji = {"PASS":"✅","FAIL":"❌","SKIP":"⏭","ERROR":"💥","BLOCKED":"🚫"}.get(res["result"],"❓")
                print(f"      {emoji}  {res['result']} — {str(res.get('reason',''))[:120]}")

                all_results.append(res)

                # Save after every test so partial results survive a crash
                with open(out_json, "w", encoding="utf-8") as fh:
                    json.dump(all_results, fh, indent=2, ensure_ascii=False)

        await browser.close()

    write_html_report(all_results, out_html)

    total  = len(all_results)
    passed = sum(1 for r in all_results if r.get("result") == "PASS")
    print(f"\n{'='*60}")
    print(f"  📊  {passed}/{total} passed")
    print(f"  📄  HTML report  →  {out_html}")
    print(f"  📄  JSON results →  {out_json}")


if __name__ == "__main__":
    asyncio.run(main())
