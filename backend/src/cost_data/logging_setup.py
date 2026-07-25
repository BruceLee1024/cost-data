from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from cost_data.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "name", None) == "cost-data-file" for handler in root.handlers):
        return
    handler = TimedRotatingFileHandler(
        get_settings().log_dir / "cost-data.jsonl",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    handler.name = "cost-data-file"
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
