from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from telebot import TeleBot

from .api_client import WorkerApiClient
from .config import BotConfig
from .formatting import extract_otp, parse_email_preview, safe_shorten, sanitize
from .state import BotState

LOGGER = logging.getLogger(__name__)


class PollingManager:
    def __init__(
        self,
        bot: TeleBot,
        config: BotConfig,
        state: BotState,
        api_client: WorkerApiClient,
        log_activity: Callable[[str], None],
    ) -> None:
        self.bot = bot
        self.config = config
        self.state = state
        self.api_client = api_client
        self.log_activity = log_activity
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.Lock()

    def ensure_user_thread(self, user_id: int) -> None:
        with self._lock:
            thread = self._threads.get(user_id)
            if thread and thread.is_alive():
                return
            worker = threading.Thread(target=self._poll_loop, args=(user_id,), daemon=True)
            self._threads[user_id] = worker
            worker.start()

    def restore_threads(self) -> None:
        for user_id, _chat_id in self.state.get_restore_candidates():
            self.ensure_user_thread(user_id)
            LOGGER.info("Restarted polling thread for user_id=%s", user_id)

    def _poll_loop(self, user_id: int) -> None:
        LOGGER.info("Started polling loop for user_id=%s", user_id)
        while True:
            self.state.load_sessions()
            active, chat_id, accounts = self.state.poll_snapshot(user_id)
            if not active or not accounts:
                LOGGER.info(
                    "Stopping polling loop for user_id=%s active=%s accounts=%s",
                    user_id,
                    active,
                    len(accounts),
                )
                return

            for email, password, last_check in accounts:
                self._poll_single_account(user_id, chat_id, email, password, last_check)
                time.sleep(1)

            time.sleep(self.config.poll_interval_seconds)

    def _poll_single_account(self, user_id: int, chat_id: int, email: str, password: str, last_check: int) -> None:
        status_code, payload = self.api_client.post_json(
            "/get_emails",
            {"email": email, "password": password, "last_check": last_check},
        )

        if status_code == 401:
            removed = self.state.remove_account_by_email(user_id, email)
            if removed:
                self.state.save_sessions()
            self._safe_send(chat_id, f"🔒 Account session expired: <code>{sanitize(email)}</code>")
            return

        if status_code != 200 or not isinstance(payload, list):
            return

        new_mails: list[dict[str, Any]] = payload
        if not new_mails:
            return

        latest_timestamp = self._latest_timestamp_or_default(new_mails, last_check)
        self.state.update_last_check(user_id, email, latest_timestamp)
        self.state.save_sessions()

        for mail in new_mails:
            self._notify_new_mail(chat_id, email, mail)

    @staticmethod
    def _latest_timestamp_or_default(new_mails: list[dict[str, Any]], fallback: int) -> int:
        timestamps: list[int] = []
        for item in new_mails:
            try:
                timestamps.append(int(item.get("received_at", 0)))
            except (TypeError, ValueError):
                continue
        return max(timestamps) if timestamps else fallback

    def _notify_new_mail(self, chat_id: int, account_email: str, mail: dict[str, Any]) -> None:
        worker_link = f"{self.config.worker_url}/view_email?id={mail.get('id', '')}"
        subject = safe_shorten(mail.get("subject", "(No Subject)"), 80)
        sender = safe_shorten(mail.get("sender", "Unknown"), 60)
        preview = parse_email_preview(mail.get("body", ""))
        otp = extract_otp(preview) or extract_otp(mail.get("subject", ""))

        text = (
            f"🔔 <b>New Email</b>\n"
            f"📧 Account: <code>{sanitize(account_email)}</code>\n"
            f"👤 From: {sender}\n"
            f"📌 Subject: {subject}"
        )
        self._safe_send_with_link(chat_id, text, worker_link)
        if otp:
            self._safe_send(chat_id, f"🔐 OTP: <code>{sanitize(otp)}</code>")

    def _safe_send_with_link(self, chat_id: int, text: str, link: str) -> None:
        from telebot import types

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🌍 View Full Email", url=link))
        markup.add(types.InlineKeyboardButton("❌ Close", callback_data="close"))
        try:
            self.bot.send_message(chat_id, text, reply_markup=markup)
        except Exception as exc:
            LOGGER.warning("Failed sending polling notification: %s", exc)

    def _safe_send(self, chat_id: int, text: str) -> None:
        try:
            self.bot.send_message(chat_id, text)
        except Exception as exc:
            LOGGER.warning("Failed to send message: %s", exc)

    def stop_user_if_needed(self, user_id: int) -> None:
        """No active cancellation primitive is needed because loops self-terminate."""
        _ = user_id

