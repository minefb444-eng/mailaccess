# Mail Access Bot + Web Portal

This project now supports both:

- Telegram bot access (existing flow)
- Web portal access (for customers who do not use Telegram)

Both channels use the same backend data source (`SESSION_FILE` + worker API).

## Highlights

- ✅ Refactored into modules (`config`, `state`, `handlers`, `polling`, `services`, etc.)
- ✅ Safer config loading (no hardcoded production token/secret defaults)
- ✅ Robust callback routing using compact account/snapshot IDs
- ✅ Thread-safe session state with atomic JSON persistence
- ✅ HTML-safe message rendering for external content
- ✅ Admin callback hardening (checks enforced in handler layer)
- ✅ FastAPI web portal with CSRF-protected forms and cookie sessions
- ✅ Login/write endpoint rate limiting for web abuse protection

## Requirements

- Python 3.10+
- Telegram bot token (for Telegram process only)
- Worker API URL and bot secret
- Web session secret (for web process only)

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Environment Variables

Required:

- `BOT_SECRET`

Required for Telegram process:

- `BOT_TOKEN`

Required for Web process:

- `WEB_SESSION_SECRET`

Optional:

- `WORKER_URL` (default: `https://mail.htat.xyz`)
- `ADMIN_ID` (default: `0`, means no admin)
- `LOG_CHANNEL_ID` (default: `0`, disables logging)
- `SESSION_FILE` (default: `sessions.json`)
- `POLL_INTERVAL_SECONDS` (default: `5`)
- `REQUEST_TIMEOUT_SECONDS` (default: `10`)
- `WEB_HOST` (default: `0.0.0.0`)
- `WEB_PORT` (default: `8080`)
- `WEB_SESSION_COOKIE_NAME` (default: `mailaccess_web_session`)
- `WEB_SESSION_HTTPS_ONLY` (default: `0`; set `1` behind HTTPS)
- `WEB_SESSION_MAX_AGE_SECONDS` (default: `43200`)
- `WEB_LOGIN_RATE_LIMIT` (default: `8`)
- `WEB_LOGIN_RATE_WINDOW_SECONDS` (default: `60`)
- `WEB_WRITE_RATE_LIMIT` (default: `45`)
- `WEB_WRITE_RATE_WINDOW_SECONDS` (default: `60`)

## Run Telegram bot

```bash
python main
```

## Run web portal

```bash
python web_main.py
```

Then open `http://<server-ip>:8080`.

## Windows RDP deployment notes

- Run Telegram and web as separate processes/services.
- Use same `SESSION_FILE` and `BOT_SECRET` in both so data stays shared.
- Put IIS/Nginx/Caddy in front of web app for HTTPS.
- Set `WEB_SESSION_HTTPS_ONLY=1` when HTTPS is enabled.
- Use provided startup scripts:
  - `scripts/windows/run_bot.bat`
  - `scripts/windows/run_web.bat`
- Copy `.env.example` values into Windows environment variables before starting services.
- Detailed guide: `docs/WINDOWS_DEPLOYMENT.md`

## Manual validation checklist

- See `docs/MANUAL_TEST_MATRIX.md` for a full end-to-end validation matrix.

## Test

```bash
pytest -q
```

## Notes

- If any token/secret was previously committed publicly, rotate it immediately.
- Session data is stored in JSON and written atomically to reduce corruption risk.
