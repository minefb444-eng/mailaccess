from __future__ import annotations

import logging
import time
from typing import Any

from telebot import TeleBot, types

from .api_client import WorkerApiClient
from .config import BotConfig
from .formatting import (
    build_profile_text,
    extract_otp,
    format_time,
    is_valid_email,
    parse_email_preview,
    safe_shorten,
    sanitize,
    shorten,
)
from .keyboards import (
    build_accounts_keyboard,
    build_admin_panel,
    build_inbox_keyboard,
    build_logout_specific_keyboard,
    build_main_menu,
)
from .polling import PollingManager
from .state import BotState

LOGGER = logging.getLogger(__name__)


class BotHandlers:
    def __init__(
        self,
        bot: TeleBot,
        config: BotConfig,
        state: BotState,
        api_client: WorkerApiClient,
        polling_manager: PollingManager,
    ) -> None:
        self.bot = bot
        self.config = config
        self.state = state
        self.api_client = api_client
        self.polling_manager = polling_manager
        self._register()

    def _register(self) -> None:
        bot = self.bot

        @bot.message_handler(commands=["start", "menu"])
        def show_menu(message: types.Message) -> None:
            self._show_main_menu(message)

        @bot.message_handler(func=lambda m: m.text == "🎁 Invite Friends")
        def invite_friends(message: types.Message) -> None:
            self._invite_friends(message)

        @bot.message_handler(func=lambda m: m.text == "👤 My Profile")
        def profile(message: types.Message) -> None:
            self._profile(message)

        @bot.message_handler(func=lambda m: m.text == "🔐 Admin Panel")
        def admin_panel(message: types.Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            bot.reply_to(message, "<b>🔧 Admin Panel</b>\nChoose an action:", reply_markup=build_admin_panel())

        @bot.callback_query_handler(func=lambda c: c.data.startswith("adm|"))
        def admin_callbacks(call: types.CallbackQuery) -> None:
            self._handle_admin_callback(call)

        @bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
        def admin_delete_confirm(call: types.CallbackQuery) -> None:
            self._handle_admin_delete_confirm(call)

        @bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
        def broadcast_prompt(message: types.Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            msg = bot.send_message(message.chat.id, "📝 Send your announcement message:")
            bot.register_next_step_handler(
                msg,
                lambda next_message, expected_uid=message.from_user.id: self._process_broadcast(next_message, expected_uid),
            )

        @bot.message_handler(func=lambda m: m.text == "📩 Login / Add Account")
        def login_prompt(message: types.Message) -> None:
            msg = bot.send_message(message.chat.id, "📧 Enter email address:")
            bot.register_next_step_handler(
                msg,
                lambda next_message, expected_uid=message.from_user.id: self._login_email_step(next_message, expected_uid),
            )

        @bot.message_handler(func=lambda m: m.text == "🔗 Connected Mails")
        def connected_mails(message: types.Message) -> None:
            self._connected_mails(message)

        @bot.callback_query_handler(func=lambda c: c.data.startswith("vw|"))
        def view_inbox(call: types.CallbackQuery) -> None:
            self._view_inbox_callback(call)

        @bot.callback_query_handler(func=lambda c: c.data.startswith("sr|"))
        def search_inbox(call: types.CallbackQuery) -> None:
            self._search_callback(call)

        @bot.callback_query_handler(func=lambda c: c.data.startswith("rd|"))
        def read_mail(call: types.CallbackQuery) -> None:
            self._read_callback(call)

        @bot.message_handler(func=lambda m: m.text == "🔌 Logout Specific")
        def logout_specific(message: types.Message) -> None:
            self._logout_specific(message)

        @bot.callback_query_handler(func=lambda c: c.data.startswith("lo|"))
        def logout_specific_callback(call: types.CallbackQuery) -> None:
            self._logout_callback(call)

        @bot.message_handler(func=lambda m: m.text == "❌ Logout All")
        def logout_all(message: types.Message) -> None:
            self.state.logout_all(message.from_user.id)
            self.state.save_sessions()
            bot.send_message(message.chat.id, "✅ All accounts disconnected.")

        @bot.callback_query_handler(func=lambda c: c.data == "close")
        def close_message(call: types.CallbackQuery) -> None:
            bot.answer_callback_query(call.id)
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                try:
                    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
                except Exception:
                    pass

        @bot.callback_query_handler(func=lambda c: c.data == "noop")
        def noop(call: types.CallbackQuery) -> None:
            bot.answer_callback_query(call.id)

    # ---------- common ----------
    def _is_admin(self, user_id: int) -> bool:
        return self.config.admin_id != 0 and user_id == self.config.admin_id

    def _log_activity(self, text: str) -> None:
        if not self.config.log_channel_id:
            return
        try:
            self.bot.send_message(self.config.log_channel_id, text)
        except Exception as exc:
            LOGGER.warning("Failed to write log activity: %s", exc)

    @staticmethod
    def _same_user_or_ignore(message: types.Message, expected_uid: int) -> bool:
        return message.from_user.id == expected_uid

    def _show_main_menu(self, message: types.Message) -> None:
        markup = build_main_menu(is_admin=self._is_admin(message.from_user.id))
        text = (
            "👋 <b>Welcome to Mail Access Bot</b>\n\n"
            "Connect your mail account, read new emails, and quickly copy OTP codes."
        )
        self.bot.send_message(message.chat.id, text, reply_markup=markup)

    def _invite_friends(self, message: types.Message) -> None:
        try:
            bot_username = self.bot.get_me().username
            link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
            text = (
                "🎁 <b>Invite & Earn</b>\n\n"
                "Share your personal referral link with friends.\n"
                "When they buy, you can earn rewards.\n\n"
                f"🔗 <code>{sanitize(link)}</code>"
            )
            self.bot.send_message(message.chat.id, text)
        except Exception:
            self.bot.send_message(message.chat.id, "❌ Could not create your referral link right now.")

    # ---------- profile ----------
    def _profile(self, message: types.Message) -> None:
        status_code, payload = self.api_client.post_json("/user/my_accounts", {"user_id": message.from_user.id})
        if status_code != 200 or not isinstance(payload, list):
            self.bot.send_message(message.chat.id, "❌ Failed to load profile. Please try again.")
            return
        self.bot.send_message(message.chat.id, build_profile_text(payload))

    # ---------- admin ----------
    def _handle_admin_callback(self, call: types.CallbackQuery) -> None:
        if not self._is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
            return
        self.bot.answer_callback_query(call.id)

        action = call.data.split("|", 1)[1]
        if action == "stats":
            self._admin_stats(call)
        elif action == "bulk":
            msg = self.bot.send_message(call.message.chat.id, "⏳ Enter rental duration in days (0 = Unlimited):")
            self.bot.register_next_step_handler(
                msg,
                lambda message, expected_uid=call.from_user.id: self._bulk_days_step(message, expected_uid),
            )
        elif action == "edit":
            msg = self.bot.send_message(call.message.chat.id, "✏️ Enter target email address:")
            self.bot.register_next_step_handler(
                msg,
                lambda message, expected_uid=call.from_user.id: self._edit_password_email_step(message, expected_uid),
            )
        elif action == "delete":
            self._admin_delete_list(call)
        elif action == "cancel":
            try:
                self.bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass

    def _admin_stats(self, call: types.CallbackQuery) -> None:
        status_code, payload = self.api_client.post_json("/admin/stats")
        if status_code != 200 or not isinstance(payload, list):
            self.bot.send_message(call.message.chat.id, "❌ Could not fetch admin stats right now.")
            return

        users = payload
        lines = [f"📊 <b>System Status ({len(users)})</b>", ""]
        for account in users[:15]:
            owner = account.get("owner_name") or "❌ Unused"
            lines.extend(
                [
                    f"📧 <b>{sanitize(account.get('email', 'N/A'))}</b>",
                    f"👤 {sanitize(owner)}",
                    "➖➖➖➖➖",
                ]
            )
        if len(users) > 15:
            lines.append(f"<i>...and {len(users) - 15} more.</i>")
        self.bot.edit_message_text(
            "\n".join(lines),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_admin_panel(),
        )

    def _bulk_days_step(self, message: types.Message, expected_uid: int) -> None:
        if not self._same_user_or_ignore(message, expected_uid) or not self._is_admin(message.from_user.id):
            return
        try:
            days = int(message.text.strip())
            if days < 0:
                raise ValueError
        except ValueError:
            self.bot.send_message(message.chat.id, "❌ Please send a valid number (0 or greater).")
            return
        hours = days * 24
        msg = self.bot.send_message(
            message.chat.id,
            "📧 Paste emails (one per line):",
        )
        self.bot.register_next_step_handler(
            msg,
            lambda next_message, expected=expected_uid, rental_hours=hours: self._bulk_emails_step(
                next_message,
                expected,
                rental_hours,
            ),
        )

    def _bulk_emails_step(self, message: types.Message, expected_uid: int, hours: int) -> None:
        if not self._same_user_or_ignore(message, expected_uid) or not self._is_admin(message.from_user.id):
            return
        lines = [line.strip() for line in message.text.splitlines() if line.strip()]
        valid_emails = [address for address in lines if is_valid_email(address)]
        if not valid_emails:
            self.bot.send_message(message.chat.id, "❌ No valid email addresses detected.")
            return
        msg = self.bot.send_message(message.chat.id, "🔑 Enter password for all listed accounts:")
        self.bot.register_next_step_handler(
            msg,
            lambda next_message, expected=expected_uid, addresses=valid_emails, rental_hours=hours: self._bulk_password_step(
                next_message,
                expected,
                addresses,
                rental_hours,
            ),
        )

    def _bulk_password_step(self, message: types.Message, expected_uid: int, emails: list[str], hours: int) -> None:
        if not self._same_user_or_ignore(message, expected_uid) or not self._is_admin(message.from_user.id):
            return
        password = message.text.strip()
        if not password:
            self.bot.send_message(message.chat.id, "❌ Password cannot be empty.")
            return

        created = 0
        for email_address in emails:
            status_code, _payload = self.api_client.post_json(
                "/admin/create",
                {"email": email_address, "password": password, "duration_hours": hours},
            )
            if status_code == 200:
                created += 1
        self._log_activity(f"💰 <b>Bulk Created</b>\nAdmin added {created}/{len(emails)} accounts ({hours}h).")
        self.bot.send_message(message.chat.id, f"✅ Bulk operation completed: {created}/{len(emails)} created.")

    def _edit_password_email_step(self, message: types.Message, expected_uid: int) -> None:
        if not self._same_user_or_ignore(message, expected_uid) or not self._is_admin(message.from_user.id):
            return
        email_address = message.text.strip()
        if not is_valid_email(email_address):
            self.bot.send_message(message.chat.id, "❌ Invalid email format.")
            return
        msg = self.bot.send_message(message.chat.id, "🔑 Enter new password:")
        self.bot.register_next_step_handler(
            msg,
            lambda next_message, expected=expected_uid, target_email=email_address: self._edit_password_final(
                next_message,
                expected,
                target_email,
            ),
        )

    def _edit_password_final(self, message: types.Message, expected_uid: int, email_address: str) -> None:
        if not self._same_user_or_ignore(message, expected_uid) or not self._is_admin(message.from_user.id):
            return
        new_password = message.text.strip()
        if not new_password:
            self.bot.send_message(message.chat.id, "❌ Password cannot be empty.")
            return
        status_code, _payload = self.api_client.post_json(
            "/admin/update_password",
            {"email": email_address, "new_password": new_password},
        )
        if status_code == 200:
            self.bot.send_message(message.chat.id, "✅ Password updated successfully.")
        else:
            self.bot.send_message(message.chat.id, "❌ Failed to update password.")

    def _admin_delete_list(self, call: types.CallbackQuery) -> None:
        status_code, payload = self.api_client.post_json("/admin/list")
        if status_code != 200 or not isinstance(payload, list) or not payload:
            self.bot.send_message(call.message.chat.id, "⚠️ No accounts found.")
            return
        markup = types.InlineKeyboardMarkup()
        for account in payload:
            email_address = str(account.get("email", "")).strip()
            if not email_address:
                continue
            token = self.state.create_ephemeral_token(call.from_user.id, email_address, ttl_seconds=1200)
            markup.add(types.InlineKeyboardButton(f"🗑️ {shorten(email_address, 40)}", callback_data=f"del|{token}"))
        markup.add(types.InlineKeyboardButton("Cancel", callback_data="adm|cancel"))
        self.bot.edit_message_text("Select an account to delete:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    def _handle_admin_delete_confirm(self, call: types.CallbackQuery) -> None:
        if not self._is_admin(call.from_user.id):
            self.bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
            return
        token = call.data.split("|", 1)[1]
        email_address = self.state.resolve_ephemeral_token(call.from_user.id, token)
        if not email_address:
            self.bot.answer_callback_query(call.id, "This action has expired.", show_alert=True)
            return
        self.bot.answer_callback_query(call.id)
        status_code, _payload = self.api_client.post_json("/admin/delete", {"email": email_address})
        if status_code == 200:
            self.bot.edit_message_text(
                f"✅ Deleted <code>{sanitize(email_address)}</code>",
                call.message.chat.id,
                call.message.message_id,
            )
        else:
            self.bot.edit_message_text(
                f"❌ Failed to delete <code>{sanitize(email_address)}</code>",
                call.message.chat.id,
                call.message.message_id,
            )

    def _process_broadcast(self, message: types.Message, expected_uid: int) -> None:
        if not self._same_user_or_ignore(message, expected_uid) or not self._is_admin(message.from_user.id):
            return
        text = message.text.strip()
        if not text:
            self.bot.send_message(message.chat.id, "❌ Broadcast cannot be empty.")
            return
        sent = 0
        for user_id in self.state.list_user_ids():
            try:
                self.bot.send_message(user_id, f"📢 <b>Announcement</b>\n\n{sanitize(text)}")
                sent += 1
            except Exception as exc:
                LOGGER.warning("Broadcast failed for user_id=%s: %s", user_id, exc)
        self.bot.send_message(message.chat.id, f"✅ Broadcast sent to {sent} users.")

    # ---------- login ----------
    def _login_email_step(self, message: types.Message, expected_uid: int) -> None:
        if not self._same_user_or_ignore(message, expected_uid):
            return
        email_address = message.text.strip()
        if not is_valid_email(email_address):
            self.bot.send_message(message.chat.id, "❌ Invalid email format.")
            return
        msg = self.bot.send_message(message.chat.id, f"🔑 Enter password for <code>{sanitize(email_address)}</code>:")
        self.bot.register_next_step_handler(
            msg,
            lambda next_message, expected=expected_uid, target_email=email_address: self._login_password_step(
                next_message,
                expected,
                target_email,
            ),
        )

    def _login_password_step(self, message: types.Message, expected_uid: int, email_address: str) -> None:
        if not self._same_user_or_ignore(message, expected_uid):
            return
        password = message.text.strip()
        if not password:
            self.bot.send_message(message.chat.id, "❌ Password cannot be empty.")
            return
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or "Unknown"
        status_code, payload = self.api_client.post_json(
            "/check_auth",
            {"email": email_address, "password": password, "user_id": user_id, "username": username},
        )
        if status_code is None:
            self.bot.send_message(message.chat.id, "❌ Connection error. Please try again.")
            return
        if status_code != 200 or not isinstance(payload, dict):
            self.bot.send_message(message.chat.id, "❌ Invalid response from auth server.")
            return
        if not payload.get("valid"):
            self.bot.send_message(message.chat.id, "❌ Access denied. Check credentials.")
            return

        account_id, _new_user = self.state.ensure_account(
            user_id=user_id,
            chat_id=message.chat.id,
            email=email_address,
            password=password,
            last_ms=int(time.time() * 1000),
        )
        self.state.save_sessions()
        self.polling_manager.ensure_user_thread(user_id)
        self._log_activity(
            f"👤 <b>New Login</b>\nUser: {sanitize(username)} ({user_id})\nEmail: {sanitize(email_address)}"
        )
        self.bot.send_message(message.chat.id, f"✅ Connected <code>{sanitize(email_address)}</code> successfully.")
        self._show_inbox(message.chat.id, user_id, account_id, 1)

    # ---------- inbox ----------
    def _connected_mails(self, message: types.Message) -> None:
        accounts = self.state.get_accounts(message.from_user.id)
        if not accounts:
            self.bot.send_message(message.chat.id, "⚠️ No active connected accounts.")
            return
        markup = build_accounts_keyboard(accounts)
        self.bot.send_message(message.chat.id, "📂 Select an account:", reply_markup=markup)

    def _view_inbox_callback(self, call: types.CallbackQuery) -> None:
        self.bot.answer_callback_query(call.id)
        parts = call.data.split("|")
        if len(parts) != 3:
            return
        _, account_id, page_raw = parts
        try:
            page = max(1, int(page_raw))
        except ValueError:
            return
        try:
            self.bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        self._show_inbox(call.message.chat.id, call.from_user.id, account_id, page)

    def _show_inbox(self, chat_id: int, user_id: int, account_id: str, page: int) -> None:
        credentials = self.state.get_credentials_by_account_id(user_id, account_id)
        if not credentials:
            self.bot.send_message(chat_id, "⚠️ Account not found or disconnected.")
            return

        email_address, password, _last_check = credentials
        query = self.state.get_search(user_id, account_id)
        status_code, payload = self.api_client.post_json(
            "/get_inbox_view",
            {"email": email_address, "password": password, "page": page, "query": query},
        )
        if status_code == 401:
            removed_email = self.state.remove_account(user_id, account_id)
            if removed_email:
                self.state.save_sessions()
            self.bot.send_message(chat_id, f"🔒 Session expired for <code>{sanitize(email_address)}</code>.")
            return

        emails = payload if isinstance(payload, list) else []
        token = self.state.store_snapshot(user_id, account_id, emails)
        subjects = [str(item.get("subject", "(No Subject)")) for item in emails]
        markup = build_inbox_keyboard(
            account_id=account_id,
            page=page,
            query=query,
            subjects=subjects,
            snapshot_token=token,
            can_next_page=len(emails) >= 10,
        )

        heading = f"📂 <b>Inbox</b>\n📧 <code>{sanitize(email_address)}</code>\n📄 Page {page}"
        if query:
            heading += f"\n🔎 Query: <code>{sanitize(query)}</code>"
        self.bot.send_message(chat_id, heading, reply_markup=markup)

    def _search_callback(self, call: types.CallbackQuery) -> None:
        parts = call.data.split("|")
        if len(parts) != 2:
            self.bot.answer_callback_query(call.id)
            return
        account_id = parts[1]
        current_query = self.state.get_search(call.from_user.id, account_id)
        if current_query:
            self.state.set_search(call.from_user.id, account_id, "")
            self.bot.answer_callback_query(call.id, "Search cleared")
            self._show_inbox(call.message.chat.id, call.from_user.id, account_id, 1)
            return

        self.bot.answer_callback_query(call.id)
        msg = self.bot.send_message(
            call.message.chat.id,
            "🔍 Send a search term.\nUse <code>clear</code> to remove active search.",
        )
        self.bot.register_next_step_handler(
            msg,
            lambda message, expected_uid=call.from_user.id, aid=account_id: self._process_search(
                message,
                expected_uid,
                aid,
            ),
        )

    def _process_search(self, message: types.Message, expected_uid: int, account_id: str) -> None:
        if not self._same_user_or_ignore(message, expected_uid):
            return
        query = message.text.strip()
        if not query or query.lower() == "clear":
            self.state.set_search(message.from_user.id, account_id, "")
        else:
            self.state.set_search(message.from_user.id, account_id, query)
        self._show_inbox(message.chat.id, message.from_user.id, account_id, 1)

    def _read_callback(self, call: types.CallbackQuery) -> None:
        parts = call.data.split("|")
        if len(parts) != 3:
            self.bot.answer_callback_query(call.id)
            return
        _, token, index_raw = parts
        try:
            index = int(index_raw)
        except ValueError:
            self.bot.answer_callback_query(call.id, "Invalid selection", show_alert=True)
            return
        mail = self.state.get_snapshot_mail(call.from_user.id, token, index)
        if not mail:
            self.bot.answer_callback_query(call.id, "This list expired. Please refresh.", show_alert=True)
            return
        self.bot.answer_callback_query(call.id)

        web_link = f"{self.config.worker_url}/view_email?id={mail.get('id', '')}"
        subject = safe_shorten(mail.get("subject", "(No Subject)"), 80)
        sender = safe_shorten(mail.get("sender", "Unknown"), 80)
        received = sanitize(format_time(mail.get("received_at")))
        body_preview = parse_email_preview(mail.get("body", ""))
        otp = extract_otp(body_preview) or extract_otp(mail.get("subject", ""))

        text = (
            f"📨 <b>Email Details</b>\n"
            f"👤 From: {sender}\n"
            f"📌 Subject: {subject}\n"
            f"📅 Time: {received or 'Unknown'}\n"
            f"➖➖➖➖➖➖➖\n"
            f"Tap below to open the full email."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🌍 View Full Email", url=web_link))
        markup.add(types.InlineKeyboardButton("❌ Close", callback_data="close"))
        self.bot.send_message(call.message.chat.id, text, reply_markup=markup)
        if otp:
            self.bot.send_message(call.message.chat.id, f"🔐 OTP: <code>{sanitize(otp)}</code>")

    # ---------- logout ----------
    def _logout_specific(self, message: types.Message) -> None:
        accounts = self.state.get_accounts(message.from_user.id)
        if not accounts:
            self.bot.send_message(message.chat.id, "⚠️ No accounts to disconnect.")
            return
        self.bot.send_message(
            message.chat.id,
            "Select an account to disconnect:",
            reply_markup=build_logout_specific_keyboard(accounts),
        )

    def _logout_callback(self, call: types.CallbackQuery) -> None:
        parts = call.data.split("|")
        if len(parts) != 2:
            self.bot.answer_callback_query(call.id)
            return
        account_id = parts[1]
        removed_email = self.state.remove_account(call.from_user.id, account_id)
        if not removed_email:
            self.bot.answer_callback_query(call.id, "Account already removed.", show_alert=True)
            return
        self.bot.answer_callback_query(call.id)
        self.state.save_sessions()
        self.bot.edit_message_text(
            f"✅ Disconnected <code>{sanitize(removed_email)}</code>",
            call.message.chat.id,
            call.message.message_id,
        )
