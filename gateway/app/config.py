from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    openai_api_key: str
    openrouter_api_key: str
    database_url: str
    redis_url: str
    gateway_master_key: str
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_routing_config() -> dict:
    config_path = Path(__file__).parent.parent / "routing_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def configure_logging(level: str = "INFO") -> None:
    import json

    class JSONFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            from datetime import datetime, timezone

            log_obj: dict = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                log_obj["exception"] = self.formatException(record.exc_info)
            extra_skip = {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            }
            for key, val in record.__dict__.items():
                if key not in extra_skip:
                    log_obj[key] = val
            return json.dumps(log_obj)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)
