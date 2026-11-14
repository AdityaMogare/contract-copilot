import asyncio

from app.main import app
from app.routers.smoke import get_checks


async def ok_check(clients, settings):
    return "fine"


async def failing_check(clients, settings):
    class HttpResponseError(Exception):
        status_code = 403
        error_code = "AuthorizationPermissionMismatch"

    raise HttpResponseError("forbidden")


async def slow_check(clients, settings):
    await asyncio.sleep(5)  # longer than SMOKE_TIMEOUT_S=0.2 in tests
    return "never"


def _use(checks):
    app.dependency_overrides[get_checks] = lambda: checks


def test_all_checks_pass_returns_200(client):
    _use({"a": ok_check, "b": ok_check})
    r = client.get("/smoke")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert [c["name"] for c in body["checks"]] == ["a", "b"]
    assert all(c["detail"] == "fine" for c in body["checks"])


def test_one_failure_returns_503_and_keeps_other_results(client):
    _use({"good": ok_check, "storage": failing_check})
    r = client.get("/smoke")
    assert r.status_code == 503
    checks = {c["name"]: c for c in r.json()["checks"]}
    assert checks["good"]["ok"] is True
    assert checks["storage"]["ok"] is False
    assert checks["storage"]["error"] == "HttpResponseError 403: AuthorizationPermissionMismatch"


def test_slow_check_times_out_without_blocking_others(client):
    _use({"good": ok_check, "slow": slow_check})
    r = client.get("/smoke")
    assert r.status_code == 503
    checks = {c["name"]: c for c in r.json()["checks"]}
    assert checks["good"]["ok"] is True
    assert checks["slow"]["error"].startswith("timeout after 0.2s")
    assert checks["slow"]["ms"] < 2000  # timed out, didn't wait the full 5 s
