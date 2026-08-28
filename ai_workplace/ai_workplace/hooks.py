app_name = "ai_workplace"
app_title = "Ai Workplace"
app_publisher = "MicroMerger Pvt. Ltd."
app_description = "MicroMerger AI Workplace"
app_email = "ai_workplace@micromerger.com"
app_license = "mit"
required_apps = ["frappe", "erpnext"]

# ──────────────────────────────────────────────────────────────────────────────
# Document Events
# ──────────────────────────────────────────────────────────────────────────────
# No document event hooks needed in Phase 1

# ──────────────────────────────────────────────────────────────────────────────
# Scheduled Tasks  (Phase 1: NONE — no proactive messaging)
# ──────────────────────────────────────────────────────────────────────────────
# scheduler_events = {}

# ──────────────────────────────────────────────────────────────────────────────
# Log Retention
# ──────────────────────────────────────────────────────────────────────────────
default_log_clearing_doctypes = {
    "WhatsApp Message Log": 30,   # days
    "AI Security Event": 90,
}

# ──────────────────────────────────────────────────────────────────────────────
# Override Whitelisted Methods (none in Phase 1)
# ──────────────────────────────────────────────────────────────────────────────
