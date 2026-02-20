from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .api_client import WorkerApiClient
from .formatting import extract_otp, format_time, parse_email_preview, safe_shorten, sanitize
from .state import BotState


@dataclass(frozen=True)
class ConnectAccountResult:
    ok: bool
    status: str
    message: str
    account_id: Optional[str] = None
    email: Optional[str] = None


@dataclass(frozen=True)
class InboxResult:
    ok: bool
    status: str
    message: str
    account_id: Optional[str] = None
    email: Optional[str] = None
    page: int = 1
    query: str = ""
    subjects: tuple[str, ...] = ()
    snapshot_token: Optional[str] = None
    can_next_page: bool = False


@dataclass(frozen=True)
class MailDetail:
    from_sender: str
    subject: str
    received: str
    otp: Optional[str]
    view_link: str


class MailAccessService:
    def __init__(
        self,
        state: BotState,
        api_client: WorkerApiClient,
        worker_url: str,
        sync_state_each_call: bool = False,
    ) -> None:
        self.state = state
        self.api_client = api_client
        self.worker_url = worker_url.rstrip("/")
        self.sync_state_each_call = sync_state_each_call

    def connect_account(
        self,
        user_id: int,
        chat_id: int,
        username: str,
        email_address: str,
        password: str,
    ) -> ConnectAccountResult:
        self._sync_state()
        status_code, payload = self.api_client.post_json(
            "/check_auth",
            {"email": email_address, "password": password, "user_id": user_id, "username": username},
        )
        if status_code is None:
            return ConnectAccountResult(False, "connection_error", "❌ Connection error. Please try again.")
        if status_code != 200 or not isinstance(payload, dict):
            return ConnectAccountResult(False, "invalid_response", "❌ Invalid response from auth server.")
        if not payload.get("valid"):
            return ConnectAccountResult(False, "access_denied", "❌ Access denied. Check credentials.")

        account_id, _new_user = self.state.ensure_account(
            user_id=user_id,
            chat_id=chat_id,
            email=email_address,
            password=password,
            last_ms=int(time.time() * 1000),
        )
        self.state.save_sessions()
        return ConnectAccountResult(
            ok=True,
            status="connected",
            message=f"✅ Connected <code>{sanitize(email_address)}</code> successfully.",
            account_id=account_id,
            email=email_address,
        )

    def list_accounts(self, user_id: int) -> list[tuple[str, str]]:
        self._sync_state()
        return self.state.get_accounts(user_id)

    def fetch_inbox(self, user_id: int, account_id: str, page: int) -> InboxResult:
        self._sync_state()
        credentials = self.state.get_credentials_by_account_id(user_id, account_id)
        if not credentials:
            return InboxResult(False, "account_missing", "⚠️ Account not found or disconnected.")

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
            return InboxResult(
                False,
                "session_expired",
                f"🔒 Session expired for <code>{sanitize(email_address)}</code>.",
                account_id=account_id,
                email=email_address,
                page=page,
                query=query,
            )

        emails = payload if isinstance(payload, list) else []
        token = self.state.store_snapshot(user_id, account_id, emails)
        subjects = tuple(str(item.get("subject", "(No Subject)")) for item in emails)
        return InboxResult(
            True,
            "ok",
            "Inbox loaded",
            account_id=account_id,
            email=email_address,
            page=page,
            query=query,
            subjects=subjects,
            snapshot_token=token,
            can_next_page=len(emails) >= 10,
        )

    def set_search(self, user_id: int, account_id: str, query: str) -> None:
        self._sync_state()
        normalized = query.strip()
        if not normalized or normalized.lower() == "clear":
            self.state.set_search(user_id, account_id, "")
            return
        self.state.set_search(user_id, account_id, normalized)

    def get_search(self, user_id: int, account_id: str) -> str:
        self._sync_state()
        return self.state.get_search(user_id, account_id)

    def read_mail_detail(self, user_id: int, token: str, index: int) -> Optional[MailDetail]:
        self._sync_state()
        mail = self.state.get_snapshot_mail(user_id, token, index)
        if not mail:
            return None
        body_preview = parse_email_preview(mail.get("body", ""))
        otp = extract_otp(body_preview) or extract_otp(mail.get("subject", ""))
        return MailDetail(
            from_sender=safe_shorten(mail.get("sender", "Unknown"), 80),
            subject=safe_shorten(mail.get("subject", "(No Subject)"), 80),
            received=sanitize(format_time(mail.get("received_at"))) or "Unknown",
            otp=otp,
            view_link=f"{self.worker_url}/view_email?id={mail.get('id', '')}",
        )

    def disconnect_account(self, user_id: int, account_id: str) -> Optional[str]:
        self._sync_state()
        removed_email = self.state.remove_account(user_id, account_id)
        if removed_email:
            self.state.save_sessions()
        return removed_email

    def logout_all(self, user_id: int) -> bool:
        self._sync_state()
        removed = self.state.logout_all(user_id)
        self.state.save_sessions()
        return removed

    def _sync_state(self) -> None:
        if self.sync_state_each_call:
            self.state.load_sessions()
