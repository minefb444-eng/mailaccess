from __future__ import annotations

from pathlib import Path

from bot_app.services import MailAccessService
from bot_app.state import BotState


class FakeApiClient:
    def __init__(self) -> None:
        self.inbox_calls = 0

    def post_json(self, endpoint: str, data: dict | None = None) -> tuple[int | None, object]:
        if endpoint == "/check_auth":
            return 200, {"valid": True}
        if endpoint == "/get_inbox_view":
            self.inbox_calls += 1
            return 200, [{"id": "m1", "subject": "Welcome"}]
        _ = data
        return 200, []


def test_services_share_same_persisted_session_file(tmp_path: Path) -> None:
    session_file = str(tmp_path / "sessions.json")
    api = FakeApiClient()

    telegram_state = BotState(session_file)
    web_state = BotState(session_file)
    telegram_service = MailAccessService(
        state=telegram_state,
        api_client=api,
        worker_url="https://mail.example.com",
        sync_state_each_call=True,
    )
    web_service = MailAccessService(
        state=web_state,
        api_client=api,
        worker_url="https://mail.example.com",
        sync_state_each_call=True,
    )

    connect = telegram_service.connect_account(
        user_id=777,
        chat_id=777,
        username="tg_user",
        email_address="sync@example.com",
        password="pw",
    )
    assert connect.ok is True
    assert web_service.list_accounts(777) == [(connect.account_id or "", "sync@example.com")]

    inbox = web_service.fetch_inbox(777, connect.account_id or "", page=1)
    assert inbox.ok is True
    assert inbox.snapshot_token

    removed_email = telegram_service.disconnect_account(777, connect.account_id or "")
    assert removed_email == "sync@example.com"
    assert web_service.list_accounts(777) == []
