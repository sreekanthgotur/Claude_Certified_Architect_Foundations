from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    anthropic_model_classifier: str = "claude-haiku-5-5"
    anthropic_model_tier1: str = "claude-sonnet-5-5"
    anthropic_model_tier2: str = "claude-opus-5-5"
    anthropic_model_tier3: str = "claude-opus-5-5"

    aws_region: str = "us-east-1"
    dynamodb_session_table: str = "ccar-sessions"
    s3_documents_bucket: str = "ccar-documents"
    s3_uploads_bucket: str = "ccar-uploads"

    mcp_crm_url: str = "https://mcp.internal/crm"
    mcp_orders_url: str = "https://mcp.internal/orders"
    mcp_knowledge_url: str = "https://mcp.internal/knowledge"
    mcp_billing_url: str = "https://mcp.internal/billing"

    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    environment: str = "dev"
    refund_approval_threshold: float = 100.0
    max_account_modifications_per_session: int = 3
    dedup_similarity_threshold: float = 0.85

    model_config = {"env_file": ".env.local", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
