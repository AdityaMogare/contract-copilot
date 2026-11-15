"""USAspending bulk download client (design 06 hops 1–3). Public API, no auth.

Async on their side: POST returns a status_url + file_url; the zip exists only once status is 'finished'
(~3–4 min per quarter of Air Force contracts, measured).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import httpx

API = "https://api.usaspending.gov/api/v2"
AIR_FORCE = {"type": "awarding", "tier": "subtier", "name": "Department of the Air Force",
             "toptier_name": "Department of Defense"}
CONTRACT_TYPES = ["A", "B", "C", "D"]   # BPA call, purchase order, delivery order, definitive contract


def quarter_range(fy: int, q: int) -> tuple[date, date]:
    """FY2025 Q1 = 2024-10-01..2024-12-31 (the federal fiscal year starts Oct 1 of the prior year)."""
    starts = {1: date(fy - 1, 10, 1), 2: date(fy, 1, 1), 3: date(fy, 4, 1), 4: date(fy, 7, 1)}
    ends = {1: date(fy - 1, 12, 31), 2: date(fy, 3, 31), 3: date(fy, 6, 30), 4: date(fy, 9, 30)}
    return starts[q], ends[q]


def request_download(client: httpx.Client, fy: int, q: int) -> dict:
    start, end = quarter_range(fy, q)
    body = {"filters": {"prime_award_types": CONTRACT_TYPES, "agencies": [AIR_FORCE], "date_type": "action_date",
                        "date_range": {"start_date": start.isoformat(), "end_date": end.isoformat()}},
            "file_format": "csv"}
    r = client.post(f"{API}/bulk_download/awards/", json=body)
    r.raise_for_status()
    return r.json()


def wait_until_ready(client: httpx.Client, status_url: str, every_s: float = 10, max_s: float = 1200) -> dict:
    waited = 0.0
    while True:
        r = client.get(status_url)
        r.raise_for_status()
        st = r.json()
        if st["status"] == "finished":
            return st
        if st["status"] == "failed":
            raise RuntimeError(f"USAspending download failed: {st.get('message')}")
        if waited >= max_s:
            raise TimeoutError(f"download not ready after {max_s:.0f}s")
        time.sleep(every_s)
        waited += every_s


def download(client: httpx.Client, url: str, dest: Path) -> Path:
    """Stream the zip to `dest` (an empty dir of its own: downloaded files are untrusted data)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest
