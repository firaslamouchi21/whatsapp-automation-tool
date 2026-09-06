import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class WhatsAppConfig:
    rate_limit_delay: int = 20
    wait_time: int = 10
    tab_close: bool = True
    close_time: int = 3
    max_retries: int = 3


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_file: Path = Path("logs/whatsapp_automation.log")
    max_file_size: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class ProcessingConfig:
    batch_size: int = 100
    parallel_processing: bool = False
    max_workers: int = 4
    resume_on_failure: bool = True


@dataclass
class AppConfig:
    whatsapp: WhatsAppConfig
    logging: LoggingConfig
    processing: ProcessingConfig
    templates_dir: Path = Path("config/templates")
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")


class ConfigManager:

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or Path("config/config.yaml")
        self.config = self._load_config()

    def _load_config(self) -> AppConfig:
        if self.config_file.exists():
            return self._load_from_file()
        return self._get_default_config()

    def _load_from_file(self) -> AppConfig:
        import yaml

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            return AppConfig(
                whatsapp=WhatsAppConfig(**data.get("whatsapp", {})),
                logging=LoggingConfig(**data.get("logging", {})),
                processing=ProcessingConfig(**data.get("processing", {})),
                templates_dir=Path(data.get("templates_dir", "config/templates")),
                data_dir=Path(data.get("data_dir", "data")),
                output_dir=Path(data.get("output_dir", "output")),
            )

        except Exception as e:
            raise RuntimeError(f"Error loading config: {e}")

    def _get_default_config(self) -> AppConfig:
        return AppConfig(
            whatsapp=WhatsAppConfig(), logging=LoggingConfig(), processing=ProcessingConfig()
        )

    def save_config(self) -> None:
        import yaml

        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.dump(asdict(self.config), f, default_flow_style=False)

    def get_config(self) -> AppConfig:
        return self.config

    def update_config(self, updates: Dict[str, Any]) -> None:
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

    def get_env_overrides(self) -> Dict[str, Any]:
        overrides = {}

        env_mappings = {
            "WHATSAPP_RATE_LIMIT": ("whatsapp", "rate_limit_delay", int),
            "WHATSAPP_WAIT_TIME": ("whatsapp", "wait_time", int),
            "LOG_LEVEL": ("logging", "level", str),
            "LOG_FILE": ("logging", "log_file", Path),
            "BATCH_SIZE": ("processing", "batch_size", int),
        }

        for env_var, (section, key, type_func) in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                if section not in overrides:
                    overrides[section] = {}
                overrides[section][key] = type_func(value)

        return overrides
