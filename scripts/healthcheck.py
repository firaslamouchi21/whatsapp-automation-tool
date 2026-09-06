#!/usr/bin/env python3
"""HTTP health check for a running WhatsApp Automation Tool web UI.

Waits for the server to accept connections, then drives the whole campaign
workflow over real HTTP (select template -> add lead -> preview -> confirm ->
start) and checks the noVNC endpoint. Exits non-zero on the first failure.

Usage:
    python scripts/healthcheck.py [BASE_URL] [--novnc-url URL] [--timeout SECONDS]

Defaults: BASE_URL=http://127.0.0.1:5000, novnc probe skipped unless given.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TEMPLATE = "meeting_request"


def _request(method: str, url: str, payload: dict | None = None, timeout: float = 10.0):
    data = None
    headers = {}
    if method != "GET":
        # Mirror the dashboard's fetch(): always a JSON content type on writes.
        data = json.dumps(payload or {}).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local URL)
        body = resp.read().decode()
        try:
            return resp.status, (json.loads(body) if body else None)
        except json.JSONDecodeError:
            return resp.status, body


def wait_for(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, _ = _request("GET", base_url + "/", timeout=3)
            if status == 200:
                print(f"  server is up ({base_url})")
                return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_err = exc
        time.sleep(0.5)
    raise SystemExit(f"server did not become ready within {timeout}s: {last_err}")


def check_workflow(base_url: str) -> None:
    status, templates = _request("GET", base_url + "/api/templates")
    assert status == 200, f"/api/templates -> {status}"
    assert templates, "no message templates loaded"
    assert TEMPLATE in templates, f"template {TEMPLATE!r} missing"
    print(f"  {len(templates)} templates loaded")

    status, _ = _request("GET", base_url + "/vnc")
    assert status == 200, f"/vnc -> {status}"

    status, body = _request(
        "POST", base_url + "/api/campaign/select-template", {"template_name": TEMPLATE}
    )
    assert status == 200, f"select-template -> {status} {body}"

    status, body = _request(
        "POST",
        base_url + "/api/leads/add",
        {"business_name": "Acme Co", "phone_number": "+97431691362"},
    )
    assert status == 200, f"leads/add -> {status} {body}"

    status, body = _request(
        "POST",
        base_url + "/api/campaign/preview",
        {"template": TEMPLATE, "lead": {"business_name": "Acme Co"}},
    )
    assert status == 200 and "Acme Co" in body["message"], f"preview -> {status} {body}"

    status, body = _request("POST", base_url + "/api/campaign/confirm")
    assert status == 200, f"confirm -> {status} {body}"

    # dry-run: exercise the runner end to end without sending anything
    status, body = _request("POST", base_url + "/api/campaign/start", {"dry_run": True})
    assert status == 200 and body.get("success"), f"start -> {status} {body}"

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        _, prog = _request("GET", base_url + "/api/campaign/progress")
        if prog and prog.get("status") in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert prog and prog.get("status") == "completed", f"campaign did not complete: {prog}"

    _request("POST", base_url + "/api/campaign/reset")
    print("  full campaign workflow OK (dry-run)")


def check_novnc(url: str) -> None:
    try:
        status, _ = _request("GET", url, timeout=5)
        print(f"  noVNC endpoint responded ({status})")
    except Exception as exc:  # noqa: BLE001 - informational only
        print(f"  WARNING: noVNC endpoint not reachable: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:5000")
    parser.add_argument("--novnc-url")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    wait_for(base, args.timeout)
    check_workflow(base)
    if args.novnc_url:
        check_novnc(args.novnc_url)
    print("healthcheck passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
