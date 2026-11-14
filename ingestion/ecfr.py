"""eCFR versioner API client (design 03 hops 1–2). Public, no auth.

Gotchas measured while designing:
- The `full` endpoint returns 406 unless the request allows compression (httpx sends gzip by default).
- `?chapter=1` is ignored by `full`, so we always fetch one `part` at a time.
"""

from __future__ import annotations

import time
from datetime import date

import httpx

BASE = "https://www.ecfr.gov/api/versioner/v1"
FAR_PARTS = [str(n) for n in range(1, 54)]   # FAR = Title 48 chapter 1, parts 1–53 (reserved ones 404/empty)
RETRY_STATUS = {429, 500, 502, 503, 504}


def _get(client: httpx.Client, url: str, params: dict, attempts: int = 4) -> httpx.Response:
    for i in range(attempts):
        r = client.get(url, params=params, headers={"Accept-Encoding": "gzip"})
        if r.status_code not in RETRY_STATUS or i == attempts - 1:
            r.raise_for_status()
            return r
        time.sleep(float(r.headers.get("retry-after", 2 ** i)))
    raise AssertionError("unreachable")


def fetch_part_xml(client: httpx.Client, snapshot: date, part: str) -> bytes:
    """GET /full/{date}/title-48.xml?part=N → the DIV5 XML for that part as of `snapshot`."""
    return _get(client, f"{BASE}/full/{snapshot.isoformat()}/title-48.xml", {"part": part}).content


def fetch_amendment_dates(client: httpx.Client, snapshot: date, part: str) -> dict[str, date]:
    """GET /versions/title-48.json?part=N → latest amendment date per section, as of `snapshot`."""
    data = _get(client, f"{BASE}/versions/title-48.json", {"part": part}).json()
    latest: dict[str, date] = {}
    for v in data.get("content_versions", []):
        d = date.fromisoformat(v["amendment_date"])
        if v.get("type") == "section" and d <= snapshot and d > latest.get(v["identifier"], date.min):
            latest[v["identifier"]] = d
    return latest


def make_client() -> httpx.Client:
    return httpx.Client(timeout=60.0, follow_redirects=True, headers={"User-Agent": "contract-copilot-ingest"})
