# Windows RDP Deployment Guide (Telegram + Web)

This project runs two Python processes:

1. Telegram bot: `python main`
2. Web portal: `python web_main.py`

Both must use the same `SESSION_FILE` and `BOT_SECRET` to keep data consistent.

## 1) Install runtime

On your Windows server:

1. Install Python 3.10+.
2. Clone/copy project.
3. Install dependencies:

```bat
py -m pip install -r requirements.txt
```

## 2) Configure environment variables

Use `.env.example` as reference and set values in system/user environment (or in your service manager).

Critical shared values:

- `BOT_SECRET`
- `WORKER_URL`
- `SESSION_FILE` (same exact path for both services)

Telegram-only:

- `BOT_TOKEN`

Web-only:

- `WEB_SESSION_SECRET`
- `WEB_PORT`
- `WEB_SESSION_HTTPS_ONLY=1` (when HTTPS terminates directly at app or trusted proxy)

## 3) Start manually (smoke test)

Telegram:

```bat
scripts\windows\run_bot.bat
```

Web:

```bat
scripts\windows\run_web.bat
```

Verify web at: `http://SERVER_IP:WEB_PORT/login`

## 4) Run as persistent Windows services

Use NSSM (recommended) or Task Scheduler.

Example NSSM setup:

### Telegram service

- Application: `py`
- Arguments: `main`
- Startup dir: project directory
- Service name: `MailAccessBot`

### Web service

- Application: `py`
- Arguments: `web_main.py`
- Startup dir: project directory
- Service name: `MailAccessWeb`

Set same environment variables for both services (with shared values identical).

## 5) Reverse proxy + HTTPS

Put IIS (ARR), Nginx, or Caddy in front of web process.

Proxy target:

- `http://127.0.0.1:8080` (or your `WEB_PORT`)

Required:

- TLS certificate on public domain.
- Forward standard headers (`X-Forwarded-For`, `X-Forwarded-Proto`).
- Restrict direct public access to backend port if possible.

## 6) Restart / recovery procedure

When changing config/code:

1. Stop web service.
2. Stop bot service.
3. Deploy updated code.
4. Start bot service.
5. Start web service.
6. Verify:
   - Bot receives `/start`
   - Web login works
   - Account actions work from both channels

If `SESSION_FILE` path changes accidentally, cross-channel data will appear missing. Ensure both services point to the same file.
