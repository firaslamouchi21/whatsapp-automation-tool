import argparse
from pathlib import Path

import pytest

import main

VALID_QA = "+97431691362"


class TestParser:
    def test_defaults(self):
        args = main.create_parser().parse_args([])
        assert args.start == 0
        assert args.dry_run is False
        assert args.config == Path("config/config.yaml")

    def test_flags(self):
        args = main.create_parser().parse_args(
            ["--leads", "l.csv", "--template", "meeting_request", "--dry-run", "--end", "5"]
        )
        assert args.leads == Path("l.csv")
        assert args.template == "meeting_request"
        assert args.dry_run is True
        assert args.end == 5


def test_list_templates(capsys: pytest.CaptureFixture):
    main.list_templates()
    out = capsys.readouterr().out
    assert "Available Templates:" in out
    assert "meeting_request" in out


def test_validate_leads(capsys: pytest.CaptureFixture, tmp_path: Path):
    f = tmp_path / "leads.csv"
    f.write_text(f"Business Name,Phone Number\nAcme,{VALID_QA}\nBad,xxx\n")
    main.validate_leads(f)
    out = capsys.readouterr().out
    assert "Valid numbers: 1" in out
    assert "Invalid numbers: 1" in out


def test_run_campaign_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("src.whatsapp_automation.time.sleep", lambda *_: None)
    leads = tmp_path / "leads.csv"
    leads.write_text(f"Business Name,Phone Number,Category\nAcme,{VALID_QA},Food\n")
    args = argparse.Namespace(
        config=tmp_path / "missing.yaml",
        verbose=False,
        leads=leads,
        template="meeting_request",
        dry_run=True,
        start=0,
        end=None,
        output=None,
    )
    result = main.run_campaign(args)
    assert result is not None
    assert result.successful_sends == 1


def test_run_campaign_bad_template_returns_none(tmp_path: Path):
    leads = tmp_path / "leads.csv"
    leads.write_text(f"Business Name,Phone Number\nAcme,{VALID_QA}\n")
    args = argparse.Namespace(
        config=tmp_path / "missing.yaml",
        verbose=False,
        leads=leads,
        template="nope",
        dry_run=True,
        start=0,
        end=None,
        output=None,
    )
    assert main.run_campaign(args) is None
