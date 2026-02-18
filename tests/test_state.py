from pathlib import Path

from bot_app.state import BotState


def test_save_load_sessions_roundtrip(tmp_path: Path) -> None:
    session_path = tmp_path / "sessions.json"
    state = BotState(str(session_path))
    account_id, _created = state.ensure_account(
        user_id=123,
        chat_id=999,
        email="user@example.com",
        password="pass123",
        last_ms=123456,
    )
    state.save_sessions()

    loaded = BotState(str(session_path))
    loaded.load_sessions()
    credentials = loaded.get_credentials_by_account_id(123, account_id)
    assert credentials is not None
    email, password, last_check = credentials
    assert email == "user@example.com"
    assert password == "pass123"
    assert last_check == 123456


def test_remove_account_deactivates_user_when_empty(tmp_path: Path) -> None:
    state = BotState(str(tmp_path / "sessions.json"))
    account_id, _created = state.ensure_account(10, 10, "a@b.com", "pw", 1)
    removed = state.remove_account(10, account_id)
    assert removed == "a@b.com"
    active, _chat_id, accounts = state.poll_snapshot(10)
    assert active is False
    assert accounts == []


def test_ephemeral_tokens_resolve_for_owner_only(tmp_path: Path) -> None:
    state = BotState(str(tmp_path / "sessions.json"))
    token = state.create_ephemeral_token(owner_id=1, value="secret@example.com")
    assert state.resolve_ephemeral_token(owner_id=2, token=token) is None
    assert state.resolve_ephemeral_token(owner_id=1, token=token) == "secret@example.com"


def test_store_snapshot_returns_accessible_mail(tmp_path: Path) -> None:
    state = BotState(str(tmp_path / "sessions.json"))
    token = state.store_snapshot(50, "acc1", [{"id": "x", "subject": "Test"}])
    mail = state.get_snapshot_mail(50, token, 0)
    assert mail is not None
    assert mail["id"] == "x"
