"""Competition-check and review endpoints with faked services (design 08). No database."""

from app.agent import check as check_mod
from app.agent import reviews as reviews_mod
from app.main import app
from app.routers import reviews as reviews_router


def test_check_unknown_piid_is_404(client, monkeypatch):
    async def run(clients, piid, thread_id=None, open_reviews=True):
        return {"piid": piid, "found": False, "awards": [], "review_items": []}
    monkeypatch.setattr(reviews_router, "run_check", run)
    assert client.post("/awards/FA0000X/competition-check").status_code == 404


def test_check_rejects_odd_piid(client):
    assert client.post("/awards/FA'%20OR%201=1/competition-check").status_code == 422


def test_check_returns_findings_without_full_far_text(client, monkeypatch):
    async def run(clients, piid, thread_id=None, open_reviews=True):
        return {"piid": piid, "found": True, "awards": [{"award": {"piid": piid}, "findings": [{"rule_id": "SINGLE-OFFER"}]}],
                "review_items": [{"id": 1}], "far_chunks": {"6.101": [{"content": "long text"}]}}
    monkeypatch.setattr(reviews_router, "run_check", run)
    b = client.post("/awards/FA880718C0009/competition-check").json()
    assert "far_chunks" not in b and b["awards"][0]["findings"][0]["rule_id"] == "SINGLE-OFFER"


def test_decide_paths(client, monkeypatch):
    app.state.clients.pg_agent = object()
    outcomes = {1: ("ok", {"id": 1, "status": "dismissed"}), 2: ("already_decided", {"id": 2, "status": "confirmed"}),
                3: ("not_found", None)}
    seen = {}

    async def decide(pool, item_id, decision, note, reviewer):
        seen["reviewer"] = reviewer
        return outcomes[item_id]
    monkeypatch.setattr(reviews_mod, "decide", decide)
    try:
        assert client.post("/reviews/1/decision", json={"decision": "dismissed"}).status_code == 200
        assert seen["reviewer"] == "local-dev"          # auth off in unit tests
        assert client.post("/reviews/2/decision", json={"decision": "confirmed"}).status_code == 409
        assert client.post("/reviews/3/decision", json={"decision": "confirmed"}).status_code == 404
        assert client.post("/reviews/1/decision", json={"decision": "approve"}).status_code == 422   # only confirmed|dismissed
    finally:
        app.state.clients.pg_agent = None


def test_threshold_drift_detects_changed_far_text():
    assert check_mod.threshold_drift([{"content": "$900,000 ... $20 million ... $150 million"}]) == []
    assert check_mod.threshold_drift([{"content": "$1 million ... $20 million ... $150 million"}]) == ["$900,000"]
