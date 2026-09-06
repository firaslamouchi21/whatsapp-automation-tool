#!/usr/bin/env python3
"""End-to-end smoke test for the web UI.

Boots the Flask app with its test client and drives the campaign flow far enough
to prove the wiring works: templates load, leads validate, a message renders.
Exits non-zero on any failure so CI fails loudly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import app  # noqa: E402


def main() -> int:
    client = app.test_client()

    r = client.get("/")
    assert r.status_code == 200, f"GET / -> {r.status_code}"

    r = client.get("/api/templates")
    assert r.status_code == 200, f"GET /api/templates -> {r.status_code}"
    templates = r.get_json()
    assert templates, "no message templates loaded (templates dir not resolved?)"
    print(f"  loaded {len(templates)} templates")

    template_name = "meeting_request"
    assert template_name in templates, f"expected template {template_name!r} missing"

    r = client.post("/api/campaign/select-template", json={"template_name": template_name})
    assert r.status_code == 200, f"select-template -> {r.status_code} {r.get_json()}"

    r = client.post(
        "/api/leads/add",
        json={"business_name": "Acme Co", "phone_number": "+97431691362"},
    )
    assert r.status_code == 200, f"leads/add -> {r.status_code} {r.get_json()}"

    r = client.post(
        "/api/campaign/preview",
        json={"template": template_name, "lead": {"business_name": "Acme Co"}},
    )
    assert r.status_code == 200, f"preview -> {r.status_code} {r.get_json()}"
    assert "Acme Co" in r.get_json()["message"]

    r = client.post("/api/campaign/confirm")
    assert r.status_code == 200, f"confirm -> {r.status_code} {r.get_json()}"

    print("web UI smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
