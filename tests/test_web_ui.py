import io
import time

import pytest

app_module = pytest.importorskip("web_ui.app")

VALID_QA = "+97431691362"


def _wait_for_campaign(client, status: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get("/api/campaign/progress").get_json()
        if body["status"] == status:
            return body
        time.sleep(0.05)
    raise AssertionError(f"campaign did not reach {status!r}: {body}")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(
        app_module,
        "campaign_state",
        {"selected_template": None, "leads_file": None, "leads_data": [], "status": "idle"},
    )
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", tmp_path)
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_index_and_templates(client):
    assert client.get("/").status_code == 200
    body = client.get("/api/templates").get_json()
    assert body and "meeting_request" in body
    mr = body["meeting_request"]
    assert isinstance(mr, dict)
    assert mr["name"] and mr["language"] == "en" and "business_name" in mr["variables"]


def test_template_detail_404(client):
    assert client.get("/api/templates/does-not-exist").status_code == 404


def test_full_campaign_flow(client):
    assert (
        client.post(
            "/api/campaign/select-template", json={"template_name": "meeting_request"}
        ).status_code
        == 200
    )

    r = client.post("/api/leads/add", json={"business_name": "Acme", "phone_number": VALID_QA})
    assert r.status_code == 200 and r.get_json()["total_leads"] == 1

    r = client.post(
        "/api/campaign/preview",
        json={"template": "meeting_request", "lead": {"business_name": "Acme"}},
    )
    assert r.status_code == 200 and "Acme" in r.get_json()["message"]

    assert client.post("/api/campaign/confirm").status_code == 200

    started = client.post("/api/campaign/start", json={"dry_run": True}).get_json()
    assert started["success"] is True and started["dry_run"] is True

    done = _wait_for_campaign(client, "completed")
    assert done["result"]["successful_sends"] == 1
    assert done["result"]["dry_run"] is True


def test_add_lead_rejects_bad_number(client):
    r = client.post("/api/leads/add", json={"business_name": "X", "phone_number": "nope"})
    assert r.status_code == 400


def test_start_requires_confirm(client):
    assert client.post("/api/campaign/start").status_code == 400


def test_csv_upload(client):
    csv = f"Business Name,Phone Number,Category\nAcme,{VALID_QA},Food\nBad,xxx,Food\n".encode()
    r = client.post(
        "/api/leads/upload",
        data={"file": (io.BytesIO(csv), "leads.csv")},
        content_type="multipart/form-data",
    )
    body = r.get_json()
    assert r.status_code == 200
    assert body["leads_count"] == 1 and body["invalid_count"] == 1


def test_reset(client):
    client.post("/api/campaign/select-template", json={"template_name": "meeting_request"})
    assert client.post("/api/campaign/reset").status_code == 200
    assert client.get("/api/campaign/status").get_json()["selected_template"] is None


def test_cross_origin_write_rejected(client, monkeypatch):
    # exercise the CSRF guard (the fixture normally bypasses it via TESTING)
    monkeypatch.setitem(app_module.app.config, "TESTING", False)
    r = client.post(
        "/api/leads/add",
        data="business_name=X&phone_number=Y",
        content_type="application/x-www-form-urlencoded",
        headers={"Origin": "http://evil.example"},
    )
    assert r.status_code == 403

    # same request with a same-origin Origin is allowed through the guard
    r = client.post(
        "/api/leads/add",
        json={"business_name": "X", "phone_number": "Y"},
        headers={"Origin": "http://localhost"},
    )
    assert r.status_code in (200, 400)  # 400 = bad phone, but the guard let it through


def test_create_template_rejects_path_traversal(client):
    r = client.post(
        "/api/templates",
        json={
            "name": "x",
            "template_id": "x",
            "template_text": "hi {business_name}",
            "variables": ["business_name"],
            "language": "../../../../tmp",
            "category": "it",
        },
    )
    assert r.status_code == 400
