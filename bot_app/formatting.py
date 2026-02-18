from __future__ import annotations

import email
import html
import re
import time
from datetime import datetime
from email.policy import default
from typing import Any, Iterable

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OTP_PATTERN = re.compile(r"\b(?<!\d)(\d{4,8})(?!\d)\b")


def sanitize(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.match(value.strip()))


def parse_email_preview(raw_text: str) -> str:
    if not raw_text:
        return "(View Online)"
    try:
        msg = email.message_from_string(raw_text, policy=default)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_content()
                    break
        elif msg.get_content_type() == "text/plain":
            body = msg.get_content()
        return (body or "(View Online)").strip()
    except Exception:
        return "(Unreadable)"


def extract_otp(text: str | None) -> str | None:
    if not text:
        return None
    match = OTP_PATTERN.search(text)
    return match.group(1) if match else None


def format_time(timestamp_ms: Any) -> str:
    if not timestamp_ms:
        return ""
    try:
        return datetime.fromtimestamp(int(timestamp_ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def get_time_left(expires_at: Any) -> str:
    if not expires_at:
        return "♾️ Unlimited"
    try:
        diff = (int(expires_at) - int(time.time() * 1000)) / 1000
        if diff <= 0:
            return "🔴 Expired"
        days = int(diff // 86400)
        hours = int((diff % 86400) // 3600)
        return f"{days}d {hours}h"
    except Exception:
        return "⚠️ Unknown"


def shorten(value: str, limit: int) -> str:
    text = value.strip() if value else ""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return "…"
    return text[: limit - 1] + "…"


def build_profile_text(accounts: Iterable[dict[str, Any]]) -> str:
    rows = list(accounts)
    if not rows:
        return "👤 <b>My Profile</b>\n\nNo active rentals yet."
    lines = [f"👤 <b>My Active Rentals ({len(rows)})</b>", ""]
    for acc in rows:
        lines.extend(
            [
                f"📧 <code>{sanitize(acc.get('email', 'N/A'))}</code>",
                f"🔑 <code>{sanitize(acc.get('password', 'N/A'))}</code>",
                f"⏳ {sanitize(get_time_left(acc.get('expires_at')))}",
                "➖➖➖➖➖➖➖",
            ]
        )
    return "\n".join(lines)
