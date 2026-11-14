import asyncio
import time

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.clients import Clients
from app.config import Settings, get_settings
from app.smoke_checks import CHECKS, Check

router = APIRouter()


class CheckResult(BaseModel):
    name: str
    ok: bool
    ms: int
    detail: str | None = None
    error: str | None = None


class SmokeReport(BaseModel):
    ok: bool
    checks: list[CheckResult]


def get_checks() -> dict[str, Check]:
    return CHECKS  # overridden in tests with fakes


def _describe(exc: BaseException) -> str:
    """'<Type> <status>: <short message>'. No tokens, headers or full dumps (design 01 §1)."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
    msg = str(code) if code else str(exc).splitlines()[0] if str(exc) else ""
    head = type(exc).__name__ + (f" {status}" if status else "")
    return f"{head}: {msg[:200]}"


async def _run(name: str, check: Check, clients: Clients, settings: Settings) -> CheckResult:
    start = time.perf_counter()
    try:
        detail = await asyncio.wait_for(check(clients, settings), timeout=settings.smoke_timeout_s)
        return CheckResult(name=name, ok=True, ms=_ms(start), detail=detail)
    except TimeoutError:
        return CheckResult(name=name, ok=False, ms=_ms(start), error=f"timeout after {settings.smoke_timeout_s:g}s")
    except Exception as exc:  # report every failure as data; /smoke never 500s for a failed check
        return CheckResult(name=name, ok=False, ms=_ms(start), error=_describe(exc))


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


@router.get("/smoke", response_model=SmokeReport)
async def smoke(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    checks: dict[str, Check] = Depends(get_checks),
) -> SmokeReport:
    clients: Clients = request.app.state.clients
    results = await asyncio.gather(*(_run(n, c, clients, settings) for n, c in checks.items()))
    report = SmokeReport(ok=all(r.ok for r in results), checks=list(results))
    response.status_code = 200 if report.ok else 503  # CI can `curl --fail` (design 01 §1)
    return report
