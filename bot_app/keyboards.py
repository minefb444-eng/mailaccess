from __future__ import annotations

from typing import Iterable

from telebot import types

from .formatting import shorten


def build_main_menu(is_admin: bool) -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("📩 Login / Add Account"), types.KeyboardButton("🔗 Connected Mails"))
    markup.add(types.KeyboardButton("👤 My Profile"), types.KeyboardButton("🎁 Invite Friends"))
    markup.add(types.KeyboardButton("🔌 Logout Specific"), types.KeyboardButton("❌ Logout All"))
    if is_admin:
        markup.add(types.KeyboardButton("🔐 Admin Panel"), types.KeyboardButton("📢 Broadcast"))
    return markup


def build_admin_panel() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("📊 Stats", callback_data="adm|stats"))
    markup.row(types.InlineKeyboardButton("➕ Bulk Create", callback_data="adm|bulk"))
    markup.row(types.InlineKeyboardButton("✏️ Edit Password", callback_data="adm|edit"))
    markup.row(types.InlineKeyboardButton("🗑️ Delete Account", callback_data="adm|delete"))
    return markup


def build_accounts_keyboard(accounts: Iterable[tuple[str, str]]) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    for account_id, email in accounts:
        markup.add(types.InlineKeyboardButton(f"📂 {shorten(email, 35)}", callback_data=f"vw|{account_id}|1"))
    return markup


def build_inbox_keyboard(
    account_id: str,
    page: int,
    query: str,
    subjects: list[str],
    snapshot_token: str,
    can_next_page: bool,
) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    if not subjects:
        markup.add(types.InlineKeyboardButton("📭 Inbox Empty", callback_data="noop"))
    else:
        for index, subject in enumerate(subjects):
            markup.add(types.InlineKeyboardButton(f"✉️ {shorten(subject, 30)}", callback_data=f"rd|{snapshot_token}|{index}"))

    row = []
    if page > 1:
        row.append(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"vw|{account_id}|{page - 1}"))
    row.append(types.InlineKeyboardButton("🔍 Search" if not query else "🧹 Clear Search", callback_data=f"sr|{account_id}"))
    if can_next_page:
        row.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"vw|{account_id}|{page + 1}"))
    if row:
        markup.row(*row)

    markup.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"vw|{account_id}|1"))
    return markup


def build_logout_specific_keyboard(accounts: Iterable[tuple[str, str]]) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    for account_id, email in accounts:
        markup.add(types.InlineKeyboardButton(f"❌ {shorten(email, 35)}", callback_data=f"lo|{account_id}"))
    return markup
