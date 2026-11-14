from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients import build_clients, close_clients
from app.config import get_settings
from app.routers import health, smoke


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Create the credential + clients once; close them on shutdown (design 01 §6).
    app.state.clients = build_clients(get_settings())
    try:
        yield
    finally:
        await close_clients(app.state.clients)


app = FastAPI(title="Contract Intelligence Copilot", lifespan=lifespan)
app.include_router(health.router)
app.include_router(smoke.router)
