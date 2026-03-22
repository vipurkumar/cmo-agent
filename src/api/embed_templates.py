"""HTML templates for CRM-embedded OmniGTM views.

All templates are self-contained (inline CSS, no external deps)
and designed for iframe embedding in CRM sidebars.
"""

from __future__ import annotations

from html import escape
from typing import Any


def _score_color(score: int) -> tuple[str, str, str]:
    """Return (bg, border, text) CSS colors based on score 0-100."""
    if score >= 70:
        return "#f0fdf4", "#bbf7d0", "#15803d"
    if score >= 40:
        return "#fffbeb", "#fde68a", "#92400e"
    return "#fef2f2", "#fecaca", "#991b1b"


def _score_dot_color(score: int) -> str:
    """Return dot/badge color based on score 0-100."""
    if score >= 70:
        return "#16a34a"
    if score >= 40:
        return "#d97706"
    return "#dc2626"


def _action_colors(action: str) -> tuple[str, str, str]:
    """Return (bg, border, text) for action type badge."""
    action_upper = action.upper().replace("_", " ")
    if "PURSUE" in action_upper:
        return "#f0fdf4", "#bbf7d0", "#15803d"
    if "NURTURE" in action_upper:
        return "#eff6ff", "#bfdbfe", "#1e40af"
    if "DISQUALIFY" in action_upper:
        return "#fef2f2", "#fecaca", "#991b1b"
    return "#fffbeb", "#fde68a", "#92400e"


def _action_label(action: str) -> str:
    """Normalize action string to display label."""
    return action.upper().replace("_", " ")


def _safe(value: Any, default: str = "") -> str:
    """Escape a value for safe HTML rendering."""
    if value is None:
        return escape(default)
    return escape(str(value))


def _dark_overrides() -> str:
    """Return CSS overrides for dark theme."""
    return """
    body {
      background: #1a1a2e !important;
      color: #e2e8f0 !important;
    }
    .card {
      background: #16213e !important;
      border-color: #2d3a5c !important;
    }
    .card-header {
      border-color: #2d3a5c !important;
    }
    .label {
      color: #94a3b8 !important;
    }
    .value {
      color: #e2e8f0 !important;
    }
    .link {
      color: #60a5fa !important;
    }
    """


# ---------------------------------------------------------------------------
# Compact card (300px CRM sidebar)
# ---------------------------------------------------------------------------


