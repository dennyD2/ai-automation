# config_sagility.py — Sagility Hiring Portal configuration

COMPANY = "Sagility"

BASE_URL      = "https://your-sagility-portal-url.com"   # ← replace with actual URL
EXCEL_PATH    = "Sagility Test cases.xlsx"
FLOW_DOC_PATH = "Sagility Flow document.docx"

# Sheets to run and which case IDs within them (None = all cases in that sheet)
SCOPE = {
    "Application Stage":  None,
    "Prescreening Stage": None,
}

# Discord webhook for Sagility alerts (overrides env var if set here)
# Leave as "" to fall back to DISCORD_WEBHOOK env var
DISCORD_WEBHOOK = ""
