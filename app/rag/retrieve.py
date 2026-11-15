"""Hops 4–5 (design 04): embed the question, hybrid search the FAR index via its alias."""

from __future__ import annotations

from dataclasses import dataclass

from azure.search.documents.models import VectorizedQuery
from opentelemetry import trace

from app.clients import Clients
from app.config import Settings

tracer = trace.get_tracer(__name__)


class HopError(Exception):
    """A dependency failed. `hop` names it so the API can answer 503 {"hop": ...}."""

    def __init__(self, hop: str, cause: BaseException):
        super().__init__(f"{hop}: {cause}")
        self.hop, self.cause = hop, cause


@dataclass
class RetrievedChunk:
    n: int            # 1-based number the model sees as [n]
    id: str
    citation: str
    url: str
    content: str
    score: float


async def embed_query(clients: Clients, settings: Settings, question: str) -> list[float]:
    with tracer.start_as_current_span("embed") as span:
        span.set_attribute("gen_ai.request.model", settings.embed_deployment)
        try:
            r = await clients.openai_rag.embeddings.create(
                model=settings.embed_deployment, input=[question],
                dimensions=settings.embed_dimensions,   # MUST match the index (design 03 §4)
            )
        except Exception as e:
            raise HopError("embed", e) from e
        span.set_attribute("gen_ai.usage.input_tokens", r.usage.prompt_tokens)
        return r.data[0].embedding


async def hybrid_search(clients: Clients, settings: Settings, question: str, vector: list[float],
                        part: str | None) -> list[RetrievedChunk]:
    with tracer.start_as_current_span("search") as span:
        span.set_attribute("search.index", settings.search_index)
        span.set_attribute("search.top", settings.rag_top_k)
        span.set_attribute("search.vector_weight", settings.rag_vector_weight)
        try:
            results = await clients.docs.search(
                search_text=question,                                  # BM25 side
                vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=50, fields="content_vector",
                                                weight=settings.rag_vector_weight)],
                filter=f"part eq '{part}'" if part else None,          # part is validated as digits (router)
                select=["id", "citation", "url", "content"],
                top=settings.rag_top_k,
            )
            chunks = [
                RetrievedChunk(n=i, id=r["id"], citation=r["citation"], url=r["url"],
                               content=r["content"], score=r["@search.score"])
                async for i, r in _enumerate(results, 1)
            ]
        except Exception as e:
            raise HopError("search", e) from e
        span.set_attribute("search.results", len(chunks))
        if chunks:
            span.set_attribute("search.top_score", chunks[0].score)
        return chunks


async def _enumerate(aiter, start: int):
    i = start
    async for x in aiter:
        yield i, x
        i += 1
