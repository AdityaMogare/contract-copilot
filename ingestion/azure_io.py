"""Azure side of ingestion (design 03 hops 3, 5–10). Sync SDK clients: this is a batch CLI.

Identity: DefaultAzureCredential → locally AzureCliCredential (Aditya). Roles used:
Storage Blob Data Contributor (blob PUT), Search Service Contributor (index PUT),
Search Index Data Contributor (docs read/write), Cognitive Services OpenAI User (embeddings).
The app's managed identity has none of the write roles, on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI

from app.config import Settings
from ingestion.chunk import Chunk

EMBED_BATCH = 64
UPSERT_BATCH = 500


def index_schema(name: str, dims: int) -> SearchIndex:
    S = SearchFieldDataType
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=S.String, key=True),
            SearchableField(name="content", type=S.String, analyzer_name="en.microsoft"),
            SearchField(
                name="content_vector", type=S.Collection(S.Single), searchable=True,
                vector_search_dimensions=dims, vector_search_profile_name="hnsw-cosine",
                hidden=True, stored=False,   # never returned → no stored copy eating the 50 MB
            ),
            SimpleField(name="section", type=S.String, filterable=True, facetable=True),
            SimpleField(name="part", type=S.String, filterable=True, facetable=True),
            SimpleField(name="subpart", type=S.String, filterable=True, facetable=True),
            SearchableField(name="section_title", type=S.String, analyzer_name="en.microsoft"),
            SimpleField(name="paragraph_range", type=S.String),
            SimpleField(name="citation", type=S.String),
            SimpleField(name="url", type=S.String),
            SimpleField(name="amended_on", type=S.DateTimeOffset, filterable=True, sortable=True),
            SimpleField(name="snapshot_date", type=S.DateTimeOffset, filterable=True),
            SimpleField(name="content_hash", type=S.String, filterable=True),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw", parameters=HnswParameters(metric="cosine"))],
            profiles=[VectorSearchProfile(name="hnsw-cosine", algorithm_configuration_name="hnsw")],
        ),
    )


def _dt(d: date | None) -> str | None:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat() if d else None


def to_doc(c: Chunk, vector: list[float], snapshot: date) -> dict:
    return {
        "id": c.id, "content": c.content, "content_vector": vector,
        "section": c.section, "part": c.part, "subpart": c.subpart, "section_title": c.section_title,
        "paragraph_range": c.paragraph_range, "citation": c.citation, "url": c.url,
        "amended_on": _dt(c.amended_on), "snapshot_date": _dt(snapshot), "content_hash": c.content_hash,
    }


class IndexingFailed(RuntimeError):
    pass


def check_results(results) -> None:
    """A 207 Multi-Status is not an exception in the SDK: each IndexingResult says if it succeeded."""
    failed = [f"{r.key}: {r.status_code} {r.error_message}" for r in results if not r.succeeded]
    if failed:
        raise IndexingFailed(f"{len(failed)} documents failed: {failed[:5]}")


@dataclass
class AzureIO:
    settings: Settings
    blob: BlobServiceClient
    index_admin: SearchIndexClient
    search: SearchClient
    openai: AzureOpenAI

    @classmethod
    def build(cls, settings: Settings) -> "AzureIO":
        cred = DefaultAzureCredential()
        endpoint = str(settings.search_endpoint)
        return cls(
            settings=settings,
            blob=BlobServiceClient(str(settings.storage_account_url), credential=cred),
            index_admin=SearchIndexClient(endpoint, cred),
            search=SearchClient(endpoint, settings.search_index_version, cred),
            openai=AzureOpenAI(
                azure_endpoint=str(settings.azure_openai_endpoint),
                api_version=settings.azure_openai_api_version,
                azure_ad_token_provider=get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default"),
                max_retries=6,   # batch job: honor 429 retry-after instead of failing (the app uses 0)
            ),
        )

    # hop 3
    def put_raw(self, snapshot: date, part: str, xml: bytes) -> str:
        name = f"ecfr/{snapshot.isoformat()}/part-{part}.xml"
        self.blob.get_blob_client(self.settings.storage_container, name).upload_blob(
            xml, overwrite=True, content_type="application/xml")
        return name

    # hop 5
    def ensure_index(self) -> bool:
        """Create the index if missing. Returns True if it was created."""
        try:
            self.index_admin.get_index(self.settings.search_index_version)
            return False
        except ResourceNotFoundError:
            self.index_admin.create_index(index_schema(self.settings.search_index_version, self.settings.embed_dimensions))
            return True

    # hop 6
    def existing_hashes(self, part: str) -> dict[str, str]:
        results = self.search.search(search_text="*", filter=f"part eq '{part}'",
                                     select=["id", "content_hash"], top=100_000)
        return {r["id"]: r["content_hash"] for r in results}

    # hop 7
    def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        vectors, tokens = [], 0
        for i in range(0, len(texts), EMBED_BATCH):
            r = self.openai.embeddings.create(model=self.settings.embed_deployment,
                                              input=texts[i:i + EMBED_BATCH],
                                              dimensions=self.settings.embed_dimensions)
            vectors += [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
            tokens += r.usage.total_tokens
        return vectors, tokens

    # hops 8–9: the service answers 207 when only some documents fail, so check every item
    def write(self, upserts: list[dict], delete_ids: list[str]) -> None:
        """POST /docs/index with mergeOrUpload / delete actions, ≤ UPSERT_BATCH per request."""
        results = []
        for i in range(0, len(upserts), UPSERT_BATCH):
            results += self.search.merge_or_upload_documents(upserts[i:i + UPSERT_BATCH])
        for i in range(0, len(delete_ids), UPSERT_BATCH):
            results += self.search.delete_documents([{"id": k} for k in delete_ids[i:i + UPSERT_BATCH]])
        check_results(results)

    # hop 10
    def storage_bytes(self) -> int:
        return self.index_admin.get_service_statistics()["counters"]["storageSize"]["usage"]
