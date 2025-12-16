"""Application configuration helpers."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Type


class BaseConfig:
    """Base configuration shared across environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///pfm.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SQLALCHEMY_ECHO = bool(int(os.getenv("SQLALCHEMY_ECHO", "0")))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Gmail API Configuration
    GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
    GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
    GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "data/gmail_token.pickle")

    @staticmethod
    def init_app(app) -> None:
        """Hook for app-specific initialization."""
        # No-op for now; reserved for future logging or telemetry wiring.
        return None


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIG_MAP: dict[str, Type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> Type[BaseConfig]:
    """Return the config class associated with the supplied name."""
    if not name:
        name = os.getenv("FLASK_CONFIG", "development")
    return CONFIG_MAP.get(name, DevelopmentConfig)


def adjust_sqlite_connect_args(app_config: BaseConfig) -> None:
    """Ensure SQLite connections allow usage from different threads when needed."""
    uri = app_config.SQLALCHEMY_DATABASE_URI
    if uri.startswith("sqlite"):
        engine_options = dict(app_config.SQLALCHEMY_ENGINE_OPTIONS)
        connect_args = engine_options.get("connect_args", {})
        connect_args.setdefault("check_same_thread", False)
        engine_options["connect_args"] = connect_args
        app_config.SQLALCHEMY_ENGINE_OPTIONS = engine_options
