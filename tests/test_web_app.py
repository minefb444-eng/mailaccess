from __future__ import annotations

import re

from fastapi.testclient import TestClient

from bot_app.config import WebConfig
from bot_app.services import ConnectAccountResult, InboxResult, MailDetail
from web_app.app import create_app


class FakeService:
    def __init__(self) -> None:
        self._accounts: list[tuple[str, str]] = []

    def connect_account(
        self,
        user_id: int,
        chat_id: int,
        username: str,
        email_address: str,
        password: str,
    ) -> ConnectAccountResult:
        _ = (user_id, chat_id, username, password)
        self._accounts.append(("aid1", email_address))
        return ConnectAccountResult(ok=True, status="connected", message="ok", account_id="aid1", email=email_address)

    def list_accounts(self, user_id: int) -> list[tuple[str, str]]:
        _ = user_id
        return list(self._accounts)

    def disconnect_account(self, user_id: int, account_id: str) -> str | None:
        _ = (user_id, account_id)
        return None

    def logout_all(self, user_id: int) -> bool:
        _ = user_id
        self._accounts = []
        return True

    def fetch_inbox(self, user_id: int, account_id: str, page: int) -> InboxResult:
        _ = (user_id, account_id, page)
        return InboxResult(ok=True, status="ok", message="ok", account_id="aid1", email="demo@example.com", snapshot_token="t1")

    def set_search(self, user_id: int, account_id: str, query: str) -> None:
        _ = (user_id, account_id, query)

    def read_mail_detail(self, user_id: int, token: str, index: int) -> MailDetail | None:
        _ = (user_id, token, index)
        return MailDetail(
            from_sender="Sender",
            subject="Subject",
            received="Unknown",
            otp="123456",
            view_link="https://mail.example.com/view_email?id=x",
        )


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _build_config() -> WebConfig:
    return WebConfig(
        worker_url="https://mail.example.com",
        bot_secret="secret",
        session_file="sessions.json",
        request_timeout_seconds=10,
        web_session_secret="session-secret",
        web_host="127.0.0.1",
        web_port=18080,
        web_session_cookie_name="test_session",
        web_session_https_only=False,
        web_login_rate_limit=2,
        web_login_rate_window_seconds=60,
        web_write_rate_limit=2,
        web_write_rate_window_seconds=60,
    )


def _login(client: TestClient, email: str = "demo@example.com", password: str = "pw") -> None:
    login_page = client.get("/login")
    csrf = _extract_csrf(login_page.text)
    response = client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_web_login_and_accounts_render() -> None:
    app = create_app(config=_build_config(), service_override=FakeService())
    client = TestClient(app)

    _login(client)

    accounts = client.get("/accounts")
    assert accounts.status_code == 200
    assert "demo@example.com" in accounts.text


def test_login_rejects_invalid_csrf() -> None:
    app = create_app(config=_build_config(), service_override=FakeService())
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"email": "demo@example.com", "password": "pw", "csrf_token": "bad-token"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Invalid session token" in response.text


def test_login_rate_limiter_blocks_excess_attempts() -> None:
    app = create_app(config=_build_config(), service_override=FakeService())
    client = TestClient(app)

    login_page = client.get("/login")
    csrf = _extract_csrf(login_page.text)
    first = client.post(
        "/login",
        data={"email": "a@example.com", "password": "pw", "csrf_token": csrf},
        follow_redirects=False,
    )
    second = client.post(
        "/login",
        data={"email": "b@example.com", "password": "pw", "csrf_token": csrf},
        follow_redirects=False,
    )
    third = client.post(
        "/login",
        data={"email": "c@example.com", "password": "pw", "csrf_token": csrf},
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert second.status_code == 302
    assert third.status_code == 429
    assert "Too many login attempts" in third.text


def test_write_routes_reject_bad_csrf() -> None:
    app = create_app(config=_build_config(), service_override=FakeService())
    client = TestClient(app)
    _login(client)

    bad = client.post("/accounts/aid1/search", data={"query": "otp", "csrf_token": "bad"})
    assert bad.status_code == 400
    assert "Invalid CSRF token" in bad.text
