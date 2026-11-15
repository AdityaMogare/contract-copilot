from collections.abc import AsyncIterator

from app import telemetry

telemetry.configure()  # before FastAPI is imported/constructed: auto-instrumentation patches the class

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI  # noqa: E402

from app.auth import require_user
from app.clients import build_clients, close_clients
from app.config import get_settings
from app.routers import ask, awards, health, reviews, smoke


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Create the credential + clients once; close them on shutdown (design 01 §6).
    app.state.clients = build_clients(get_settings())
    for pool in (app.state.clients.pg, app.state.clients.pg_agent):
        if pool is not None:
            await pool.open(wait=False)   # min_size=0: opens no connection until first use
    try:
        yield
    finally:
        await close_clients(app.state.clients)


app = FastAPI(title="Contract Intelligence Copilot", lifespan=lifespan)
app.include_router(health.router)  # public: liveness probe, no external calls
app.include_router(smoke.router, dependencies=[Depends(require_user)])  # Entra token required
app.include_router(ask.router, dependencies=[Depends(require_user)])
app.include_router(awards.router, dependencies=[Depends(require_user)])
app.include_router(reviews.router, dependencies=[Depends(require_user)])
