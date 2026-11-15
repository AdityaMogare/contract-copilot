"""OpenTelemetry → Application Insights (design 04 hop 9).

- Auto-instrumentation (Azure Monitor distro): FastAPI requests, Azure SDK calls (Search), and the
  OpenAI SDK's HTTP calls all become spans (observed in App Insights, 2026-11-14). app/rag adds
  manual `embed` / `search` / `chat` / `validate` parent spans carrying what HTTP spans can't:
  token counts, reasoning tokens, finish reason, retrieval counts, validation result.
- Ingestion authenticates with Entra (local auth is OFF on appi-cczq9h, infra step 2b): the
  exporter gets a token for https://monitor.azure.com/.default from a SYNC DefaultAzureCredential,
  because it exports from a background thread, not the event loop. Role: Monitoring Metrics Publisher.
- No connection string → telemetry is off (unit tests, or a machine without App Insights).
"""

from __future__ import annotations

import logging
import os

from dotenv import dotenv_values

KEY = "APPLICATIONINSIGHTS_CONNECTION_STRING"
log = logging.getLogger(__name__)


def configure() -> bool:
    """Must run BEFORE `FastAPI()` is constructed (the instrumentation patches the class)."""
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":   # standard OTel off-switch (tests)
        return False
    conn = os.environ.get(KEY) or dotenv_values(".env").get(KEY)
    if not conn:
        return False
    from azure.identity import DefaultAzureCredential
    from azure.monitor.opentelemetry import configure_azure_monitor

    os.environ.setdefault("OTEL_SERVICE_NAME", "copilot-api")   # "cloud role name" in App Insights
    configure_azure_monitor(
        connection_string=conn,
        credential=DefaultAzureCredential(),
        enable_live_metrics=False,
        # Don't trace the liveness probe: ACA calls it every few seconds and it would dominate the bill.
        instrumentation_options={"fastapi": {"excluded_urls": "health"}},
    )
    log.info("telemetry → Application Insights (Entra auth)")
    return True
