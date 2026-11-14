"""Add liveness + readiness probes on /health to a Container App (design 01/02).

`az containerapp create` has no probe flags. This reads the current template, sets probes on
the first container, and PATCHes it back through ARM via `az rest`. Idempotent.
Usage: python3 infra/patch_probes.py <resource-group> <container-app>
"""

import json
import subprocess
import sys

rg, name = sys.argv[1], sys.argv[2]
extra = sys.argv[3:]  # e.g. --debug, passed through to az


def az(*args: str) -> str:
    return subprocess.run(["az", *args, *extra], check=True, capture_output=True, text=True).stdout


app = json.loads(az("containerapp", "show", "-g", rg, "-n", name, "-o", "json"))
template = app["properties"]["template"]
probe = {"httpGet": {"path": "/health", "port": 8000}, "periodSeconds": 10, "failureThreshold": 3}
template["containers"][0]["probes"] = [
    {"type": "Liveness", **probe, "initialDelaySeconds": 5},
    {"type": "Readiness", **probe, "initialDelaySeconds": 3},
]
body = json.dumps({"properties": {"template": template}})
az("rest", "--method", "patch", "--url", f"https://management.azure.com{app['id']}?api-version=2025-07-01",
   "--body", body, "-o", "none")
print("probes set on /health", file=sys.stderr)
