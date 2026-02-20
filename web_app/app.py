from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from bot_app.api_client import WorkerApiClient
from bot_app.config import WebConfig, load_web_config
from bot_app.formatting import is_valid_email
from bot_app.services import MailAccessService
from bot_app.state import BotState


def create_app(config: WebConfig | None = None, service_override: MailAccessService | None = None) -> FastAPI:
    app_config = config or load_web_config()
    app = FastAPI(title="Mail Access Web Portal")
    app.add_middleware(
        SessionMiddleware,
        secret_key=app_config.web_session_secret,
        session_cookie=app_config.web_session_cookie_name,
        same_site="lax",
        https_only=app_config.web_session_https_only,
    )

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    service = service_override
    if service is None:
        state = BotState(app_config.session_file)
        state.load_sessions()
        api_client = WorkerApiClient(
            base_url=app_config.worker_url,
            bot_secret=app_config.bot_secret,
            timeout_seconds=app_config.request_timeout_seconds,
        )
        service = MailAccessService(
            state=state,
            api_client=api_client,
            worker_url=app_config.worker_url,
            sync_state_each_call=True,
        )

    app.state.config = app_config
    app.state.templates = templates
    app.state.service = service

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> RedirectResponse:
        if request.session.get("uid"):
            return RedirectResponse("/accounts", status_code=302)
        return RedirectResponse("/login", status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": None, "csrf_token": _ensure_csrf_token(request)},
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login(
        request: Request,
        email: str = Form(default=""),
        password: str = Form(default=""),
        csrf_token: str = Form(default=""),
    ):
        if not _validate_csrf(request, csrf_token):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid session token. Refresh and try again.", "csrf_token": _ensure_csrf_token(request)},
                status_code=400,
            )
        email_address = email.strip()
        pass_value = password.strip()
        if not is_valid_email(email_address):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Invalid email format.", "csrf_token": _ensure_csrf_token(request)},
                status_code=400,
            )
        if not pass_value:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": "Password cannot be empty.", "csrf_token": _ensure_csrf_token(request)},
                status_code=400,
            )

        user_id = _ensure_web_user_id(request)
        result = service.connect_account(
            user_id=user_id,
            chat_id=user_id,
            username=f"web_user_{user_id}",
            email_address=email_address,
            password=pass_value,
        )
        if not result.ok:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"error": _web_error_text(result.status), "csrf_token": _ensure_csrf_token(request)},
                status_code=400,
            )
        return RedirectResponse("/accounts", status_code=302)

    @app.get("/accounts", response_class=HTMLResponse)
    async def accounts(request: Request):
        user_id = request.session.get("uid")
        if not user_id:
            return RedirectResponse("/login", status_code=302)
        accounts_rows = service.list_accounts(int(user_id))
        return templates.TemplateResponse(
            request,
            "accounts.html",
            {"accounts": accounts_rows, "csrf_token": _ensure_csrf_token(request)},
        )

    @app.post("/accounts/{account_id}/logout")
    async def logout_account(
        request: Request,
        account_id: str,
        csrf_token: str = Form(default=""),
    ) -> RedirectResponse:
        user_id = request.session.get("uid")
        if not user_id:
            return RedirectResponse("/login", status_code=302)
        if _validate_csrf(request, csrf_token):
            service.disconnect_account(int(user_id), account_id)
        return RedirectResponse("/accounts", status_code=302)

    @app.post("/logout-all")
    async def logout_all(request: Request, csrf_token: str = Form(default="")) -> RedirectResponse:
        user_id = request.session.get("uid")
        if not user_id:
            return RedirectResponse("/login", status_code=302)
        if _validate_csrf(request, csrf_token):
            service.logout_all(int(user_id))
            request.session.clear()
        return RedirectResponse("/login", status_code=302)

    @app.get("/accounts/{account_id}/inbox", response_class=HTMLResponse)
    async def inbox(
        request: Request,
        account_id: str,
        page: int = 1,
    ):
        user_id = request.session.get("uid")
        if not user_id:
            return RedirectResponse("/login", status_code=302)
        inbox_result = service.fetch_inbox(int(user_id), account_id, max(1, page))
        if not inbox_result.ok:
            return templates.TemplateResponse(
                request,
                "inbox.html",
                {
                    "account_id": account_id,
                    "error": _strip_html(inbox_result.message),
                    "subjects": [],
                    "page": max(1, page),
                    "query": "",
                    "has_prev": page > 1,
                    "has_next": False,
                    "snapshot_token": "",
                    "csrf_token": _ensure_csrf_token(request),
                    "email": "",
                },
                status_code=404,
            )

        return templates.TemplateResponse(
            request,
            "inbox.html",
            {
                "account_id": inbox_result.account_id,
                "error": None,
                "subjects": list(enumerate(inbox_result.subjects)),
                "page": inbox_result.page,
                "query": inbox_result.query,
                "has_prev": inbox_result.page > 1,
                "has_next": inbox_result.can_next_page,
                "snapshot_token": inbox_result.snapshot_token,
                "csrf_token": _ensure_csrf_token(request),
                "email": inbox_result.email or "",
            },
        )

    @app.post("/accounts/{account_id}/search")
    async def set_search(
        request: Request,
        account_id: str,
        query: str = Form(default=""),
        csrf_token: str = Form(default=""),
    ) -> RedirectResponse:
        user_id = request.session.get("uid")
        if not user_id:
            return RedirectResponse("/login", status_code=302)
        if _validate_csrf(request, csrf_token):
            service.set_search(int(user_id), account_id, query)
        return RedirectResponse(f"/accounts/{account_id}/inbox?page=1", status_code=302)

    @app.get("/mail/{token}/{index}", response_class=HTMLResponse)
    async def mail_detail(request: Request, token: str, index: int):
        user_id = request.session.get("uid")
        if not user_id:
            return RedirectResponse("/login", status_code=302)
        detail = service.read_mail_detail(int(user_id), token, index)
        if not detail:
            return templates.TemplateResponse(
                request,
                "mail_detail.html",
                {"detail": None, "error": "Email list expired. Please refresh inbox."},
                status_code=404,
            )
        return templates.TemplateResponse(request, "mail_detail.html", {"detail": detail, "error": None})

    return app


def _ensure_web_user_id(request: Request) -> int:
    raw_uid = request.session.get("uid")
    if raw_uid:
        return int(raw_uid)
    uid = -max(1, secrets.randbelow(2_000_000_000))
    request.session["uid"] = uid
    return uid


def _ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if token:
        return str(token)
    token = secrets.token_urlsafe(24)
    request.session["csrf_token"] = token
    return token


def _validate_csrf(request: Request, submitted: str) -> bool:
    if not submitted:
        return False
    session_token = request.session.get("csrf_token")
    return bool(session_token and submitted == session_token)


def _web_error_text(status: str) -> str:
    if status == "access_denied":
        return "Access denied. Check your credentials."
    if status == "connection_error":
        return "Connection error. Please try again."
    return "Authentication failed."


def _strip_html(value: str) -> str:
    return value.replace("<code>", "").replace("</code>", "")
