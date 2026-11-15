"""POST /ask with faked hops: no Azure calls. Covers design 04 §6 test list."""

import asyncio

import pytest

from app.rag import answer
from app.rag.answer import ModelAnswer, Usage
from app.rag.retrieve import HopError, RetrievedChunk
from app.routers import ask as ask_router

CHUNKS = [
    RetrievedChunk(1, "6_302-1--000", "FAR 6.302-1(a)", "https://www.acquisition.gov/far/6.302-1", "…", 0.033),
    RetrievedChunk(2, "6_304--000", "FAR 6.304(a)–(d)", "https://www.acquisition.gov/far/6.304", "…", 0.031),
]


@pytest.fixture
def fake_hops(monkeypatch):
    """Retrieval returns CHUNKS; chat returns the scripted outputs in order."""
    script: list = []
    calls = {"chat": 0}

    async def embed(clients, settings, q):
        return [0.0] * 512

    async def search(clients, settings, q, v, part):
        return list(CHUNKS)

    async def complete(clients, settings, messages, usage: Usage):
        calls["chat"] += 1
        usage.attempts += 1
        usage.prompt_tokens += 100
        out = script.pop(0)
        if isinstance(out, Exception):
            raise HopError("chat", out)
        return out

    monkeypatch.setattr(ask_router, "embed_query", embed)
    monkeypatch.setattr(ask_router, "hybrid_search", search)
    monkeypatch.setattr(answer, "_complete", complete)
    return script, calls


def _ask(client, q="When can I skip competition?", **kw):
    return client.post("/ask", json={"question": q, **kw})


def test_answer_maps_source_numbers_to_citations(client, fake_hops):
    script, _ = fake_hops
    script.append(ModelAnswer(status="answered", answer="Only one source [1]; approval per [2] and [1].", sources=[1, 2]))
    r = _ask(client)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "answered"
    assert [c["citation"] for c in body["citations"]] == ["FAR 6.302-1(a)", "FAR 6.304(a)–(d)"]   # deduped, in order
    assert body["citations"][0]["n"] == 1 and body["retrieved"] == 2
    assert body["usage"]["attempts"] == 1


def test_out_of_range_source_retries_once_then_succeeds(client, fake_hops):
    script, calls = fake_hops
    script += [ModelAnswer(status="answered", answer="See [7].", sources=[7]),
               ModelAnswer(status="answered", answer="See [1].", sources=[1])]
    body = _ask(client).json()
    assert body["status"] == "answered" and calls["chat"] == 2


def test_two_invalid_answers_become_not_found(client, fake_hops):
    script, calls = fake_hops
    script += [ModelAnswer(status="answered", answer="No cites.", sources=[]),
               ModelAnswer(status="answered", answer="Still none.", sources=[])]
    body = _ask(client).json()
    assert body["status"] == "not_found" and body["citations"] == [] and calls["chat"] == 2
    assert body["answer"] == answer.NOT_FOUND_TEXT


def test_length_cutoff_counts_as_failed_attempt(client, fake_hops):
    script, calls = fake_hops
    script += ["ran out of completion tokens (reasoning + answer)",
               ModelAnswer(status="partial", answer="Part of it [2]. The rest isn't covered.", sources=[2])]
    body = _ask(client).json()
    assert body["status"] == "partial" and [c["n"] for c in body["citations"]] == [2]


def test_model_not_found_passes_through(client, fake_hops):
    script, _ = fake_hops
    script.append(ModelAnswer(status="not_found", answer="", sources=[]))
    assert _ask(client).json()["status"] == "not_found"


def test_zero_results_skip_the_llm(client, fake_hops, monkeypatch):
    _, calls = fake_hops

    async def empty(*a):
        return []
    monkeypatch.setattr(ask_router, "hybrid_search", empty)
    body = _ask(client).json()
    assert body["status"] == "not_found" and calls["chat"] == 0


def test_dependency_failure_is_503_naming_the_hop(client, fake_hops):
    script, _ = fake_hops
    script.append(RuntimeError("429 Too Many Requests"))
    r = _ask(client)
    assert r.status_code == 503 and r.json()["detail"]["hop"] == "chat"


def test_deadline_is_504(client, fake_hops, monkeypatch):
    async def slow(*a):
        await asyncio.sleep(1)
    monkeypatch.setattr(ask_router, "embed_query", slow)
    monkeypatch.setenv("RAG_DEADLINE_S", "0.05")
    from app.config import get_settings
    get_settings.cache_clear()
    assert _ask(client).status_code == 504


@pytest.mark.parametrize("payload", [{"question": ""}, {"question": "x" * 1001},
                                     {"question": "ok", "part": "6' or 1 eq 1"}])
def test_bad_input_is_422(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_validate_rules():
    v = answer.validate
    assert v(ModelAnswer(status="answered", answer="x [1]", sources=[1]), 2) is None
    assert "do not exist" in v(ModelAnswer(status="answered", answer="x [3]", sources=[]), 2)
    assert "requires citing" in v(ModelAnswer(status="partial", answer="x", sources=[]), 2)
    assert v(ModelAnswer(status="not_found", answer="", sources=[]), 2) is None
