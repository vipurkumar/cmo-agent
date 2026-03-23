from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "CMO_", "env_file": ".env", "extra": "ignore"}

    # LLM
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_API_KEY: str = ""

    # Database (points to PgBouncer, NOT PostgreSQL directly)
    DATABASE_URL: str = "postgresql+asyncpg://localhost:6432/cmo"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_KEY_PREFIX: str = "cmo:"

    # ClickHouse
    CLICKHOUSE_URL: str = "clickhouse://localhost:9000/cmo"

    # n8n integration
    HMAC_SECRET: str = ""
    N8N_WEBHOOK_BASE_URL: str = "http://localhost:5678/webhook"

    # Agent defaults
    MAX_ACCOUNTS_PER_BATCH: int = 20
    SEQUENCE_MAX_STAGES: int = 3

    # External API keys
    APOLLO_API_KEY: str = ""
    CLAY_API_KEY: str = ""
    LINKEDIN_API_KEY: str = ""
    HUBSPOT_API_KEY: str = ""
    ZOHO_CLIENT_ID: str = ""
    ZOHO_CLIENT_SECRET: str = ""
    ZOHO_REFRESH_TOKEN: str = ""
    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""

    # External API base URLs
    APOLLO_BASE_URL: str = "https://api.apollo.io/v1"
    CLAY_BASE_URL: str = "https://api.clay.com/v1"

    # Embeddings
    EMBEDDING_PROVIDER: str = "anthropic"  # "anthropic" or "openai"
    EMBEDDING_MODEL: str = "voyage-3"  # or "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1024  # voyage-3 default; openai uses 1536
    OPENAI_API_KEY: str = ""  # only needed if EMBEDDING_PROVIDER = "openai"

    # Apollo enrichment
    USE_APOLLO_ENRICHMENT: bool = True
    APOLLO_MCP_ENABLED: bool = False  # set True when running inside Claude Code

    # Clay enrichment (optional — requires CLAY_API_KEY)
    USE_CLAY_ENRICHMENT: bool = False

    # Draft-only mode — generate emails without sending (no n8n/Slack needed)
    OUTBOUND_DRAFT_ONLY: bool = True

    # Demo mode — runs full agent loop with mock tools, no external deps
    DEMO_MODE: bool = False

    # Admin API key for workspace provisioning
    ADMIN_API_KEY: str = ""

    # CORS
    CORS_ALLOWED_ORIGINS: list[str] = ["*"]

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "info"


settings = Settings()
