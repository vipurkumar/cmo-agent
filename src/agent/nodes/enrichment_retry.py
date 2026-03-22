"""enrichment_retry node — handles enrichment failures with retry logic.

Increments a retry counter and clears the error so the researcher node
can be re-invoked. If max retries are exceeded, marks should_continue
as False to stop the sequence for this account.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.logger import log

MAX_ENRICHMENT_RETRIES = 3


async def enrichment_retry(state: OutboundState) -> dict:
    """Handle enrichment failure — retry or give up."""
    thread_id = state["thread_id"]
    account = state["current_account"]
    workspace_id = account.workspace_id if account else state.get("workspace_id", "")
    log.info("enrichment_retry.start", thread_id=thread_id, workspace_id=workspace_id)

    # Track retry count via metadata on the current account
    # We use a convention: state error string may contain retry info,
    # but we track via a simple counter approach using account metadata.
    current_account = state.get("current_account")
    retry_count = 0

    if current_account and current_account.metadata:
        retry_count = current_account.metadata.get("enrichment_retries", 0)

    retry_count += 1

    if retry_count > MAX_ENRICHMENT_RETRIES:
        log.warning(
            "enrichment_retry.max_retries_exceeded",
            thread_id=thread_id,
            workspace_id=workspace_id,
            retry_count=retry_count,
        )
        return {
            "error": f"Enrichment failed after {MAX_ENRICHMENT_RETRIES} retries",
            "enrichment": None,
            "should_continue": False,
        }

    # Update retry count in account metadata
    if current_account:
        updated_metadata = dict(current_account.metadata) if current_account.metadata else {}
        updated_metadata["enrichment_retries"] = retry_count
        current_account = current_account.model_copy(update={"metadata": updated_metadata})

    log.info(
        "enrichment_retry.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        retry_count=retry_count,
    )

    return {
        "error": None,
        "enrichment": None,
        "current_account": current_account,
    }
