"""CLI: load one fiscal year of Air Force contract transactions into Postgres (design 06).

uv run python -m awards.load --fy 2025 [--quarters 1,2] [--from-blob]

Runs as Aditya (Entra admin of the server): Entra token as the Postgres password, no stored secret.
One DB transaction per fiscal year: delete that FY, COPY transactions + awards, audit row, COMMIT.
A failure anywhere rolls back, so the previous FY data stays intact.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from app.config import get_settings
from awards import usaspending
from awards.transform import AWARD_COLS, TX_COLS, build

PG_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
CONTAINER = "usaspending-raw"
SCHEMA = Path(__file__).with_name("schema.sql")


def connect_as_me(settings, cred) -> psycopg.Connection:
    """TLS + Entra token as password. The token is checked once, at connect time."""
    token = cred.get_token(PG_SCOPE).token
    return psycopg.connect(host=settings.pg_host, dbname=settings.pg_database, user=settings.pg_user,
                           password=token, sslmode="require", connect_timeout=15)


def csv_rows(zip_path: Path):
    """Yield dict rows from the single CSV inside a USAspending zip (parsed as data, never executed)."""
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", newline=""))


def fetch_quarter(fy: int, q: int, http: httpx.Client, blob: BlobServiceClient, workdir: Path, from_blob: bool) -> Path:
    dest = workdir / f"fy{fy}-q{q}.zip"
    blob_client = blob.get_blob_client(CONTAINER, f"fy{fy}/q{q}.zip")
    if from_blob:                                                            # replay: no USAspending call
        dest.write_bytes(blob_client.download_blob().readall())
        return dest
    req = usaspending.request_download(http, fy, q)                          # hop 1
    print(f"q{q}: requested {req['file_name']}, waiting…", file=sys.stderr, flush=True)
    st = usaspending.wait_until_ready(http, req["status_url"])               # hop 2
    print(f"q{q}: ready, {st.get('total_rows')} rows", file=sys.stderr, flush=True)
    usaspending.download(http, req["file_url"], dest)                        # hop 3
    blob_client.upload_blob(dest.read_bytes(), overwrite=True)               # hop 4
    return dest


def load(fy: int, quarters: list[int], from_blob: bool) -> dict:
    settings = get_settings()
    cred = DefaultAzureCredential()
    blob = BlobServiceClient(str(settings.storage_account_url), credential=cred)
    started = datetime.now(timezone.utc)
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="usaspending-") as tmp, httpx.Client(timeout=120) as http:
        for q in quarters:
            rows += list(csv_rows(fetch_quarter(fy, q, http, blob, Path(tmp), from_blob)))
    txs, awards = build(rows, fy)

    with connect_as_me(settings, cred) as conn:                              # hops 5–6
        with conn.transaction():
            conn.execute(SCHEMA.read_text())
            conn.execute("DELETE FROM transactions WHERE fiscal_year = %s", (fy,))
            conn.execute("DELETE FROM awards WHERE fiscal_year = %s", (fy,))
            with conn.cursor().copy(f"COPY transactions ({', '.join(TX_COLS)}) FROM STDIN") as cp:
                for t in txs:
                    cp.write_row(t)
            with conn.cursor().copy(f"COPY awards ({', '.join(AWARD_COLS)}) FROM STDIN") as cp:
                for a in awards:
                    cp.write_row(a)
            n_tx = conn.execute("SELECT count(*) FROM transactions WHERE fiscal_year = %s", (fy,)).fetchone()[0]
            n_aw = conn.execute("SELECT count(*) FROM awards WHERE fiscal_year = %s", (fy,)).fetchone()[0]
            # Reconciliation: every CSV row is a transaction; every distinct award key is an award.
            if n_tx != len(rows) or n_aw != len({r["contract_award_unique_key"] for r in rows}):
                raise RuntimeError(f"reconciliation failed: csv={len(rows)} tx={n_tx} awards={n_aw}")
            conn.execute("INSERT INTO load_runs (fiscal_year, source, csv_rows, transactions, awards, started_at, finished_at) "
                         "VALUES (%s, %s, %s, %s, %s, %s, now())",
                         (fy, "blob" if from_blob else "usaspending", len(rows), n_tx, n_aw, started))
        conn.execute("ANALYZE awards; ANALYZE transactions")
    return {"fiscal_year": fy, "quarters": quarters, "csv_rows": len(rows), "transactions": n_tx, "awards": n_aw}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fy", type=int, required=True)
    ap.add_argument("--quarters", default="1,2,3,4")
    ap.add_argument("--from-blob", action="store_true")
    a = ap.parse_args()
    t = time.perf_counter()
    out = load(a.fy, [int(q) for q in a.quarters.split(",")], a.from_blob)
    out["seconds"] = round(time.perf_counter() - t, 1)
    print(out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
