CREATE TABLE IF NOT EXISTS session_events (
    id UUID,
    workspace_id String,
    session_id String,
    event_type String,
    metadata String,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (workspace_id, created_at);

CREATE TABLE IF NOT EXISTS cost_events (
    id UUID,
    workspace_id String,
    task String,
    model String,
    input_tokens UInt32,
    output_tokens UInt32,
    cost_usd Float64,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (workspace_id, created_at);

-- OmniGTM qualification analytics

CREATE TABLE IF NOT EXISTS qualification_events (
    id UUID,
    workspace_id String,
    account_id String,
    event_type String,
    icp_fit_score UInt8,
    pain_fit_score UInt8,
    timing_score UInt8,
    overall_priority_score UInt8,
    action_type String,
    confidence_score Float64,
    scoring_version String,
    metadata String,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (workspace_id, account_id, created_at);

CREATE TABLE IF NOT EXISTS recommendation_events (
    id UUID,
    workspace_id String,
    account_id String,
    brief_id String,
    action_type String,
    overall_score UInt8,
    confidence_score Float64,
    contact_count UInt8,
    pain_count UInt8,
    signal_count UInt8,
    model_version String,
    prompt_version String,
    user_action String,
    metadata String,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (workspace_id, account_id, created_at);

CREATE TABLE IF NOT EXISTS feedback_analytics (
    id UUID,
    workspace_id String,
    recommendation_id String,
    recommendation_type String,
    user_id String,
    action_taken String,
    model_version String,
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (workspace_id, created_at);
