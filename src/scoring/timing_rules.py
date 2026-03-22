"""Deterministic timing score from signal recency.

Timing score (0–100) reflects how recently relevant signals were observed.
Uses configurable decay windows from action_thresholds.SIGNAL_DECAY.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agent.state import Signal
from src.config.action_thresholds import SIGNAL_DECAY


def _recency_score(signal_date: datetime | None, now: datetime | None = None) -> float:
    """Compute a 0.0–1.0 recency score based on signal age.

    - Within fresh_days: 1.0
    - Between fresh and stale: linear decay to 0.3
    - Between stale and expired: linear decay to 0.0
    - Beyond expired: 0.0
    """
    if signal_date is None:
        return 0.3  # unknown date = moderate recency

    now = now or datetime.now(tz=timezone.utc)
    if signal_date.tzinfo is None:
        signal_date = signal_date.replace(tzinfo=timezone.utc)

    age_days = (now - signal_date).days
    fresh = SIGNAL_DECAY["fresh_days"]
    stale = SIGNAL_DECAY["stale_days"]
    expired = SIGNAL_DECAY["expired_days"]

    if age_days <= fresh:
        return 1.0
    if age_days <= stale:
        return 0.3 + 0.7 * (stale - age_days) / (stale - fresh)
    if age_days <= expired:
        return 0.3 * (expired - age_days) / (expired - stale)
    return 0.0


def score_timing(
    signals: list[Signal],
    now: datetime | None = None,
) -> tuple[int, float]:
    """Compute a timing score (0–100) from a list of signals.

    Strategy:
    - Take the top 5 signals by reliability * recency
    - Weight recent, reliable signals more heavily
    - No signals = low timing score (30)

    Returns
    -------
    tuple of (timing_score, confidence)
    """
    if not signals:
        return 30, 0.2  # no signals = low timing, low confidence

    now = now or datetime.now(tz=timezone.utc)

    # Score each signal
    scored: list[tuple[float, Signal]] = []
    for signal in signals:
        recency = _recency_score(signal.event_date, now)
        if recency <= 0.0:
            continue  # expired signals don't count
        # Combined weight: recency * reliability
        weight = recency * max(signal.reliability_score, 0.3)
        scored.append((weight, signal))

    if not scored:
        return 20, 0.2

    # Sort by weight descending, take top 5
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    # Weighted average of recency scores, scaled to 0–100
    total_weight = sum(w for w, _ in top)
    weighted_sum = sum(w * _recency_score(s.event_date, now) for w, s in top)
    avg_recency = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Base score from recency
    timing_score = int(min(100, max(0, round(avg_recency * 80 + 20))))

    # Bonus for signal volume (more signals = more confidence in timing)
    volume_bonus = min(15, len(scored) * 3)
    timing_score = min(100, timing_score + volume_bonus)

    # Confidence based on signal count and reliability
    avg_reliability = sum(s.reliability_score for _, s in top) / len(top)
    confidence = min(1.0, 0.3 + (len(scored) * 0.1) + (avg_reliability * 0.3))

    return timing_score, confidence
