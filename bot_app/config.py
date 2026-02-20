from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SharedRuntimeConfig:
    worker_url: str
    bot_secret: str
    session_file: str
    request_timeout_seconds: int


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    worker_url: str
    bot_secret: str
    admin_id: int
    log_channel_id: Optional[int]
    session_file: str = "sessions.json"
    poll_interval_seconds: int = 5
    request_timeout_seconds: int = 10


@dataclass(frozen=True)
class WebConfig:
    worker_url: str
    bot_secret: str
    session_file: str
    request_timeout_seconds: int
    web_session_secret: str
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_session_cookie_name: str = "mailaccess_web_session"
    web_session_https_only: bool = False


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _load_shared_runtime_config() -> SharedRuntimeConfig:
    bot_secret = os.getenv("BOT_SECRET", "").strip()
    worker_url = os.getenv("WORKER_URL", "https://mail.htat.xyz").strip().rstrip("/")
    if not bot_secret:
        raise ValueError("BOT_SECRET is required and cannot be empty.")
    if not worker_url.startswith("http"):
        raise ValueError("WORKER_URL must be an absolute http(s) URL.")

    timeout_seconds = max(1, _int_env("REQUEST_TIMEOUT_SECONDS", 10))
    session_file = os.getenv("SESSION_FILE", "sessions.json").strip() or "sessions.json"
    return SharedRuntimeConfig(
        worker_url=worker_url,
        bot_secret=bot_secret,
        session_file=session_file,
        request_timeout_seconds=timeout_seconds,
    )


def load_config() -> BotConfig:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("BOT_TOKEN is required and cannot be empty.")

    shared = _load_shared_runtime_config()

    admin_id = _int_env("ADMIN_ID", 0)
    log_channel_id_raw = _int_env("LOG_CHANNEL_ID", 0)
    log_channel_id = log_channel_id_raw if log_channel_id_raw != 0 else None
    poll_interval_seconds = max(1, _int_env("POLL_INTERVAL_SECONDS", 5))

    return BotConfig(
        bot_token=bot_token,
        worker_url=shared.worker_url,
        bot_secret=shared.bot_secret,
        admin_id=admin_id,
        log_channel_id=log_channel_id,
        session_file=shared.session_file,
        poll_interval_seconds=poll_interval_seconds,
        request_timeout_seconds=shared.request_timeout_seconds,
    )


def load_web_config() -> WebConfig:
    shared = _load_shared_runtime_config()
    web_session_secret = os.getenv("WEB_SESSION_SECRET", "").strip()
    if not web_session_secret:
        raise ValueError("WEB_SESSION_SECRET is required and cannot be empty.")
    return WebConfig(
        worker_url=shared.worker_url,
        bot_secret=shared.bot_secret,
        session_file=shared.session_file,
        request_timeout_seconds=shared.request_timeout_seconds,
        web_session_secret=web_session_secret,
        web_host=os.getenv("WEB_HOST", "0.0.0.0").strip() or "0.0.0.0",
        web_port=max(1, _int_env("WEB_PORT", 8080)),
        web_session_cookie_name=os.getenv("WEB_SESSION_COOKIE_NAME", "mailaccess_web_session").strip()
        or "mailaccess_web_session",
        web_session_https_only=bool(_int_env("WEB_SESSION_HTTPS_ONLY", 0)),
    )
