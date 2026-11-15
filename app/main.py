from collections.abc import AsyncIterator

from app import telemetry

telemetry.configure()  # before FastAPI is imported/constructed: auto-instrumentation patches the class

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI  # noqa: E402

from app.auth import require_user
from app.clients import build_clients, close_clients
from app.config import get_settings
from app.routers import ask, health, smoke


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Create the credential + clients once; close them on shutdown (design 01 §6).
    app.state.clients = build_clients(get_settings())
    try:
        yield
    finally:
        await close_clients(app.state.clients)


app = FastAPI(title="Contract Intelligence Copilot", lifespan=lifespan)
app.include_router(health.router)  # public: liveness probe, no external calls
app.include_router(smoke.router, dependencies=[Depends(require_user)])  # Entra token required
app.include_router(ask.router, dependencies=[Depends(require_user)])
