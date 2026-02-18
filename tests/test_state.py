from pathlib import Path
import json

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


def test_load_sessions_tolerates_malformed_numeric_values(tmp_path: Path) -> None:
    session_path = tmp_path / "sessions.json"
    session_path.write_text(
        json.dumps(
            {
                "7": {
                    "active": True,
                    "chat_id": "bad-chat-id",
                    "accounts": {
                        "broken@example.com": {
                            "pass": "pw",
                            "last": "NaN",
                            "aid": "",
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    state = BotState(str(session_path))
    state.load_sessions()

    accounts = state.get_accounts(7)
    assert len(accounts) == 1
    account_id, email = accounts[0]
    assert account_id
    assert email == "broken@example.com"

    credentials = state.get_credentials_by_account_id(7, account_id)
    assert credentials is not None
    loaded_email, loaded_password, loaded_last = credentials
    assert loaded_email == "broken@example.com"
    assert loaded_password == "pw"
    assert loaded_last == 0

    active, chat_id, snapshot_accounts = state.poll_snapshot(7)
    assert active is True
    assert chat_id == 7
    assert len(snapshot_accounts) == 1
