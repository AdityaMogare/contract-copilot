"""One credential, one client per service, created once at startup (design 01 §6).

Why shared: DefaultAzureCredential caches tokens per scope in memory. A new credential per
request would re-run the credential chain (an `az` subprocess locally, an identity-endpoint
call in Azure) on every request, and leak HTTP sessions.
"""

from dataclasses import dataclass

from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.keyvault.secrets.aio import SecretClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.storage.blob.aio import BlobServiceClient
from openai import AsyncAzureOpenAI

from app.config import Settings

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


@dataclass
class Clients:
    credential: DefaultAzureCredential
    openai: AsyncAzureOpenAI
    search: SearchIndexClient
    keyvault: SecretClient
    blob: BlobServiceClient


def build_clients(settings: Settings) -> Clients:
    # Locally: resolves to AzureCliCredential (your az login). In Container Apps:
    # ManagedIdentityCredential, picking the identity from AZURE_CLIENT_ID.
    credential = DefaultAzureCredential()
    return Clients(
        credential=credential,
        openai=AsyncAzureOpenAI(
            azure_endpoint=str(settings.azure_openai_endpoint),
            api_version=settings.azure_openai_api_version,
            azure_ad_token_provider=get_bearer_token_provider(credential, COGNITIVE_SCOPE),
            max_retries=0,  # smoke reports the first result; retries would hide 401/429
        ),
        search=SearchIndexClient(str(settings.search_endpoint), credential),
        keyvault=SecretClient(str(settings.key_vault_url), credential),
        blob=BlobServiceClient(str(settings.storage_account_url), credential=credential),
    )


async def close_clients(clients: Clients) -> None:
    await clients.openai.close()
    await clients.search.close()
    await clients.keyvault.close()
    await clients.blob.close()
    await clients.credential.close()
