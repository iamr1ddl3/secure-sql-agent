"""Settings from environment (.env in dev). See .env.example."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database: the service only ever uses the low-privilege login role.
    agent_database_url: str = Field(description="postgresql://sql_agent_login.<ref>:<pw>@<pooler>:6543/postgres")
    identity_hmac_key_id: str = "k1"
    identity_hmac_key: str = Field(min_length=32, description="Same secret as app.identity_keys row k1")
    row_cap: int = 1000
    statement_timeout_ms: int = 5000

    # Identity (Supabase Auth)
    supabase_url: str
    supabase_jwt_secret: str | None = None  # legacy HS256 projects only

    # Models (all via OpenRouter, so cost per query is comparable across vendors)
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    models_file: str = "config/models.yaml"
    default_model: str = "primary"

    # Observability
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
