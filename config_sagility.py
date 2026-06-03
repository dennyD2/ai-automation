# config_sagility.py — Sagility Hiring Portal configuration

COMPANY = "Sagility"

BASE_URL      = "https://hire-qa.bling-ai.com/sagility?reqId=REQ-017239&country='US'&location='TX'&source=SOURCE-3-125&profileID=IND007053"   # ← replace with actual URL
EXCEL_PATH    = "Sagility Test cases.xlsx"
FLOW_DOC_PATH = "Flow document.docx"

# Sheets to run and which case IDs within them (None = all cases in that sheet)
SCOPE = {
    "Application Stage":  None,
    "Prescreening Stage": None,
}

# Discord webhook for Sagility alerts (overrides env var if set here)
# Leave as "" to fall back to DISCORD_WEBHOOK env var
DISCORD_WEBHOOK = ""
