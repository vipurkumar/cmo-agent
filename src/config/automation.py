"""Automation configuration for OmniGTM Phase 4.

Defines thresholds for narrow automation — auto-outbound only triggers
for tightly defined high-confidence cases. All thresholds are intentionally
STRICTER than manual pursue_now thresholds.

Per-workspace overrides via WorkspaceSettings.settings_data["automation"].
"""

from __future__ import annotations

# --- Feature flags ---
# Automation is OFF by default — must be explicitly enabled per workspace

AUTOMATION_DEFAULTS = {
    "enabled": False,                   # master switch — must be True to auto-send
    "require_approval_override": True,  # if True, admin must explicitly enable
}

# --- Auto-outbound thresholds (stricter than manual pursue_now) ---

AUTO_OUTBOUND_THRESHOLDS = {
    "overall_priority_min": 80,         # manual is 60
    "top_contact_relevance_min": 85,    # manual is 70
    "pain_confidence_min": 0.70,        # manual is 0.50
    "account_score_confidence_min": 0.80,  # overall confidence floor
    "min_signals": 2,                   # at least 2 corroborating signals
    "min_pain_hypotheses": 1,           # at least 1 pain hypothesis
    "max_unknowns": 3,                  # brief can't have > 3 unknowns
}

# --- Send caps (per workspace, per day/week) ---

SEND_CAPS = {
    "daily_max_per_workspace": 25,      # max auto-sends per workspace per day
    "weekly_max_per_workspace": 100,    # max auto-sends per workspace per week
    "daily_max_per_account": 3,         # max messages to a single account per day
    "cool_down_hours": 48,             # min hours between messages to same contact
}

# --- Blocklist config ---

BLOCKLIST_CONFIG = {
    "check_domain_blocklist": True,
    "check_email_blocklist": True,
    "check_company_blocklist": True,
    "auto_block_unsubscribed": True,    # auto-add unsubscribed contacts
}

# --- Kill switch ---

KILL_SWITCH = {
    "global_pause": False,              # emergency stop all automation
    "pause_on_error_rate": 0.10,        # auto-pause if >10% of sends error
    "error_window_hours": 24,           # error rate measured over this window
    "pause_on_negative_reply_rate": 0.25,  # auto-pause if >25% negative replies
    "reply_window_hours": 72,           # reply rate measured over this window
}

# --- Rollback config ---

ROLLBACK_CONFIG = {
    "keep_audit_days": 90,              # retain automation audit trail for 90 days
    "allow_undo_hours": 24,             # can undo automated actions within 24h
}
