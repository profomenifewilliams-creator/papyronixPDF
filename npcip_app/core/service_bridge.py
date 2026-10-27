"""Optional bridge to the project's own Java service; no third-party API calls."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

def mirror_case(case) -> str:
    base = os.environ.get("NPCIP_CASE_SERVICE_URL", "").strip().rstrip("/")
    token = os.environ.get("NPCIP_SERVICE_TOKEN", "").strip()
    if not base or not token:
        return "not_configured"
    if not (base.startswith("https://") or base.startswith("http://localhost") or base.startswith("http://127.0.0.1")):
        return "invalid_config"
    # Intentionally sync only a reference, title and broad category; never send a case summary or evidence file.
    body = json.dumps({
        "reference": str(case.case_number)[:24],
        "title": str(case.title)[:180],
        "category": "Cyber investigation",
    }).encode("utf-8")
    req = Request(
        base + "/internal/cases",
        data=body,
        headers={"Content-Type": "application/json", "X-NPCIP-Service-Token": token},
        method="POST",
    )
    try:
        with urlopen(req, timeout=3) as response:
            return "synced" if response.status in (200, 201) else "failed"
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return "failed"
