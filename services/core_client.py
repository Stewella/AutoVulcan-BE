import requests
import subprocess
import json
from typing import Dict, Any

from config import settings

CORE_ENGINE_HOST = settings.CORE_ENGINE_HOST
CORE_ENGINE_API_KEY = None  # extend to settings if needed


def call_core_engine_http(payload: Dict[str, Any], timeout: int = 600) -> Dict[str, Any]:
    url = f"{CORE_ENGINE_HOST.rstrip('/')}/run"
    headers = {"Content-Type": "application/json"}
    if CORE_ENGINE_API_KEY:
        headers["X-API-KEY"] = CORE_ENGINE_API_KEY
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def call_core_engine_via_docker(container_name: str, cmd_args: list, workdir: str = "/app") -> Dict[str, Any]:
    # exec command inside core-engine container and capture stdout
    base = ["docker", "exec", container_name] + cmd_args
    p = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=workdir)
    if p.returncode != 0:
        raise RuntimeError(f"core-engine exec failed: {p.stderr}")
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"raw": p.stdout}
