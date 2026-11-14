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
    # Versioned name: a schema change means a new index, then a config switch (design 03).
    search_index: str = "far-chunks-v1"
    # Must match at ingest AND query time, or Search rejects the vector (design 03 §4).
    embed_dimensions: int = 512
    key_vault_url: AnyHttpUrl
    storage_account_url: AnyHttpUrl
    storage_container: str = "far-raw"

    smoke_timeout_s: float = 20.0

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
