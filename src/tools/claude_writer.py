"""ClaudeWriterTool — generates personalized email copy using call_claude().

IMPORTANT: This tool MUST use call_claude() from budget.py. NEVER call
the Anthropic SDK directly.
"""

from __future__ import annotations

import json
from typing import Any

from src.config import settings
from src.llm.budget import call_claude
from src.logger import log
from src.ratelimit.bucket import RateLimiter
from src.tools.base import BaseTool


class ClaudeWriterTool(BaseTool):
    """Generates personalized email copy using the central LLM gateway.

    Input: research_data, template, personalization_hooks.
    Output: dict with ``subject`` and ``body`` keys.
    """

    def __init__(self, rate_limiter: RateLimiter) -> None:
        super().__init__(rate_limiter)

    async def run(
        self,
        research_data: dict[str, Any],
        template: str,
        personalization_hooks: list[str],
        workspace_id: str,
        plan: str,
    ) -> dict[str, str]:
        """Generate a personalised email subject and body.

        Parameters
        ----------
        research_data:
            Dict of research findings (company info, news, LinkedIn data, etc.).
        template:
            Base email template with placeholder markers.
        personalization_hooks:
            List of specific hooks/angles to weave into the copy.
        workspace_id:
            Tenant identifier for rate limiting and logging.
        plan:
            Billing plan of the workspace.

        Returns
        -------
        dict[str, str]
            ``{"subject": "...", "body": "..."}``
        """
        log.info(
            "claude_writer.start",
            workspace_id=workspace_id,
            hook_count=len(personalization_hooks),
        )

        # 1. Rate limit check FIRST (uses the "claude" resource bucket)
        await self.rate_limiter.enforce(workspace_id, "claude", plan)

        # 2. Build prompts
        system_prompt = (
            "You are an expert B2B email copywriter. Write concise, "
            "personalized cold outreach emails that feel human and drive replies. "
            "Output valid JSON with exactly two keys: \"subject\" and \"body\". "
            "No markdown, no extra keys."
        )

        user_prompt = (
            f"## Research Data\n{json.dumps(research_data, indent=2)}\n\n"
            f"## Template\n{template}\n\n"
            f"## Personalization Hooks\n"
            + "\n".join(f"- {hook}" for hook in personalization_hooks)
            + "\n\nGenerate a personalized email based on the template and research. "
            "Return JSON: {\"subject\": \"...\", \"body\": \"...\"}"
        )

        # 3. Call Claude through the central gateway — NEVER call anthropic directly
        raw_response = await call_claude(
            task="email_generation",
            system=system_prompt,
            user=user_prompt,
            workspace_id=workspace_id,
            model=settings.CLAUDE_MODEL,
        )

        # 4. Parse the JSON response
        try:
            result = json.loads(raw_response)
        except json.JSONDecodeError:
            log.warning(
                "claude_writer.json_parse_failed",
                workspace_id=workspace_id,
                raw_response=raw_response[:200],
            )
            # Fallback: treat entire response as the body
            result = {"subject": "Follow-up", "body": raw_response}

        email: dict[str, str] = {
            "subject": result.get("subject", ""),
            "body": result.get("body", ""),
            "personalization_score": result.get("personalization_score", 0.0),
        }

        log.info(
            "claude_writer.complete",
            workspace_id=workspace_id,
            subject_length=len(email["subject"]),
            body_length=len(email["body"]),
        )

        return email
