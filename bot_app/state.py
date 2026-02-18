from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional


class BotState:
    def __init__(self, session_file: str) -> None:
        self.session_file = Path(session_file)
        self.lock = Lock()
        self.user_sessions: dict[int, dict[str, Any]] = {}
        self.search_cache: dict[int, dict[str, str]] = {}
        self.inbox_snapshots: dict[int, dict[str, dict[str, Any]]] = {}
        self.ephemeral_tokens: dict[str, dict[str, Any]] = {}

    # ---------- Session persistence ----------
    def load_sessions(self) -> None:
        if not self.session_file.exists():
            return
        try:
            with self.session_file.open("r", encoding="utf-8") as file:
                raw_data = json.load(file)
        except Exception:
            return

        if not isinstance(raw_data, dict):
            return

        loaded: dict[int, dict[str, Any]] = {}
        for user_id_raw, user_payload in raw_data.items():
            try:
                user_id = int(user_id_raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(user_payload, dict):
                continue
            accounts_payload = user_payload.get("accounts")
            if not isinstance(accounts_payload, dict):
                accounts_payload = {}

            accounts: dict[str, dict[str, Any]] = {}
            for email, account_payload in accounts_payload.items():
                if not isinstance(email, str) or not isinstance(account_payload, dict):
                    continue
                account_id = account_payload.get("aid") or self._new_account_id()
                accounts[email] = {
                    "pass": str(account_payload.get("pass", "")),
                    "last": int(account_payload.get("last", 0) or 0),
                    "aid": str(account_id),
                }

            loaded[user_id] = {
                "active": bool(user_payload.get("active", True)),
                "chat_id": int(user_payload.get("chat_id", user_id)),
                "accounts": accounts,
            }

        with self.lock:
            self.user_sessions = loaded

    def save_sessions(self) -> None:
        with self.lock:
            to_save = {str(uid): data for uid, data in self.user_sessions.items()}
        self._atomic_write_json(self.session_file, to_save)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
        os.replace(tmp_path, path)

    # ---------- User/account ----------
    def ensure_account(
        self,
        user_id: int,
        chat_id: int,
        email: str,
        password: str,
        last_ms: Optional[int] = None,
    ) -> tuple[str, bool]:
        with self.lock:
            user = self.user_sessions.setdefault(user_id, {"accounts": {}, "active": True, "chat_id": chat_id})
            newly_created_user = len(user["accounts"]) == 0
            user["active"] = True
            user["chat_id"] = chat_id
            account = user["accounts"].get(email)
            if account is None:
                account = {"aid": self._new_account_id(), "pass": "", "last": 0}
                user["accounts"][email] = account
            account["pass"] = password
            account["last"] = int(last_ms if last_ms is not None else time.time() * 1000)
            if not account.get("aid"):
                account["aid"] = self._new_account_id()
            return str(account["aid"]), newly_created_user

    def get_account_by_id(self, user_id: int, account_id: str) -> Optional[tuple[str, dict[str, Any]]]:
        with self.lock:
            user = self.user_sessions.get(user_id)
            if not user:
                return None
            for email, account in user.get("accounts", {}).items():
                if account.get("aid") == account_id:
                    return email, dict(account)
        return None

    def get_accounts(self, user_id: int) -> list[tuple[str, str]]:
        with self.lock:
            user = self.user_sessions.get(user_id, {})
            accounts = user.get("accounts", {})
            return [(acc.get("aid", ""), email) for email, acc in accounts.items()]

    def get_credentials_by_account_id(self, user_id: int, account_id: str) -> Optional[tuple[str, str, int]]:
        with self.lock:
            user = self.user_sessions.get(user_id)
            if not user:
                return None
            for email, account in user.get("accounts", {}).items():
                if account.get("aid") == account_id:
                    return email, str(account.get("pass", "")), int(account.get("last", 0))
        return None

    def update_last_check(self, user_id: int, email: str, last_ms: int) -> None:
        with self.lock:
            user = self.user_sessions.get(user_id)
            if not user:
                return
            account = user.get("accounts", {}).get(email)
            if account:
                account["last"] = int(last_ms)

    def remove_account(self, user_id: int, account_id: str) -> Optional[str]:
        with self.lock:
            user = self.user_sessions.get(user_id)
            if not user:
                return None
            target_email = None
            for email, account in list(user.get("accounts", {}).items()):
                if account.get("aid") == account_id:
                    target_email = email
                    del user["accounts"][email]
                    break
            if target_email is None:
                return None
            if not user["accounts"]:
                user["active"] = False
            return target_email

    def remove_account_by_email(self, user_id: int, email: str) -> bool:
        with self.lock:
            user = self.user_sessions.get(user_id)
            if not user:
                return False
            if email not in user.get("accounts", {}):
                return False
            del user["accounts"][email]
            if not user["accounts"]:
                user["active"] = False
            return True

    def logout_all(self, user_id: int) -> bool:
        with self.lock:
            existed = user_id in self.user_sessions
            if existed:
                del self.user_sessions[user_id]
            self.search_cache.pop(user_id, None)
            self.inbox_snapshots.pop(user_id, None)
            return existed

    def list_user_ids(self) -> list[int]:
        with self.lock:
            return list(self.user_sessions.keys())

    def get_restore_candidates(self) -> list[tuple[int, int]]:
        with self.lock:
            result: list[tuple[int, int]] = []
            for user_id, payload in self.user_sessions.items():
                if payload.get("active") and payload.get("accounts"):
                    result.append((user_id, int(payload.get("chat_id", user_id))))
            return result

    def poll_snapshot(self, user_id: int) -> tuple[bool, int, list[tuple[str, str, int]]]:
        with self.lock:
            user = self.user_sessions.get(user_id)
            if not user:
                return False, user_id, []
            active = bool(user.get("active"))
            chat_id = int(user.get("chat_id", user_id))
            accounts = [
                (email, str(account.get("pass", "")), int(account.get("last", 0)))
                for email, account in user.get("accounts", {}).items()
            ]
            return active, chat_id, accounts

    # ---------- Search ----------
    def set_search(self, user_id: int, account_id: str, query: str) -> None:
        with self.lock:
            per_user = self.search_cache.setdefault(user_id, {})
            if query:
                per_user[account_id] = query
            else:
                per_user.pop(account_id, None)

    def get_search(self, user_id: int, account_id: str) -> str:
        with self.lock:
            return self.search_cache.get(user_id, {}).get(account_id, "")

    # ---------- Inbox snapshots ----------
    def store_snapshot(self, user_id: int, account_id: str, emails: list[dict[str, Any]]) -> str:
        token = self._new_snapshot_token()
        now = int(time.time())
        with self.lock:
            per_user = self.inbox_snapshots.setdefault(user_id, {})
            per_user[token] = {"aid": account_id, "emails": emails, "created": now}
            if len(per_user) > 30:
                oldest_tokens = sorted(per_user.items(), key=lambda item: item[1]["created"])[:-30]
                for old_token, _ in oldest_tokens:
                    per_user.pop(old_token, None)
        return token

    def get_snapshot_mail(self, user_id: int, token: str, index: int) -> Optional[dict[str, Any]]:
        with self.lock:
            payload = self.inbox_snapshots.get(user_id, {}).get(token)
            if not payload:
                return None
            emails = payload.get("emails", [])
            if index < 0 or index >= len(emails):
                return None
            return dict(emails[index])

    # ---------- Ephemeral tokens ----------
    def create_ephemeral_token(self, owner_id: int, value: str, ttl_seconds: int = 600) -> str:
        token = secrets.token_hex(5)
        expires_at = int(time.time()) + ttl_seconds
        with self.lock:
            self.ephemeral_tokens[token] = {"owner_id": owner_id, "value": value, "expires_at": expires_at}
            self._cleanup_ephemeral_tokens_locked()
        return token

    def resolve_ephemeral_token(self, owner_id: int, token: str) -> Optional[str]:
        with self.lock:
            self._cleanup_ephemeral_tokens_locked()
            payload = self.ephemeral_tokens.get(token)
            if not payload:
                return None
            if payload.get("owner_id") != owner_id:
                return None
            return str(payload.get("value", ""))

    def _cleanup_ephemeral_tokens_locked(self) -> None:
        now = int(time.time())
        expired = [token for token, payload in self.ephemeral_tokens.items() if payload.get("expires_at", 0) <= now]
        for token in expired:
            self.ephemeral_tokens.pop(token, None)

    @staticmethod
    def _new_account_id() -> str:
        return secrets.token_hex(4)

    @staticmethod
    def _new_snapshot_token() -> str:
        return secrets.token_hex(4)
