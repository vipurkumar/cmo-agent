"""Demo bootstrap — patches all external dependencies so the agent runs in-memory."""

from __future__ import annotations

import uuid as _uuid

import httpx

from src.agent.state import Account, Campaign, Contact, OutboundState
from src.demo.infra import (
    DemoRateLimiter,
    demo_save_message,
    demo_session_factory,
    demo_store_embedding,
    demo_update_message_status,
)
from src.demo.llm import demo_call_claude
from src.demo.tools import (
    DemoApolloSearchTool,
    DemoHubSpotTool,
    DemoNewsSearchTool,
    DemoSlackApprovalTool,
)
from src.logger import log


def init_demo() -> None:
    """Monkey-patch all external dependencies for demo mode.

    Call this ONCE at startup before any graph invocation.
    """
    log.info("demo.init", msg="Patching tools, LLM, and DB for demo mode")

    demo_rl = DemoRateLimiter()

    # -- Patch tool factories in node modules --
    import src.agent.nodes.researcher as researcher_mod
    import src.agent.nodes.personaliser as personaliser_mod
    import src.agent.nodes.approval_gate as approval_gate_mod
    import src.agent.nodes.notify_sales as notify_sales_mod

    researcher_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]
    researcher_mod._get_tools = lambda: (  # type: ignore[attr-defined]
        DemoApolloSearchTool(demo_rl),
        DemoNewsSearchTool(demo_rl),
    )

    personaliser_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]
    # personaliser uses ClaudeWriterTool which calls call_claude() internally,
    # so patching call_claude is sufficient — but we still need the rate limiter
    personaliser_mod.init_tools(demo_rl)

    approval_gate_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]
    approval_gate_mod._get_tool = lambda: DemoSlackApprovalTool(demo_rl)  # type: ignore[attr-defined]

    notify_sales_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]
    notify_sales_mod._get_tools = lambda: (  # type: ignore[attr-defined]
        DemoSlackApprovalTool(demo_rl),
        DemoHubSpotTool(demo_rl),
    )

    # -- Patch call_claude everywhere it was imported --
    import src.llm.budget as budget_mod
    import src.agent.nodes.researcher as researcher_ref
    import src.agent.nodes.reply_monitor as reply_monitor_ref
    import src.tools.claude_writer as claude_writer_ref

    budget_mod.call_claude = demo_call_claude  # type: ignore[assignment]
    researcher_ref.call_claude = demo_call_claude  # type: ignore[assignment]
    reply_monitor_ref.call_claude = demo_call_claude  # type: ignore[assignment]
    claude_writer_ref.call_claude = demo_call_claude  # type: ignore[assignment]

    # -- Patch DB functions --
    import src.db.queries as queries_mod
    import src.db.campaign_memory as memory_mod
    import src.agent.nodes.sender as sender_mod
    import src.agent.nodes.memory_updater as memory_updater_mod
    import src.agent.nodes.unsubscribe_handler as unsub_mod

    queries_mod.async_session_factory = demo_session_factory  # type: ignore[assignment]
    queries_mod.save_message = demo_save_message  # type: ignore[assignment]
    queries_mod.update_message_status = demo_update_message_status  # type: ignore[assignment]
    memory_mod.store_embedding = demo_store_embedding  # type: ignore[assignment]

    # Re-bind imports in node modules that imported at module level
    sender_mod.async_session_factory = demo_session_factory  # type: ignore[assignment]
    sender_mod.save_message = demo_save_message  # type: ignore[assignment]
    memory_updater_mod.async_session_factory = demo_session_factory  # type: ignore[assignment]
    memory_updater_mod.store_embedding = demo_store_embedding  # type: ignore[assignment]
    unsub_mod.async_session_factory = demo_session_factory  # type: ignore[assignment]
    unsub_mod.update_message_status = demo_update_message_status  # type: ignore[assignment]

    # -- Patch httpx in sender and reply_monitor (they call n8n directly) --
    import src.agent.nodes.reply_monitor as reply_monitor_mod

    _original_httpx_client = httpx.AsyncClient

    class _DemoHttpxClient:
        """Intercepts n8n webhook calls with demo responses."""

        def __init__(self, **kwargs):
            self._kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url: str, **kwargs) -> httpx.Response:
            if "/send-email" in url:
                return httpx.Response(
                    200,
                    json={"status": "sent", "message_id": "demo-sent-001"},
                )
            return httpx.Response(200, json={"status": "ok"})

        async def get(self, url: str, **kwargs) -> httpx.Response:
            if "/check-reply" in url:
                return httpx.Response(
                    200,
                    json={
                        "reply_text": (
                            "Thanks for reaching out! We've actually been evaluating "
                            "billing platforms internally — our current setup can't handle "
                            "the usage-based metering we need. MTZ360 looks like it could "
                            "be a strong fit. Can we set up a call this week to discuss?"
                        ),
                    },
                )
            return httpx.Response(200, json={})

    sender_mod.httpx.AsyncClient = _DemoHttpxClient  # type: ignore[assignment,misc]
    reply_monitor_mod.httpx.AsyncClient = _DemoHttpxClient  # type: ignore[assignment,misc]

    log.info("demo.init.complete", msg="All patches applied")


