from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    # Liveness only: no external calls, so a slow model can't get healthy replicas restarted.
    return {"status": "ok"}
