import sys
from pathlib import Path

import pandas as pd
import pytest

from src.message_templates import TemplateError
from src.whatsapp_automation import WhatsAppAutomation

VALID_QA = "+97431691362"


@pytest.fixture
def automation(monkeypatch: pytest.MonkeyPatch) -> WhatsAppAutomation:
    # never actually sleep during tests
    monkeypatch.setattr("src.whatsapp_automation.time.sleep", lambda *_: None)
    return WhatsAppAutomation(config={"rate_limit_delay": 0, "max_retries": 3, "retry_delay": 0})


def _fake_pywhatkit(monkeypatch: pytest.MonkeyPatch, send):
    module = type("FakePywhatkit", (), {"sendwhatmsg_instantly": staticmethod(send)})
    monkeypatch.setitem(sys.modules, "pywhatkit", module)


class TestConfigNormalisation:
    def test_flat_config(self):
        a = WhatsAppAutomation(config={"rate_limit_delay": 7, "max_retries": 4})
        assert a.rate_limit_delay == 7
        assert a.max_retries == 4

    def test_nested_config_from_appconfig(self):
        from config.settings import AppConfig, LoggingConfig, ProcessingConfig, WhatsAppConfig

        cfg = AppConfig(WhatsAppConfig(rate_limit_delay=9), LoggingConfig(), ProcessingConfig())
        assert WhatsAppAutomation(config=cfg.__dict__).rate_limit_delay == 9

    def test_max_retries_never_below_one(self):
        assert WhatsAppAutomation(config={"max_retries": 0}).max_retries == 1


class TestLoadLeads:
    def test_missing_file(self, automation: WhatsAppAutomation, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            automation.load_leads(tmp_path / "nope.csv")

    def test_missing_columns(self, automation: WhatsAppAutomation, tmp_path: Path):
        f = tmp_path / "bad.csv"
        f.write_text("Foo,Bar\n1,2\n")
        with pytest.raises(ValueError):
            automation.load_leads(f)

    def test_ok(self, automation: WhatsAppAutomation, sample_leads_csv: Path):
        assert len(automation.load_leads(sample_leads_csv)) == 3


class TestValidateLead:
    def test_valid(self, automation: WhatsAppAutomation):
        row = pd.Series({"Business Name": " Acme ", "Phone Number": VALID_QA, "Category": "Food"})
        lead = automation.validate_lead(row)
        assert lead["business_name"] == "Acme"
        assert lead["phone_number"] == VALID_QA
        assert lead["category"] == "Food"

    def test_missing_number(self, automation: WhatsAppAutomation):
        assert automation.validate_lead(pd.Series({"Phone Number": None})) is None

    def test_bad_number(self, automation: WhatsAppAutomation):
        assert automation.validate_lead(pd.Series({"Phone Number": "not-a-phone"})) is None


class TestSendRetry:
    def test_succeeds_first_try(self, automation: WhatsAppAutomation, monkeypatch):
        calls = []
        _fake_pywhatkit(monkeypatch, lambda **kw: calls.append(kw))
        assert automation.send_message(VALID_QA, "hi", "Acme") is True
        assert len(calls) == 1

    def test_retries_then_succeeds(self, automation: WhatsAppAutomation, monkeypatch):
        attempts = {"n": 0}

        def flaky(**_):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise RuntimeError("boom")

        _fake_pywhatkit(monkeypatch, flaky)
        assert automation.send_message(VALID_QA, "hi", "Acme") is True
        assert attempts["n"] == 2

    def test_gives_up_after_max_retries(self, automation: WhatsAppAutomation, monkeypatch):
        attempts = {"n": 0}

        def always_fail(**_):
            attempts["n"] += 1
            raise RuntimeError("boom")

        _fake_pywhatkit(monkeypatch, always_fail)
        assert automation.send_message(VALID_QA, "hi", "Acme") is False
        assert attempts["n"] == automation.max_retries


class TestProcessCampaignDryRun:
    def test_dry_run_counts(self, automation: WhatsAppAutomation, tmp_path: Path):
        f = tmp_path / "leads.csv"
        f.write_text(
            "Business Name,Phone Number,Category\n"
            f"Acme,{VALID_QA},Food\n"
            "Bad Co,not-a-number,Food\n"
        )
        result = automation.run_campaign(f, "meeting_request", dry_run=True)
        assert (result.total_leads, result.successful_sends, result.invalid_numbers) == (2, 1, 1)
        assert result.failed_sends == 0

    def test_records_capture_per_lead_status(self, automation: WhatsAppAutomation, tmp_path: Path):
        f = tmp_path / "leads.csv"
        f.write_text("Business Name,Phone Number\n" f"Acme,{VALID_QA}\n" "Bad Co,not-a-number\n")
        result = automation.run_campaign(f, "meeting_request", dry_run=True)
        statuses = {r["business_name"]: r["status"] for r in result.records}
        assert statuses["Acme"] == "dry_run"
        assert statuses["Bad Co"] == "invalid_number"

    def test_unknown_template_raises(self, automation: WhatsAppAutomation, sample_leads_csv: Path):
        with pytest.raises(TemplateError):
            automation.run_campaign(sample_leads_csv, "does_not_exist", dry_run=True)
