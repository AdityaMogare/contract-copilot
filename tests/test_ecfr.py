from datetime import date

import httpx

from ingestion import ecfr


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_amendment_dates_latest_not_after_snapshot():
    payload = {"content_versions": [
        {"identifier": "6.302-1", "amendment_date": "2019-01-01", "type": "section"},
        {"identifier": "6.302-1", "amendment_date": "2025-10-01", "type": "section"},
        {"identifier": "6.302-1", "amendment_date": "2027-01-01", "type": "section"},   # after snapshot
        {"identifier": "6.3", "amendment_date": "2025-10-01", "type": "subpart"},
    ]}
    with _client(lambda req: httpx.Response(200, json=payload)) as c:
        got = ecfr.fetch_amendment_dates(c, date(2026, 10, 28), "6")
    assert got == {"6.302-1": date(2025, 10, 1)}


def test_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(ecfr.time, "sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(req)
        assert req.headers["accept-encoding"] == "gzip"      # eCFR returns 406 without it
        return httpx.Response(429, headers={"retry-after": "1"}) if len(calls) == 1 else httpx.Response(200, content=b"<DIV5/>")

    with _client(handler) as c:
        assert ecfr.fetch_part_xml(c, date(2026, 10, 28), "6") == b"<DIV5/>"
    assert len(calls) == 2
    assert calls[0].url.params["part"] == "6" and "/full/2026-10-28/title-48.xml" in str(calls[0].url)
