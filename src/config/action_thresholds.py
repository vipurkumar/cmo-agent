"""Configurable thresholds for OmniGTM next-best-action decisions.

All thresholds are tunable per workspace via WorkspaceSettings.
These are the system defaults.
"""

from __future__ import annotations

# --- Action decision thresholds ---

ACTION_THRESHOLDS = {
    "pursue_now": {
        "overall_priority_min": 60,
        "top_contact_relevance_min": 70,
        "pain_confidence_min": 0.50,
    },
    "nurture": {
        "icp_fit_min": 50,
        "timing_max": 50,          # nurture when timing is weak
        "pain_confidence_max": 0.50,
    },
    "disqualify": {
        "icp_fit_max": 30,         # auto-disqualify below this
    },
    "human_review_required": {
        "confidence_min": 0.50,    # route to human below this
    },
}

# --- Confidence display thresholds ---

CONFIDENCE_LEVELS = {
    "high": 0.75,       # show without caveats
    "medium": 0.50,     # show with "[medium confidence]" marker
    "low": 0.25,        # show with "[low confidence — verify]" marker
    # below 0.25: suppress from brief, log for audit
}

# --- Signal freshness decay ---

SIGNAL_DECAY = {
    "fresh_days": 14,       # full recency score
    "stale_days": 60,       # recency drops to 0.3
    "expired_days": 180,    # signal ignored
}
