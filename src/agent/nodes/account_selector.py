"""account_selector node — picks the next account from the batch to process.

Sets current_account, current_contact, and resets current_stage to 1.
"""

from __future__ import annotations

from src.agent.state import OutboundState
from src.logger import log


async def account_selector(state: OutboundState) -> dict:
    """Select the next unprocessed account from state["accounts"].

    On first invocation current_account is None, so we pick accounts[0].
    On subsequent invocations (after memory_updater resets current_account),
    we advance to the next account in the list.
    """
    thread_id = state["thread_id"]
    workspace_id = state["workspace_id"]
    log.info("account_selector.start", thread_id=thread_id, workspace_id=workspace_id)

    accounts = state.get("accounts", [])
    contacts = state.get("contacts", [])
    current = state.get("current_account")

    if not accounts:
        log.warning(
            "account_selector.no_accounts",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"should_continue": False}

    # Determine which account to pick next
    if current is None:
        next_idx = 0
    else:
        current_idx = next(
            (i for i, a in enumerate(accounts) if a.id == current.id),
            -1,
        )
        next_idx = current_idx + 1

    if next_idx >= len(accounts):
        log.info(
            "account_selector.all_processed",
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        return {"should_continue": False}

    next_account = accounts[next_idx]

    # Find the primary contact for this account
    account_contacts = [c for c in contacts if c.account_id == next_account.id]
    next_contact = account_contacts[0] if account_contacts else None

    log.info(
        "account_selector.complete",
        thread_id=thread_id,
        workspace_id=workspace_id,
        account_id=next_account.id,
        company_name=next_account.company_name,
    )

    return {
        "current_account": next_account,
        "current_contact": next_contact,
        "current_stage": 1,
        "enrichment": None,
        "draft_email": None,
        "approval_status": None,
        "reply_analysis": None,
        "error": None,
        "should_continue": True,
    }
