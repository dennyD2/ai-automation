from datetime import datetime

def generate_unique_email() -> str:

short_ts = datetime.utcnow().strftime("%d%H%M%S")

return f"bling2cloud+{short_ts}@gmail.com"