def build_demo_graph():
    """Build the LangGraph with in-memory checkpointing (no Redis needed)."""
    from langgraph.checkpoint.memory import MemorySaver

    from src.agent.graph import build_graph

    graph = build_graph()
    return graph.compile(checkpointer=MemorySaver())


def create_demo_state() -> OutboundState:
    """Create a demo state personalised for Monetize360's GTM team.

    Targets enterprises that need complex billing/monetization infrastructure —
    Monetize360's ICP: SaaS/fintech companies with usage-based or hybrid pricing
    models, AI workloads, or legacy billing systems they need to modernize.
    """
    workspace_id = "monetize360-demo"

    campaign = Campaign(
        id="camp-m360-001",
        workspace_id=workspace_id,
        name="Q2 Outbound — Enterprise Monetization Modernization",
        status="active",
        icp_criteria={
            "industry": "SaaS / Fintech / Healthcare IT",
            "employee_range": "200-5000",
            "billing_complexity": "Usage-based, hybrid, or outcome-driven pricing",
            "signals": ["AI product launch", "pricing model change", "Series B+", "legacy billing pain"],
        },
        sequence_config={
            "stages": [
                {"template": "Initial outreach — reference billing complexity and recent growth signals", "delay_days": 0},
                {"template": "Follow-up — share MTZ360 case study on reducing billing ops overhead", "delay_days": 3},
                {"template": "Break-up email — offer live monetization architecture review", "delay_days": 5},
            ],
            "slack_channel": "m360-approvals",
            "sales_channel": "m360-sales-alerts",
        },
    )

    accounts = [
        Account(
            id="acct-001",
            workspace_id=workspace_id,
            company_name="NovaPay Technologies",
            domain="novapaytech.com",
            industry="Embedded Finance / BaaS",
            employee_count=420,
            metadata={},
        ),
        Account(
            id="acct-002",
            workspace_id=workspace_id,
            company_name="MediCloud AI",
            domain="medicloud.ai",
            industry="Healthcare IT / AI",
            employee_count=280,
            metadata={},
        ),
    ]

    contacts = [
        Contact(
            id="contact-001",
            workspace_id=workspace_id,
            account_id="acct-001",
            email="r.kapoor@novapaytech.com",
            first_name="Ravi",
            last_name="Kapoor",
            role="VP of Product & Monetization",
            linkedin_url="https://linkedin.com/in/ravikapoor-demo",
        ),
        Contact(
            id="contact-002",
            workspace_id=workspace_id,
            account_id="acct-002",
            email="lisa.tang@medicloud.ai",
            first_name="Lisa",
            last_name="Tang",
            role="Head of Revenue Operations",
            linkedin_url="https://linkedin.com/in/lisatang-demo",
        ),
    ]

    return OutboundState(
        thread_id="m360-demo-thread-001",
        workspace_id=workspace_id,
        campaign=campaign,
        accounts=accounts,
        current_account=None,
        contacts=contacts,
        current_contact=None,
        enrichment=None,
        draft_email=None,
        approval_status=None,
        sent_messages=[],
        reply_analysis=None,
        current_stage=1,
        max_stages=3,
        error=None,
        should_continue=True,
    )


