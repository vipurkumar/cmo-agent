-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Workspaces
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'pro',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    key_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT 'default',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_ws ON api_keys(workspace_id);

-- Workspace settings
CREATE TABLE IF NOT EXISTS workspace_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    daily_send_limit INTEGER NOT NULL DEFAULT 100,
    approval_required BOOLEAN NOT NULL DEFAULT true,
    sending_hours_start INTEGER NOT NULL DEFAULT 8,
    sending_hours_end INTEGER NOT NULL DEFAULT 18,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_workspace_settings_ws ON workspace_settings(workspace_id);

-- Campaigns
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    icp_criteria JSONB NOT NULL DEFAULT '{}',
    sequence_config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_campaigns_ws ON campaigns(workspace_id);

-- Accounts
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    company_name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    employee_count INTEGER,
    revenue BIGINT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_accounts_ws ON accounts(workspace_id);

-- Contacts
CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    account_id UUID NOT NULL REFERENCES accounts(id),
    email TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    role TEXT,
    linkedin_url TEXT,
    phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contacts_ws ON contacts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_contacts_account ON contacts(account_id);

-- Sequences
CREATE TABLE IF NOT EXISTS sequences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    stage_number INTEGER NOT NULL,
    template_id TEXT,
    delay_days INTEGER NOT NULL DEFAULT 3,
    channel TEXT NOT NULL DEFAULT 'email',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sequences_ws ON sequences(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sequences_campaign ON sequences(campaign_id);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    contact_id UUID NOT NULL REFERENCES contacts(id),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    subject TEXT,
    body TEXT,
    stage INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    sent_at TIMESTAMPTZ,
    reply_text TEXT,
    reply_intent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_ws ON messages(workspace_id);
CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id);
CREATE INDEX IF NOT EXISTS idx_messages_campaign ON messages(campaign_id);

-- Campaign memory (pgvector)
CREATE TABLE IF NOT EXISTS campaign_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    campaign_id UUID NOT NULL REFERENCES campaigns(id),
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_campaign_memories_ws ON campaign_memories(workspace_id);
CREATE INDEX IF NOT EXISTS idx_campaign_memories_campaign ON campaign_memories(campaign_id);

-- Account scores (qualification pipeline)
CREATE TABLE IF NOT EXISTS account_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    account_id UUID NOT NULL,
    icp_fit_score INTEGER NOT NULL,
    pain_fit_score INTEGER NOT NULL,
    timing_score INTEGER NOT NULL,
    overall_priority_score INTEGER NOT NULL,
    fit_reasons JSONB NOT NULL DEFAULT '[]',
    non_fit_reasons JSONB NOT NULL DEFAULT '[]',
    confidence_score DOUBLE PRECISION NOT NULL,
    is_disqualified BOOLEAN NOT NULL DEFAULT false,
    disqualify_reason TEXT,
    scoring_version TEXT NOT NULL DEFAULT 'v1',
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_account_scores_ws_account ON account_scores(workspace_id, account_id);

-- Signals
CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    account_id UUID NOT NULL,
    signal_type TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_fact TEXT NOT NULL,
    possible_implication TEXT NOT NULL,
    event_date TIMESTAMPTZ,
    recency_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    reliability_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_signals_ws_account ON signals(workspace_id, account_id);

-- Pain hypothesis records
CREATE TABLE IF NOT EXISTS pain_hypothesis_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    account_id UUID NOT NULL,
    brief_id UUID NOT NULL,
    pain_type TEXT NOT NULL,
    score INTEGER NOT NULL,
    supporting_facts JSONB NOT NULL DEFAULT '[]',
    inferences JSONB NOT NULL DEFAULT '[]',
    unknowns JSONB NOT NULL DEFAULT '[]',
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pain_hypothesis_records_ws_account ON pain_hypothesis_records(workspace_id, account_id);

-- Seller brief records
CREATE TABLE IF NOT EXISTS seller_brief_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    account_id UUID NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    brief_json JSONB NOT NULL,
    action_type TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL,
    model_version TEXT NOT NULL DEFAULT 'v1',
    prompt_version TEXT NOT NULL DEFAULT 'v1',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_seller_brief_records_ws_account ON seller_brief_records(workspace_id, account_id);
CREATE INDEX IF NOT EXISTS idx_seller_brief_records_ws_action ON seller_brief_records(workspace_id, action_type);

-- Feedback events
CREATE TABLE IF NOT EXISTS feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    recommendation_id UUID NOT NULL,
    recommendation_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    correction TEXT,
    model_version TEXT NOT NULL DEFAULT 'v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_events_ws_rec ON feedback_events(workspace_id, recommendation_id);

-- Outcome events
CREATE TABLE IF NOT EXISTS outcome_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    account_id UUID NOT NULL,
    opportunity_id UUID,
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outcome_events_ws_account ON outcome_events(workspace_id, account_id);

-- Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    notification_type TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notifications_ws ON notifications(workspace_id);
CREATE INDEX IF NOT EXISTS idx_notifications_ws_read ON notifications(workspace_id, read);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    email TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, email)
);
CREATE INDEX IF NOT EXISTS idx_users_ws ON users(workspace_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Workspace invitations
CREATE TABLE IF NOT EXISTS workspace_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    invited_by UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days')
);
CREATE INDEX IF NOT EXISTS idx_invitations_ws ON workspace_invitations(workspace_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email ON workspace_invitations(email);

-- Webhook subscriptions
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    url TEXT NOT NULL,
    events TEXT[] NOT NULL DEFAULT '{}',
    secret TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhook_subs_ws ON webhook_subscriptions(workspace_id);

-- Webhook delivery log
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES webhook_subscriptions(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    response_status INTEGER,
    response_body TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_ws ON webhook_deliveries(workspace_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_retry ON webhook_deliveries(next_retry_at) WHERE status = 'pending';

-- User credentials (email/password auth for dashboard login)
CREATE TABLE IF NOT EXISTS user_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_credentials_email ON user_credentials(email);

-- Login sessions
CREATE TABLE IF NOT EXISTS login_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    email TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_login_sessions_token ON login_sessions(token);