def render_card(
    brief_data: dict[str, Any],
    score_data: dict[str, Any],
    theme: str = "light",
) -> str:
    """Return compact HTML card for CRM sidebar (max 300px wide)."""
    brief_json = brief_data.get("brief_json") or {}
    company_name = _safe(brief_json.get("account_snapshot", "Unknown Account")[:80])
    overall_score = int(score_data.get("overall_priority_score", brief_data.get("overall_score", 0)))
    action_type = str(brief_data.get("action_type", score_data.get("action_type", "REVIEW")))
    confidence = float(brief_data.get("confidence_score", score_data.get("confidence_score", 0)))
    account_id = _safe(brief_data.get("account_id", ""))

    # Extract top contact
    contacts = brief_json.get("recommended_contacts", [])
    top_contact_name = ""
    top_contact_title = ""
    if contacts:
        c = contacts[0]
        top_contact_name = _safe(c.get("name", ""))
        top_contact_title = _safe(c.get("title", ""))

    # Extract top pain
    pains = brief_json.get("likely_pain_points", [])
    top_pain = ""
    if pains:
        top_pain = _safe(pains[0].get("pain_type", "").replace("_", " ").title())

    # Extract hook
    angles = brief_json.get("persona_angles", [])
    hook = ""
    if angles:
        hook = _safe(angles[0].get("one_line_hook", ""))

    score_bg, score_border, score_text = _score_color(overall_score)
    score_dot = _score_dot_color(overall_score)
    action_bg, action_border, action_text = _action_colors(action_type)
    action_label = _action_label(action_type)

    dark_css = _dark_overrides() if theme == "dark" else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniGTM - Account Card</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f4f6f9;
  color: #1e293b;
  line-height: 1.5;
  padding: 8px;
  -webkit-font-smoothing: antialiased;
}}
.card {{
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  max-width: 300px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
.card-header {{
  padding: 12px 14px;
  border-bottom: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.logo {{
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, #0f1629, #1a1a2e);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #818cf8;
  font-weight: 700;
  font-size: 11px;
  flex-shrink: 0;
}}
.card-header-text {{
  flex: 1;
  min-width: 0;
}}
.card-header-text h2 {{
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.card-body {{
  padding: 14px;
}}
.score-row {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}}
.score-badge {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  background: {score_bg};
  border: 1px solid {score_border};
  color: {score_text};
}}
.score-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: {score_dot};
}}
.action-badge {{
  display: inline-flex;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  background: {action_bg};
  border: 1px solid {action_border};
  color: {action_text};
}}
.field {{
  margin-bottom: 10px;
}}
.label {{
  font-size: 10px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 2px;
}}
.value {{
  font-size: 13px;
  color: #1e293b;
}}
.hook {{
  font-style: italic;
  color: #475569;
}}
.divider {{
  height: 1px;
  background: #f1f5f9;
  margin: 10px 0;
}}
.card-footer {{
  padding: 10px 14px;
  border-top: 1px solid #f1f5f9;
  text-align: center;
}}
.link {{
  font-size: 12px;
  font-weight: 600;
  color: #2563eb;
  text-decoration: none;
}}
.link:hover {{
  text-decoration: underline;
}}
.confidence {{
  font-size: 10px;
  color: #94a3b8;
  margin-top: 4px;
}}
{dark_css}
</style>
</head>
<body>
<div class="card">
  <div class="card-header">
    <div class="logo">GTM</div>
    <div class="card-header-text">
      <h2>OmniGTM Brief</h2>
    </div>
  </div>
  <div class="card-body">
    <div class="score-row">
      <div class="score-badge">
        <span class="score-dot"></span>
        Score: {overall_score}/100
      </div>
      <div class="action-badge">{action_label}</div>
    </div>
    {"" if not top_contact_name else f'''<div class="field">
      <div class="label">Top Contact</div>
      <div class="value">{top_contact_name}</div>
      <div class="value" style="font-size:11px;color:#64748b;">{top_contact_title}</div>
    </div>'''}
    {"" if not top_pain else f'''<div class="field">
      <div class="label">Top Pain</div>
      <div class="value">{top_pain}</div>
    </div>'''}
    {"" if not hook else f'''<div class="divider"></div>
    <div class="field">
      <div class="label">Hook</div>
      <div class="value hook">&ldquo;{hook}&rdquo;</div>
    </div>'''}
    <div class="confidence">Confidence: {confidence:.0%}</div>
  </div>
  <div class="card-footer">
    <a class="link" href="/embed/{account_id}/brief" target="_blank">View Full Brief</a>
  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Full brief page
# ---------------------------------------------------------------------------


def _render_score_gauge(label: str, score: int) -> str:
    """Render a single horizontal score gauge bar."""
    color = _score_dot_color(score)
    return f"""<div style="margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
    <span style="color:#64748b;font-weight:500;">{_safe(label)}</span>
    <span style="font-weight:600;color:{color};">{score}/100</span>
  </div>
  <div style="height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;">
    <div style="width:{score}%;height:100%;background:{color};border-radius:3px;"></div>
  </div>
</div>"""


def _render_contact_card(contact: dict[str, Any]) -> str:
    """Render a single contact card."""
    name = _safe(contact.get("name", "Unknown"))
    title = _safe(contact.get("title", ""))
    role = _safe(contact.get("likely_role", "").replace("_", " ").title())
    relevance = int(contact.get("relevance_score", 0))
    reason = _safe(contact.get("reason_for_relevance", ""))
    color = _score_dot_color(relevance)
    return f"""<div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="font-weight:600;font-size:14px;">{name}</div>
      <div style="font-size:12px;color:#64748b;">{title}</div>
    </div>
    <div style="display:flex;align-items:center;gap:4px;">
      <span style="display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;background:#f5f3ff;color:#5b21b6;border:1px solid #ddd6fe;">{role}</span>
      <span style="font-size:12px;font-weight:600;color:{color};">{relevance}</span>
    </div>
  </div>
  {"" if not reason else f'<div style="font-size:12px;color:#475569;margin-top:6px;">{reason}</div>'}
</div>"""


def _render_pain_card(pain: dict[str, Any]) -> str:
    """Render a pain hypothesis card."""
    pain_type = _safe(pain.get("pain_type", "").replace("_", " ").title())
    score = int(pain.get("score", 0))
    color = _score_dot_color(score)
    inferences = pain.get("inferences", [])
    unknowns = pain.get("unknowns", [])

    inferences_html = ""
    if inferences:
        items = "".join(f"<li>{_safe(i)}</li>" for i in inferences[:3])
        inferences_html = f'<div style="margin-top:6px;"><span style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;">Inferences</span><ul style="margin:4px 0 0 16px;font-size:12px;color:#475569;">{items}</ul></div>'

    unknowns_html = ""
    if unknowns:
        items = "".join(f"<li>{_safe(u)}</li>" for u in unknowns[:2])
        unknowns_html = f'<div style="margin-top:6px;"><span style="font-size:10px;font-weight:600;color:#d97706;text-transform:uppercase;">Unknowns</span><ul style="margin:4px 0 0 16px;font-size:12px;color:#92400e;">{items}</ul></div>'

    return f"""<div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <span style="font-weight:600;font-size:13px;">{pain_type}</span>
    <span style="font-size:12px;font-weight:600;color:{color};">{score}/100</span>
  </div>
  {inferences_html}
  {unknowns_html}
</div>"""


def _render_signal_badge(signal: dict[str, Any]) -> str:
    """Render a signal badge."""
    stype = _safe(signal.get("signal_type", "").replace("_", " ").title())
    fact = _safe(signal.get("observed_fact", ""))
    return f"""<div style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:6px;background:#eff6ff;border:1px solid #bfdbfe;margin:0 6px 6px 0;">
  <span style="font-size:11px;font-weight:600;color:#1e40af;">{stype}</span>
  {"" if not fact else f'<span style="font-size:11px;color:#475569;">- {fact[:60]}</span>'}
</div>"""


def render_full_brief(
    brief_data: dict[str, Any],
    score_data: dict[str, Any],
) -> str:
    """Return full HTML brief page, standalone and print-friendly."""
    brief_json = brief_data.get("brief_json") or {}
    account_id = _safe(brief_data.get("account_id", ""))
    overall_score = int(score_data.get("overall_priority_score", brief_data.get("overall_score", 0)))
    icp_fit = int(score_data.get("icp_fit_score", 0))
    pain_fit = int(score_data.get("pain_fit_score", 0))
    timing = int(score_data.get("timing_score", 0))
    confidence = float(brief_data.get("confidence_score", score_data.get("confidence_score", 0)))
    action_type = str(brief_data.get("action_type", "REVIEW"))
    version = int(brief_data.get("version", 1))
    generated_at = _safe(str(brief_data.get("generated_at", "")))

    action_bg, action_border, action_text = _action_colors(action_type)
    action_label = _action_label(action_type)

    # Sections
    snapshot = _safe(brief_json.get("account_snapshot", "No snapshot available."))
    why_account = _safe(brief_json.get("why_this_account", ""))
    why_now = _safe(brief_json.get("why_now", ""))

    # Pain points
    pains = brief_json.get("likely_pain_points", [])
    pains_html = "".join(_render_pain_card(p) for p in pains) if pains else '<p style="color:#94a3b8;font-size:13px;">No pain hypotheses generated.</p>'

    # Contacts
    contacts = brief_json.get("recommended_contacts", [])
    contacts_html = "".join(_render_contact_card(c) for c in contacts) if contacts else '<p style="color:#94a3b8;font-size:13px;">No contacts ranked.</p>'

    # Persona angles / talk tracks
    angles = brief_json.get("persona_angles", [])
    angles_html = ""
    if angles:
        for a in angles:
            hook = _safe(a.get("one_line_hook", ""))
            prop = _safe(a.get("short_value_prop", ""))
            objection = _safe(a.get("likely_objection", ""))
            response = _safe(a.get("suggested_response", ""))
            angles_html += f"""<div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;margin-bottom:8px;">
  <div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:4px;">&ldquo;{hook}&rdquo;</div>
  <div style="font-size:12px;color:#475569;margin-bottom:6px;">{prop}</div>
  {"" if not objection else f'<div style="font-size:11px;"><span style="font-weight:600;color:#dc2626;">Objection:</span> <span style="color:#475569;">{objection}</span></div>'}
  {"" if not response else f'<div style="font-size:11px;margin-top:2px;"><span style="font-weight:600;color:#16a34a;">Response:</span> <span style="color:#475569;">{response}</span></div>'}
</div>"""
    else:
        angles_html = '<p style="color:#94a3b8;font-size:13px;">No talk tracks generated.</p>'

    # Risks & unknowns
    risks = brief_json.get("risks_and_unknowns", [])
    risks_html = ""
    if risks:
        items = "".join(f'<li style="margin-bottom:4px;">{_safe(r)}</li>' for r in risks)
        risks_html = f'<ul style="margin-left:16px;font-size:13px;color:#475569;">{items}</ul>'
    else:
        risks_html = '<p style="color:#94a3b8;font-size:13px;">No risks identified.</p>'

    # Action recommendation
    rec = brief_json.get("recommended_action", {})
    rec_explanation = _safe(rec.get("explanation", ""))
    rec_channel = _safe(rec.get("best_channel", ""))
    rec_contact = rec.get("best_first_contact", {})
    rec_contact_name = _safe(rec_contact.get("name", "")) if rec_contact else ""
    rec_multi = rec.get("multi_threading_recommended", False)

    # Signals
    signals = brief_json.get("signals_used", [])
    signals_html = "".join(_render_signal_badge(s) for s in signals) if signals else '<p style="color:#94a3b8;font-size:12px;">No signals recorded.</p>'

    # Score gauges
    gauges_html = _render_score_gauge("Overall Priority", overall_score)
    gauges_html += _render_score_gauge("ICP Fit", icp_fit)
    gauges_html += _render_score_gauge("Pain Fit", pain_fit)
    gauges_html += _render_score_gauge("Timing", timing)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniGTM Seller Brief</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f4f6f9;
  color: #1e293b;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}
.page {{
  max-width: 800px;
  margin: 0 auto;
  padding: 24px 16px;
}}
.brief-header {{
  background: linear-gradient(135deg, #0f1629 0%, #1a1a2e 50%, #16213e 100%);
  color: #fff;
  padding: 24px;
  border-radius: 12px 12px 0 0;
  position: relative;
  overflow: hidden;
}}
.brief-header::before {{
  content: '';
  position: absolute;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background: radial-gradient(ellipse at 30% 50%, rgba(99,102,241,0.08) 0%, transparent 60%);
  pointer-events: none;
}}
.brief-header h1 {{
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  position: relative;
}}
.brief-header h1 span {{
  background: linear-gradient(135deg, #818cf8, #60a5fa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.brief-header-meta {{
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: #94a3b8;
  position: relative;
}}
.content {{
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-top: none;
  border-radius: 0 0 12px 12px;
  padding: 24px;
}}
.section {{
  margin-bottom: 24px;
}}
.section:last-child {{
  margin-bottom: 0;
}}
.section-title {{
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #64748b;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid #f1f5f9;
}}
.section-text {{
  font-size: 14px;
  color: #475569;
  white-space: pre-wrap;
}}
.scores-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}
.score-card {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
}}
.action-banner {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-radius: 8px;
  background: {action_bg};
  border: 1px solid {action_border};
  margin-bottom: 16px;
}}
.action-banner-label {{
  font-size: 18px;
  font-weight: 700;
  color: {action_text};
}}
.action-banner-score {{
  font-size: 28px;
  font-weight: 800;
  color: {action_text};
}}
.two-col {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}
@media (max-width: 600px) {{
  .two-col, .scores-grid {{
    grid-template-columns: 1fr;
  }}
}}
@media print {{
  body {{ background: #fff; }}
  .page {{ padding: 0; }}
  .brief-header {{ border-radius: 0; }}
  .content {{ border: none; border-radius: 0; }}
}}
</style>
</head>
<body>
<div class="page">
  <div class="brief-header">
    <h1><span>OmniGTM</span> Seller Brief</h1>
    <div class="brief-header-meta">
      <span>Account: {account_id}</span>
      <span>Version: {version}</span>
      <span>Generated: {generated_at}</span>
    </div>
  </div>
  <div class="content">

    <!-- Action Banner -->
    <div class="action-banner">
      <div>
        <div class="action-banner-label">{action_label}</div>
        <div style="font-size:12px;color:{action_text};opacity:0.8;">Confidence: {confidence:.0%}</div>
      </div>
      <div class="action-banner-score">{overall_score}</div>
    </div>

    <!-- Scores -->
    <div class="section">
      <div class="section-title">Scores</div>
      <div class="scores-grid">
        <div class="score-card">{gauges_html}</div>
        <div class="score-card">
          <div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:8px;">RECOMMENDATION</div>
          <div style="font-size:13px;color:#475569;">{_safe(rec_explanation)}</div>
          {"" if not rec_channel else f'<div style="margin-top:8px;font-size:12px;"><span style="font-weight:600;color:#64748b;">Best Channel:</span> <span style="color:#1e293b;">{rec_channel}</span></div>'}
          {"" if not rec_contact_name else f'<div style="margin-top:4px;font-size:12px;"><span style="font-weight:600;color:#64748b;">First Contact:</span> <span style="color:#1e293b;">{rec_contact_name}</span></div>'}
          {"" if not rec_multi else '<div style="margin-top:4px;font-size:11px;color:#7c3aed;font-weight:600;">Multi-threading recommended</div>'}
        </div>
      </div>
    </div>

    <!-- 1. Snapshot -->
    <div class="section">
      <div class="section-title">1. Account Snapshot</div>
      <div class="section-text">{snapshot}</div>
    </div>

    <!-- 2. Why This Account -->
    <div class="section">
      <div class="section-title">2. Why This Account</div>
      <div class="section-text">{_safe(why_account) if why_account else '<span style="color:#94a3b8;">Not available.</span>'}</div>
    </div>

    <!-- 3. Why Now -->
    <div class="section">
      <div class="section-title">3. Why Now</div>
      <div class="section-text">{_safe(why_now) if why_now else '<span style="color:#94a3b8;">Not available.</span>'}</div>
      <div style="margin-top:10px;display:flex;flex-wrap:wrap;">{signals_html}</div>
    </div>

    <!-- 4. Pain Points -->
    <div class="section">
      <div class="section-title">4. Likely Pain Points</div>
      {pains_html}
    </div>

    <!-- 5. Recommended Contacts -->
    <div class="section">
      <div class="section-title">5. Recommended Contacts</div>
      {contacts_html}
    </div>

    <!-- 6. Talk Tracks / Persona Angles -->
    <div class="section">
      <div class="section-title">6. Talk Tracks</div>
      {angles_html}
    </div>

    <!-- 7. Risks & Unknowns -->
    <div class="section">
      <div class="section-title">7. Risks &amp; Unknowns</div>
      {risks_html}
    </div>

    <!-- 8. Action Recommendation -->
    <div class="section">
      <div class="section-title">8. Action Recommendation</div>
      <div style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;">
        <div style="font-size:13px;color:#475569;">{_safe(rec_explanation)}</div>
        {"" if not rec_channel else f'<div style="margin-top:8px;font-size:12px;"><span style="font-weight:600;color:#64748b;">Channel:</span> {rec_channel}</div>'}
        {"" if not rec_contact_name else f'<div style="margin-top:4px;font-size:12px;"><span style="font-weight:600;color:#64748b;">Start with:</span> {rec_contact_name}</div>'}
      </div>
    </div>

  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# No-data placeholder
# ---------------------------------------------------------------------------


def render_no_data(account_id: str) -> str:
    """Return placeholder HTML when no brief data exists."""
    safe_id = _safe(account_id)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniGTM - No Data</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f4f6f9;
  color: #1e293b;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 16px;
}}
.empty {{
  text-align: center;
  max-width: 280px;
}}
.icon {{
  width: 48px;
  height: 48px;
  background: #f1f5f9;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
  font-size: 20px;
  color: #94a3b8;
}}
.title {{
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}}
.subtitle {{
  font-size: 12px;
  color: #94a3b8;
}}
</style>
</head>
<body>
<div class="empty">
  <div class="icon">?</div>
  <div class="title">No qualification data</div>
  <div class="subtitle">Account {safe_id} has not been qualified yet. Run the qualification pipeline to generate a seller brief.</div>
</div>
</body>
</html>"""
