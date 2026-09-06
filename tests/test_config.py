from pathlib import Path

import pytest

from config.settings import ConfigManager


class TestConfigManager:
    def test_defaults_when_no_file(self, tmp_path: Path):
        cm = ConfigManager(tmp_path / "missing.yaml")
        assert cm.get_config().whatsapp.rate_limit_delay == 20
        assert cm.get_config().whatsapp.max_retries == 3

    def test_loads_from_yaml(self, tmp_path: Path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "whatsapp:\n  rate_limit_delay: 45\n  max_retries: 5\n" "logging:\n  level: DEBUG\n"
        )
        cm = ConfigManager(cfg)
        assert cm.get_config().whatsapp.rate_limit_delay == 45
        assert cm.get_config().whatsapp.max_retries == 5
        assert cm.get_config().logging.level == "DEBUG"

    def test_env_overrides_applied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("WHATSAPP_RATE_LIMIT", "99")
        monkeypatch.setenv("WHATSAPP_MAX_RETRIES", "7")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        cm = ConfigManager(tmp_path / "missing.yaml")
        assert cm.get_config().whatsapp.rate_limit_delay == 99
        assert cm.get_config().whatsapp.max_retries == 7
        assert cm.get_config().logging.level == "WARNING"

    def test_env_overrides_beat_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("whatsapp:\n  rate_limit_delay: 45\n")
        monkeypatch.setenv("WHATSAPP_RATE_LIMIT", "10")
        cm = ConfigManager(cfg)
        assert cm.get_config().whatsapp.rate_limit_delay == 10

    def test_whatsapp_settings_is_flat_dict(self, tmp_path: Path):
        cm = ConfigManager(tmp_path / "missing.yaml")
        settings = cm.whatsapp_settings()
        assert settings["rate_limit_delay"] == 20
        assert "wait_time" in settings and "max_retries" in settings
        assert all(not isinstance(v, dict) for v in settings.values())
