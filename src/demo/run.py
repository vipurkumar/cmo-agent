"""Run the CMO Agent demo end-to-end.

Usage:
    python -m src.demo.run

No external services required — everything runs in-memory.
"""

from __future__ import annotations

import asyncio
import sys

from src.demo.bootstrap import build_demo_graph, create_demo_state, init_demo
from src.logger import log


def _print_banner() -> None:
    print("\n" + "=" * 70)
    print("  CMO Agent — Demo Mode")
    print("  Full agent loop with mock tools • No external services needed")
    print("=" * 70 + "\n")


def _print_node(node_name: str, data: dict) -> None:
    print(f"\n{'─' * 60}")
    print(f"  Node: {node_name}")
    print(f"{'─' * 60}")

    if node_name == "account_selector":
        acct = data.get("current_account")
        contact = data.get("current_contact")
        if acct:
            print(f"  Selected: {acct.company_name} ({acct.domain})")
        if contact:
            print(f"  Contact:  {contact.first_name} {contact.last_name} <{contact.email}>")

    elif node_name == "researcher":
        enrichment = data.get("enrichment")
        if enrichment:
            print(f"  Summary:  {enrichment.company_summary[:120]}...")
            print(f"  News:     {len(enrichment.recent_news)} items")
            print(f"  Hooks:    {len(enrichment.personalization_hooks)} found")
            print(f"  Tech:     {', '.join(enrichment.technologies)}")

    elif node_name == "personaliser":
        draft = data.get("draft_email")
        if draft:
            print(f"  Subject:  {draft.subject_line}")
            print(f"  Score:    {draft.personalization_score}")
            body_preview = draft.body.replace("\n", " ")[:150]
            print(f"  Preview:  {body_preview}...")

    elif node_name == "approval_gate":
        print(f"  Status:   {data.get('approval_status', 'unknown')}")

    elif node_name == "sender":
        msgs = data.get("sent_messages", [])
        if msgs:
            last = msgs[-1]
            print(f"  Sent to:  {last.contact_id}")
            print(f"  Stage:    {last.stage}")
            print(f"  Status:   {last.status}")

    elif node_name == "reply_monitor":
        reply = data.get("reply_analysis")
        if reply:
            print(f"  Intent:   {reply.intent} (confidence: {reply.confidence})")
            print(f"  Action:   {reply.suggested_action}")
            print(f"  Reason:   {reply.reasoning[:100]}...")
        else:
            print("  No reply detected")

    elif node_name == "router":
        print(f"  Continue: {data.get('should_continue', False)}")
        if "current_stage" in data:
            print(f"  Stage:    {data['current_stage']}")

    elif node_name == "notify_sales":
        print("  Sales team notified via Slack + HubSpot")

    elif node_name == "memory_updater":
        print("  Campaign learnings stored, state reset for next account")

    elif node_name == "enrichment_retry":
        print(f"  Error cleared, retrying enrichment")

    elif node_name == "unsubscribe_handler":
        print("  Contact unsubscribed, sequence stopped")

    if data.get("error"):
        print(f"  ERROR:    {data['error']}")


async def run_demo() -> None:
    """Execute the full demo flow with streaming output."""
    _print_banner()

    print("Initializing demo mode (patching all external deps)...")
    init_demo()

    print("Building agent graph (in-memory checkpointing)...")
    graph = build_demo_graph()

    print("Creating demo state (2 sample accounts, 1 campaign)...")
    state = create_demo_state()

    print("\nStarting agent loop...\n")

    config = {"configurable": {"thread_id": state["thread_id"]}}

    async for event in graph.astream(state, config=config):
        for node_name, node_output in event.items():
            if node_name == "__end__":
                continue
            _print_node(node_name, node_output or {})

    print(f"\n{'=' * 70}")
    print("  Demo complete!")
    print(f"{'=' * 70}\n")


def main() -> None:
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
