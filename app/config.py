"""Typed configuration. Values come from env vars, or from .env locally (gitignored).

Nothing here is a secret: endpoints and deployment names only. Auth is Entra tokens via
DefaultAzureCredential, so there's no key to configure (design 01 §6).
"""

from functools import lru_cache

from pydantic import AnyHttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_endpoint: AnyHttpUrl
    # gpt-5-mini needs max_completion_tokens / reasoning_effort, which this version accepts.
    azure_openai_api_version: str = "2025-04-01-preview"
    chat_deployment: str = "chat"  # deployment NAMES, never model names (CLAUDE.md)
    embed_deployment: str = "embed"

    search_endpoint: AnyHttpUrl
    # The app queries the ALIAS; ingestion creates/writes the versioned index behind it.
    # A schema change builds v2, then repoints the alias (design 04, infra step 7b).
    search_index: str = "far-chunks"
    search_index_version: str = "far-chunks-v2"   # design 05
    # Must match at ingest AND query time, or Search rejects the vector (design 03 §4).
    embed_dimensions: int = 512
    key_vault_url: AnyHttpUrl
    storage_account_url: AnyHttpUrl
    storage_container: str = "far-raw"

    smoke_timeout_s: float = 20.0

    # RAG (design 04). Starting values for the baseline, not tuned ones.
    rag_top_k: int = 8
    # RRF weight of the vector query vs BM25 (1.0 = equal). Design 05: 3.0 won on dev (hit@8 16→19/19).
    rag_vector_weight: float = 3.0
    rag_reasoning_effort: str = "low"
    rag_max_completion_tokens: int = 2000
    rag_deadline_s: float = 25.0
    max_question_chars: int = 1000

    # Not a secret once App Insights local auth is off (infra step 2b): ingestion needs an Entra token.
    applicationinsights_connection_string: str | None = None

    # Entra access-token validation (design 02 revision). Fail-closed: required unless the
    # environment explicitly says otherwise (local .env sets AUTH_REQUIRED=false).
    auth_required: bool = True
    auth_tenant_id: str | None = None
    auth_audience: str | None = None  # the app registration's appId (v2 tokens use it as `aud`)
    auth_scope: str = "access_as_user"

    @model_validator(mode="after")
    def _auth_config_complete(self) -> "Settings":
        if self.auth_required and not (self.auth_tenant_id and self.auth_audience):
            raise ValueError("AUTH_REQUIRED=true needs AUTH_TENANT_ID and AUTH_AUDIENCE")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