# ---------------------------------------------------------------------------
# Qualification graph demo helpers
# ---------------------------------------------------------------------------


def init_demo_qualification() -> None:
    """Monkey-patch all external dependencies for the qualification graph demo.

    Call this ONCE at startup before any qualification graph invocation.
    Keeps all existing outbound patches intact — this is additive.
    """
    log.info("demo.init_qualification", msg="Patching qualification graph dependencies")

    try:
        from src.demo.qualification_data import get_demo_qualification_response
    except ImportError:
        log.error("demo.init_qualification.import_error", msg="qualification_data module not found")
        raise

    demo_rl = DemoRateLimiter()

    # ------------------------------------------------------------------
    # 1. Patch call_claude — route qualification tasks through canned data,
    #    fall back to existing demo_call_claude for outbound tasks.
    # ------------------------------------------------------------------

    async def _demo_qualification_call_claude(
        task: str,
        system: str | list[dict],
        user: str,
        workspace_id: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        # Try qualification canned responses first (uses prompt text for company matching)
        result = get_demo_qualification_response(task, user)
        if result is None:
            # Also try matching against system prompt
            system_text = system if isinstance(system, str) else str(system)
            result = get_demo_qualification_response(task, system_text)
        if result is not None:
            log.info("demo.qualification.call_claude.hit", task=task, workspace_id=workspace_id)
            return result
        # Fall back to outbound demo responses
        return await demo_call_claude(
            task=task,
            system=system,
            user=user,
            workspace_id=workspace_id,
            model=model,
            max_tokens=max_tokens,
        )

    import src.llm.budget as budget_mod

    budget_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]

    # Patch call_claude in every qualification node that imports it at module level
    try:
        import src.agent.nodes.icp_scorer as icp_scorer_mod
        icp_scorer_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    try:
        import src.agent.nodes.signal_detector as signal_detector_mod
        signal_detector_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    try:
        import src.agent.nodes.contact_ranker as contact_ranker_mod
        contact_ranker_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    try:
        import src.agent.nodes.pain_inferrer as pain_inferrer_mod
        pain_inferrer_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    try:
        import src.agent.nodes.value_prop_matcher as value_prop_matcher_mod
        value_prop_matcher_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    try:
        import src.agent.nodes.brief_builder as brief_builder_mod
        brief_builder_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    # Patch title_normalizer — it also calls call_claude
    try:
        import src.normalization.title_normalizer as title_normalizer_mod
        title_normalizer_mod.call_claude = _demo_qualification_call_claude  # type: ignore[assignment]
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # 2. Patch campaign_memory — no pgvector in demo mode
    # ------------------------------------------------------------------

    async def _demo_search_similar(
        session=None, workspace_id="", campaign_id="", query_vector=None, top_k=5,
    ):
        return []

    try:
        import src.db.campaign_memory as memory_mod
        memory_mod.store_embedding = demo_store_embedding  # type: ignore[assignment]
        memory_mod.search_similar = _demo_search_similar  # type: ignore[assignment]
    except ImportError:
        pass

    # Also patch search_similar in value_prop_matcher (imported at module level)
    try:
        import src.agent.nodes.value_prop_matcher as vpm_mod
        vpm_mod.search_similar = _demo_search_similar  # type: ignore[assignment]
        vpm_mod._session_factory = demo_session_factory  # type: ignore[assignment]
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # 3. Patch tool init functions in nodes that use external tools
    # ------------------------------------------------------------------

    # data_ingester — uses CRMReaderTool; patch to return pre-populated data
    try:
        import src.agent.nodes.data_ingester as data_ingester_mod

        data_ingester_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]

        class _DemoCRMReader:
            """Returns empty contact lists — contacts are pre-populated in state."""
            async def run(self, **kwargs):
                return []

        data_ingester_mod._get_crm_reader = lambda: _DemoCRMReader()  # type: ignore[attr-defined]
    except ImportError:
        pass

    # signal_detector — uses NewsSearchTool and WebScraperTool
    try:
        import src.agent.nodes.signal_detector as sig_mod

        sig_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]

        class _DemoWebScraper:
            """Returns empty content — signals come from news + LLM classification."""
            async def run(self, **kwargs):
                return {"content": ""}

        sig_mod._get_tools = lambda: (  # type: ignore[attr-defined]
            DemoNewsSearchTool(demo_rl),
            _DemoWebScraper(),
        )
    except ImportError:
        pass

    # contact_ranker — no external tools, only call_claude (already patched)

    # value_prop_matcher — session factory already patched above

    # ------------------------------------------------------------------
    # 4. Patch writeback / review / gate nodes to be simple pass-throughs
    # ------------------------------------------------------------------

    # brief_reviewer — auto-approve everything in demo mode
    try:
        import src.agent.nodes.brief_reviewer as brief_reviewer_mod

        async def _demo_brief_reviewer(state) -> dict:
            log.info("demo.brief_reviewer.auto_approved",
                     workspace_id=state.get("workspace_id", ""))
            return {"approval_status": "auto_approved"}

        brief_reviewer_mod.brief_reviewer = _demo_brief_reviewer  # type: ignore[assignment]

        # Also replace the node function in the graph module so the graph
        # picks up the demo version when build_qualification_graph() is called
        try:
            import src.agent.nodes.brief_reviewer as br_ref
            br_ref.brief_reviewer = _demo_brief_reviewer  # type: ignore[assignment]
        except ImportError:
            pass
    except ImportError:
        pass

    # crm_writer — no-op pass-through
    try:
        import src.agent.nodes.crm_writer as crm_writer_mod

        async def _demo_crm_writer(state) -> dict:
            log.info("demo.crm_writer.noop",
                     workspace_id=state.get("workspace_id", ""))
            return {}

        crm_writer_mod.crm_writer = _demo_crm_writer  # type: ignore[assignment]
        crm_writer_mod._rate_limiter = demo_rl  # type: ignore[attr-defined]
        crm_writer_mod.async_session_factory = demo_session_factory  # type: ignore[assignment]
    except ImportError:
        pass

    # zoho_writer — no-op pass-through
    try:
        import src.agent.nodes.zoho_writer as zoho_writer_mod

        async def _demo_zoho_writer(state) -> dict:
            log.info("demo.zoho_writer.noop",
                     workspace_id=state.get("workspace_id", ""))
            return {}

        zoho_writer_mod.zoho_writer = _demo_zoho_writer  # type: ignore[assignment]
    except ImportError:
        pass

    # task_creator — no-op pass-through
    try:
        import src.agent.nodes.task_creator as task_creator_mod

        async def _demo_task_creator(state) -> dict:
            log.info("demo.task_creator.noop",
                     workspace_id=state.get("workspace_id", ""))
            return {}

        task_creator_mod.task_creator = _demo_task_creator  # type: ignore[assignment]
    except ImportError:
        pass

    # auto_outbound_gate — skip all guardrails, return not triggered
    try:
        import src.agent.nodes.auto_outbound_gate as auto_gate_mod

        async def _demo_auto_outbound_gate(state) -> dict:
            log.info("demo.auto_outbound_gate.skip",
                     workspace_id=state.get("workspace_id", ""))
            return {
                "auto_outbound_triggered": False,
                "auto_outbound_skip_reason": "demo_mode",
            }

        auto_gate_mod.auto_outbound_gate = _demo_auto_outbound_gate  # type: ignore[assignment]

        # Patch guardrails if they were imported — prevent RuntimeError
        auto_gate_mod._redis = None  # type: ignore[attr-defined]

        class _DemoKillSwitch:
            async def is_paused(self, workspace_id):
                return False, ""

        class _DemoBlocklistEnforcer:
            async def is_blocked(self, **kwargs):
                return False, ""

        class _DemoSendCapEnforcer:
            async def check_and_increment(self, **kwargs):
                pass

        auto_gate_mod._kill_switch = _DemoKillSwitch()  # type: ignore[attr-defined]
        auto_gate_mod._blocklist = _DemoBlocklistEnforcer()  # type: ignore[attr-defined]
        auto_gate_mod._send_caps = _DemoSendCapEnforcer()  # type: ignore[attr-defined]
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # 5. Patch DB session factory in queries module
    # ------------------------------------------------------------------
    try:
        import src.db.queries as queries_mod
        queries_mod.async_session_factory = demo_session_factory  # type: ignore[assignment]
    except ImportError:
        pass

    log.info("demo.init_qualification.complete", msg="All qualification patches applied")


