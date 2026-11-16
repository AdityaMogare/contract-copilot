"""One credential, one client per service, created once at startup (design 01 §6).

Why shared: DefaultAzureCredential caches tokens per scope in memory. A new credential per
request would re-run the credential chain (an `az` subprocess locally, an identity-endpoint
call in Azure) on every request, and leak HTTP sessions.
"""

from dataclasses import dataclass

import httpx

from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.keyvault.secrets.aio import SecretClient
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.storage.blob.aio import BlobServiceClient
from openai import AsyncAzureOpenAI

from app.config import Settings
from psycopg.rows import dict_row

from app.db import AGENT_OPTS, make_pool

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


@dataclass
class Clients:
    credential: DefaultAzureCredential
    openai: AsyncAzureOpenAI
    search: SearchIndexClient
    docs: SearchClient          # queries the alias (design 04)
    openai_rag: AsyncAzureOpenAI  # same endpoint/credential, but retries 429s
    keyvault: SecretClient
    blob: BlobServiceClient
    pg: object | None = None      # AsyncConnectionPool (design 06); None if Postgres isn't configured
    token_provider: object | None = None  # async bearer provider for the cognitiveservices scope (agent LLM)
    pg_agent: object | None = None  # design 08: schema agent, read-write; LangGraph needs autocommit + dict rows
    http: httpx.AsyncClient | None = None  # design 10: Content Safety + Language REST calls (no SDK needed)


def build_clients(settings: Settings) -> Clients:
    # Locally: resolves to AzureCliCredential (your az login). In Container Apps:
    # ManagedIdentityCredential, picking the identity from AZURE_CLIENT_ID.
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, COGNITIVE_SCOPE)
    return Clients(
        credential=credential,
        token_provider=token_provider,
        http=httpx.AsyncClient(timeout=settings.guard_timeout_s),
        pg=make_pool(settings, credential),
        pg_agent=make_pool(settings, credential, AGENT_OPTS, {"autocommit": True, "row_factory": dict_row}),
        openai=AsyncAzureOpenAI(
            azure_endpoint=str(settings.azure_openai_endpoint),
            api_version=settings.azure_openai_api_version,
            azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SCOPE),
            max_retries=0,  # smoke reports the first result; retries would hide 401/429
        ),
        search=SearchIndexClient(str(settings.search_endpoint), credential),
        docs=SearchClient(str(settings.search_endpoint), settings.search_index, credential),
        openai_rag=AsyncAzureOpenAI(
            azure_endpoint=str(settings.azure_openai_endpoint),
            api_version=settings.azure_openai_api_version,
            azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SCOPE),
            max_retries=2,   # /ask: honor 429 retry-after a couple of times, then 503 (design 04 hop 6)
            timeout=20.0,
        ),
        keyvault=SecretClient(str(settings.key_vault_url), credential),
        blob=BlobServiceClient(str(settings.storage_account_url), credential=credential),
    )


async def close_clients(clients: Clients) -> None:
    await clients.openai.close()
    if clients.http is not None:
        await clients.http.aclose()
    await clients.search.close()
    await clients.docs.close()
    await clients.openai_rag.close()
    await clients.keyvault.close()
    await clients.blob.close()
    for pool in (clients.pg, clients.pg_agent):
        if pool is not None:
            await pool.close()
    await clients.credential.close()
