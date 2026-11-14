"""One function per dependency. Each returns a short detail string on success and raises on
failure; the /smoke router turns exceptions into CheckResult errors (design 01 §1, §3)."""

from collections.abc import Awaitable, Callable

from app.clients import Clients
from app.config import Settings

Check = Callable[[Clients, Settings], Awaitable[str]]


async def check_chat(c: Clients, s: Settings) -> str:
    resp = await c.openai.chat.completions.create(
        model=s.chat_deployment,  # for Azure, "model" is the DEPLOYMENT name
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_completion_tokens=64,  # reasoning tokens count here; keeps cost tiny
        reasoning_effort="minimal",
    )
    # Pass on HTTP 200 + a finish_reason, not on the text: a tight token cap can yield empty content.
    return f"model={resp.model} finish={resp.choices[0].finish_reason}"


async def check_embed(c: Clients, s: Settings) -> str:
    resp = await c.openai.embeddings.create(model=s.embed_deployment, input="smoke test")
    return f"dims={len(resp.data[0].embedding)}"


async def check_search(c: Clients, s: Settings) -> str:
    names = [n async for n in c.search.list_index_names()]
    return f"indexes={len(names)}"


async def check_keyvault(c: Clients, s: Settings) -> str:
    # Properties only: never read secret values in a health check.
    count = 0
    async for _ in c.keyvault.list_properties_of_secrets():
        count += 1
    return f"secrets={count}"


async def check_storage(c: Clients, s: Settings) -> str:
    container = c.blob.get_container_client(s.storage_container)
    count = 0
    async for _ in container.list_blobs(results_per_page=1):
        count += 1
        break
    return f"container={s.storage_container} sample_blobs={count}"


CHECKS: dict[str, Check] = {
    "chat": check_chat,
    "embed": check_embed,
    "search": check_search,
    "keyvault": check_keyvault,
    "storage": check_storage,
}