def build_demo_qualification_graph():
    """Build the qualification graph with in-memory checkpointing (no Redis needed).

    IMPORTANT: call ``init_demo_qualification()`` BEFORE this function so that
    the monkey-patched node functions are picked up by the graph builder.
    """
    from langgraph.checkpoint.memory import MemorySaver

    import src.agent.qualification_graph as qg_mod

    # Re-bind node references in the qualification_graph module so the graph
    # builder uses the patched versions (the original imports are captured at
    # module load time, before monkey-patching).
    try:
        import src.agent.nodes.brief_reviewer as br_mod
        qg_mod.brief_reviewer = br_mod.brief_reviewer  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass

    try:
        import src.agent.nodes.crm_writer as cw_mod
        qg_mod.crm_writer = cw_mod.crm_writer  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass

    try:
        import src.agent.nodes.zoho_writer as zw_mod
        qg_mod.zoho_writer = zw_mod.zoho_writer  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass

    try:
        import src.agent.nodes.task_creator as tc_mod
        qg_mod.task_creator = tc_mod.task_creator  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass

    try:
        import src.agent.nodes.auto_outbound_gate as aog_mod
        qg_mod.auto_outbound_gate = aog_mod.auto_outbound_gate  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass

    graph = qg_mod.build_qualification_graph()
    return graph.compile(checkpointer=MemorySaver())


