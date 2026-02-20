from __future__ import annotations

from pathlib import Path

from bot_app.services import MailAccessService
from bot_app.state import BotState


class FakeApiClient:
    def __init__(self, responses: dict[str, tuple[int | None, object]]) -> None:
        self.responses = responses

    def post_json(self, endpoint: str, data: dict | None = None) -> tuple[int | None, object]:
        _ = data
        return self.responses.get(endpoint, (500, None))


def test_connect_account_success_persists_session(tmp_path: Path) -> None:
    state = BotState(str(tmp_path / "sessions.json"))
    api = FakeApiClient({"/check_auth": (200, {"valid": True})})
    service = MailAccessService(state=state, api_client=api, worker_url="https://mail.example.com")

    result = service.connect_account(
        user_id=1001,
        chat_id=1001,
        username="web_user_1001",
        email_address="demo@example.com",
        password="secret",
    )

    assert result.ok is True
    assert result.account_id
    accounts = service.list_accounts(1001)
    assert len(accounts) == 1
    assert accounts[0][1] == "demo@example.com"


def test_fetch_inbox_401_removes_account(tmp_path: Path) -> None:
    state = BotState(str(tmp_path / "sessions.json"))
    account_id, _ = state.ensure_account(55, 55, "bad@example.com", "pw", 10)
    state.save_sessions()
    api = FakeApiClient({"/get_inbox_view": (401, None)})
    service = MailAccessService(state=state, api_client=api, worker_url="https://mail.example.com")

    result = service.fetch_inbox(user_id=55, account_id=account_id, page=1)

    assert result.ok is False
    assert result.status == "session_expired"
    assert service.list_accounts(55) == []


def test_read_mail_detail_returns_otp_and_link(tmp_path: Path) -> None:
    state = BotState(str(tmp_path / "sessions.json"))
    token = state.store_snapshot(
        user_id=99,
        account_id="aid1",
        emails=[{"id": "mail1", "subject": "Code 998822", "sender": "NoReply", "body": "OTP 998822", "received_at": 0}],
    )
    api = FakeApiClient({})
    service = MailAccessService(state=state, api_client=api, worker_url="https://mail.example.com")

    detail = service.read_mail_detail(user_id=99, token=token, index=0)

    assert detail is not None
    assert detail.otp == "998822"
    assert detail.view_link.endswith("/view_email?id=mail1")
