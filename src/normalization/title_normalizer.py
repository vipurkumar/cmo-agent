"""Job title normalization — function + seniority extraction.

Uses Haiku for batch title normalization (too many variations for rules).
Falls back to rule-based heuristics when LLM is unavailable.
"""

from __future__ import annotations

import json
import re

from src.config import settings
from src.llm.budget import call_claude
from src.llm.prompts import SYSTEM_TITLE_NORMALIZER
from src.logger import log

# ---------------------------------------------------------------------------
# Rule-based fallback (used when LLM is unavailable or for common titles)
# ---------------------------------------------------------------------------

SENIORITY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(chief|c-suite|ceo|cfo|cto|coo|cro|cmo|cpo)\b", "C-Suite"),
    (r"\bsvp\b|senior vice president", "SVP"),
    (r"\bvp\b|vice president", "VP"),
    (r"\bsenior director\b", "Senior Director"),
    (r"\bdirector\b|\bhead of\b", "Director"),
    (r"\bsenior manager\b", "Senior Manager"),
    (r"\bmanager\b", "Manager"),
    (r"\bsenior\b(?!.*(?:director|manager|vice))", "Senior IC"),
    (r"\blead\b|\bprincipal\b|\bstaff\b", "Senior IC"),
]

FUNCTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(rev\s*ops|revenue operations)\b", "Revenue Operations"),
    (r"\bpricing\b", "Pricing"),
    (r"\b(finance|controller|accounting|treasury)\b", "Finance"),
    (r"\b(engineering|developer|software|sre|devops|platform|engineer)\b", "Engineering"),
    (r"\b(billing|payments|subscriptions)\b", "Finance"),
    (r"\b(product)\b(?!.*marketing)", "Product"),
    (r"\b(marketing|demand gen|growth|content|brand)\b", "Marketing"),
    (r"\b(sales|business development|account executive|sdr|bdr)\b", "Sales"),
    (r"\b(operations|ops)\b(?!.*revenue)", "Operations"),
    (r"\b(ceo|cfo|cto|coo|cro|cmo|cpo|president|founder)\b", "Executive"),
]


def _rule_based_normalize(title: str) -> dict[str, str]:
    """Fast rule-based title normalization."""
    title_lower = title.lower().strip()

    # Detect seniority
    seniority = "Unknown"
    for pattern, level in SENIORITY_PATTERNS:
        if re.search(pattern, title_lower):
            seniority = level
            break

    # Detect function
    function = "Other"
    for pattern, func in FUNCTION_PATTERNS:
        if re.search(pattern, title_lower):
            function = func
            break

    return {
        "original_title": title,
        "normalized_function": function,
        "normalized_seniority": seniority,
    }


# ---------------------------------------------------------------------------
# LLM-based normalization (Haiku, batched)
# ---------------------------------------------------------------------------


async def normalize_titles(
    titles: list[str],
    workspace_id: str,
    use_llm: bool = True,
) -> list[dict[str, str]]:
    """Normalize a batch of job titles into function + seniority.

    Parameters
    ----------
    titles:
        List of raw job title strings.
    workspace_id:
        Tenant ID for budget tracking.
    use_llm:
        If True, use Haiku for normalization. If False, use rule-based fallback.

    Returns
    -------
    List of dicts with original_title, normalized_function, normalized_seniority.
    """
    if not titles:
        return []

    if not use_llm:
        return [_rule_based_normalize(t) for t in titles]

    # Batch into groups of 20 for LLM efficiency
    results: list[dict[str, str]] = []
    for i in range(0, len(titles), 20):
        batch = titles[i : i + 20]
        try:
            batch_results = await _normalize_batch_llm(batch, workspace_id)
            results.extend(batch_results)
        except Exception:
            log.warning(
                "title_normalizer.llm_fallback",
                workspace_id=workspace_id,
                batch_size=len(batch),
            )
            results.extend(_rule_based_normalize(t) for t in batch)

    return results


async def _normalize_batch_llm(
    titles: list[str],
    workspace_id: str,
) -> list[dict[str, str]]:
    """Use Haiku to normalize a batch of titles."""
    titles_text = "\n".join(f"- {t}" for t in titles)

    raw = await call_claude(
        task="title_normalization",
        system=SYSTEM_TITLE_NORMALIZER,
        user=f"Normalize these job titles:\n\n{titles_text}",
        workspace_id=workspace_id,
        model=settings.CLAUDE_HAIKU_MODEL,
    )

    # Parse JSON response
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        parsed = [parsed]

    # Validate and fill gaps
    results: list[dict[str, str]] = []
    for i, title in enumerate(titles):
        if i < len(parsed) and isinstance(parsed[i], dict):
            results.append({
                "original_title": title,
                "normalized_function": parsed[i].get("normalized_function", "Other"),
                "normalized_seniority": parsed[i].get("normalized_seniority", "Unknown"),
            })
        else:
            results.append(_rule_based_normalize(title))

    return results