def create_demo_qualification_state():
    """Create a QualificationState with realistic demo data for two accounts.

    Returns a QualificationState dict ready to be passed to the compiled
    qualification graph. Includes pre-populated accounts, contacts, and
    sample knowledge base content.
    """
    from src.agent.state import QualificationState

    workspace_id = "demo-workspace"

    campaign = Campaign(
        id="demo-camp-1",
        workspace_id=workspace_id,
        name="OmniGTM Demo Campaign",
        status="active",
        icp_criteria={
            "industries": [
                "SaaS", "FinTech", "Embedded Finance", "BaaS",
                "Healthcare IT", "HealthTech",
            ],
            "company_size": {"min": 100, "max": 5000},
            "revenue_range": {"min": 10_000_000, "max": 500_000_000},
            "geographies": ["US", "EU", "IN"],
            "positive_signals": [
                "recent_funding", "pricing_page_change", "hiring_pricing",
                "usage_based_pricing", "enterprise_motion",
            ],
            "negative_signals": ["existing_customer", "competitor"],
            "disqualify_rules": ["employee_count_below_20", "pre_revenue"],
        },
        sequence_config={
            "review_channel": "gtm-reviews",
            "sales_channel": "m360-sales-alerts",
        },
    )

    raw_accounts = [
        {
            "id": "demo-acct-1",
            "company_name": "NovaPay Technologies",
            "domain": "novapay.io",
            "industry": "FinTech",
            "employee_count": 450,
            "revenue": 85_000_000,
            "metadata": {
                "geography": "US",
                "signals": ["recent_funding", "pricing_page_change", "hiring_pricing"],
            },
        },
        {
            "id": "demo-acct-2",
            "company_name": "MediCloud AI",
            "domain": "medicloud.ai",
            "industry": "HealthTech",
            "employee_count": 150,
            "revenue": 22_000_000,
            "metadata": {
                "geography": "US",
            },
        },
    ]

    # Build typed Account objects with IDs
    accounts = [
        Account(
            id=f"demo-acct-{i+1}",
            workspace_id=workspace_id,
            company_name=raw["company_name"],
            domain=raw.get("domain"),
            industry=raw.get("industry"),
            employee_count=raw.get("employee_count"),
            revenue=raw.get("revenue"),
            metadata=raw.get("metadata", {}),
        )
        for i, raw in enumerate(raw_accounts)
    ]

    # Pre-populated contacts for both companies
    contacts = [
        # NovaPay Technologies contacts
        Contact(
            id="np-contact-001",
            workspace_id=workspace_id,
            account_id="demo-acct-1",
            email="sarah@novapay.io",
            first_name="Sarah",
            last_name="Chen",
            role="VP Revenue Operations",
            linkedin_url="https://linkedin.com/in/sarahchen-demo",
        ),
        Contact(
            id="np-contact-002",
            workspace_id=workspace_id,
            account_id="demo-acct-1",
            email="marcus@novapay.io",
            first_name="Marcus",
            last_name="Johnson",
            role="Head of Pricing Strategy",
            linkedin_url="https://linkedin.com/in/marcusjohnson-demo",
        ),
        Contact(
            id="np-contact-003",
            workspace_id=workspace_id,
            account_id="demo-acct-1",
            email="raj@novapay.io",
            first_name="Raj",
            last_name="Patel",
            role="Sr. Director, Engineering — Billing & Payments",
            linkedin_url="https://linkedin.com/in/rajpatel-demo",
        ),
        # MediCloud AI contacts
        Contact(
            id="mc-contact-001",
            workspace_id=workspace_id,
            account_id="demo-acct-2",
            email="amy@medicloud.ai",
            first_name="Amy",
            last_name="Foster",
            role="VP Clinical Operations",
            linkedin_url="https://linkedin.com/in/amyfoster-demo",
        ),
        Contact(
            id="mc-contact-002",
            workspace_id=workspace_id,
            account_id="demo-acct-2",
            email="tom@medicloud.ai",
            first_name="Tom",
            last_name="Bradley",
            role="Director of Finance",
            linkedin_url="https://linkedin.com/in/tombradley-demo",
        ),
    ]

    # Sample knowledge base content
    kb_case_studies = [
        "FinTech Co (Series B, 300 employees): Switched from custom Stripe billing to MTZ360. "
        "Reduced billing ops overhead by 70% and eliminated revenue leakage within 6 weeks. "
        "Deal desk cycle time dropped by 52%.",
        "Healthcare SaaS (200 employees): Automated outcome-based billing for 200+ facilities. "
        "HIPAA-compliant billing pipeline reduced manual invoicing by 85%. "
        "Expanded from 50 to 200 facilities without adding finance headcount.",
    ]

    kb_battlecards = [
        "vs Zuora: MTZ360 is faster to implement (weeks not months), no-code pricing builder, "
        "and better suited for usage-based models. Zuora is enterprise-heavy and expensive.",
        "vs Chargebee: MTZ360 handles multi-dimensional pricing (usage + outcome + hybrid) "
        "natively. Chargebee struggles with non-subscription models.",
        "vs Build In-House: Average company spends 18 engineer-months building billing. "
        "MTZ360 deploys in 2-4 weeks. Total cost of ownership is 60% lower over 3 years.",
    ]

    kb_messaging = [
        "Core value prop: Stop building billing. Start monetizing. MTZ360 handles any pricing "
        "model — usage-based, hybrid, outcome-driven — so your team ships product, not invoices.",
        "ICP pain hook: If your engineering team is spending more than 10% of sprints on billing, "
        "you're building the wrong product.",
    ]

    thread_id = f"demo-qualify-{_uuid.uuid4().hex[:8]}"

    return QualificationState(
        thread_id=thread_id,
        workspace_id=workspace_id,
        campaign=campaign,
        raw_accounts=raw_accounts,
        accounts=accounts,
        current_account=None,
        contacts=contacts,
        ranked_contacts=[],
        buying_committee=None,
        signals=[],
        pain_hypotheses=[],
        value_props=[],
        account_score=None,
        seller_brief=None,
        action_recommendation=None,
        kb_case_studies=kb_case_studies,
        kb_battlecards=kb_battlecards,
        kb_messaging=kb_messaging,
        current_stage=1,
        approval_status=None,
        error=None,
        should_continue=True,
        auto_outbound_triggered=False,
        auto_outbound_skip_reason=None,
    )
