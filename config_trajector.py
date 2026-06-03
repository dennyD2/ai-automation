# config_trajector.py — Trajector Portal configuration

COMPANY = "Trajector"

BASE_URL      = "https://main.d1lrc6o2sgi54h.amplifyapp.com/trajector/login.html"
EXCEL_PATH    = "Trajector Test cases.xlsx"
FLOW_DOC_PATH = "Trajector Flow document.docx"

# Sheets to run and which case IDs within them (None = all cases in that sheet)
SCOPE = {
    "Forgot Password": None,
}

# Discord webhook for Trajector alerts (overrides env var if set here)
# Leave as "" to fall back to DISCORD_WEBHOOK env var
DISCORD_WEBHOOK = ""
