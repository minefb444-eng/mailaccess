# Mail Access Telegram Bot

A cleaner and safer Telegram bot for managing connected mail accounts, reading inbox previews, and extracting OTP codes.

## Highlights

- ✅ Refactored into modules (`config`, `state`, `handlers`, `polling`, etc.)
- ✅ Safer config loading (no hardcoded production token/secret defaults)
- ✅ Robust callback routing using compact account/snapshot IDs
- ✅ Thread-safe session state with atomic JSON persistence
- ✅ HTML-safe message rendering for external content
- ✅ Admin callback hardening (checks enforced in handler layer)

## Requirements

- Python 3.10+
- Telegram bot token
- Worker API URL and bot secret

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Environment Variables

Required:

- `BOT_TOKEN`
- `BOT_SECRET`

Optional:

- `WORKER_URL` (default: `https://mail.htat.xyz`)
- `ADMIN_ID` (default: `0`, means no admin)
- `LOG_CHANNEL_ID` (default: `0`, disables logging)
- `SESSION_FILE` (default: `sessions.json`)
- `POLL_INTERVAL_SECONDS` (default: `5`)
- `REQUEST_TIMEOUT_SECONDS` (default: `10`)

## Run

```bash
python main
```

## Test

```bash
pytest -q
```

## Notes

- If any token/secret was previously committed publicly, rotate it immediately.
- Session data is stored in JSON and written atomically to reduce corruption risk.
