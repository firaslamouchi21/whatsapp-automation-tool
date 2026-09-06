import logging
import sys
from pathlib import Path
from typing import Optional


class LoggerConfig:

    @staticmethod
    def setup_logger(
        name: str,
        log_file: Optional[Path] = None,
        level: int = logging.INFO,
        format_string: Optional[str] = None,
    ) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        if logger.handlers:
            return logger

        formatter = logging.Formatter(
            format_string or "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        return logger
