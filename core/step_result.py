from datetime import datetime

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
