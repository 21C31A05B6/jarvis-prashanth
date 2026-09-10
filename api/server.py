"""Authenticated multi-user HTTP and Gemini Live WebSocket API.

Deployments must set JARVIS_HOSTED=1 in their process environment (see
Dockerfile / docker-compose.yml / fly.toml / render.yaml) so
memory_manager's tenant-boundary guard is active. This is deliberately NOT
set here at import time: importing this module also happens from the test
suite (and any other code that merely needs `app` for introspection),
where auto-flagging "hosted mode" as a process-wide env var would leak into
unrelated tests running in the same interpreter.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.agents import get_agent, list_agents
from agent.router import route_message
from core.api_key_validator import normalize_gemini_api_key, validate_gemini_api_key
from core.tenant import tenant_scope
from memory.memory_manager import format_memory_for_prompt, forget, load_memory, remember
from memory.semantic_search import semantic_search_memory

from .auth import get_auth_context, get_current_user, websocket_user
from .config import settings
from .database import SessionLocal, get_db, init_db
from .models import User
from .rate_limit import limiter
from .repositories import (
    add_chat_message,
    add_task_record,
    count_recent_failed_logins,
    create_calendar_event,
    create_meeting_note,
    create_notification,
    create_todo,
    delete_calendar_event,
    delete_notification,
    delete_todo,
    delete_workflow,
    get_task_record,
    has_prior_successful_login_from_ip,
    list_audit_log,
    list_calendar_events,
    list_meeting_notes,
    list_notifications,
    list_todos,
    list_workflows,
    load_user_config,
    log_audit_event,
    log_usage_event,
    mark_notification_read,
    paginated_chat_messages,
    prune_short_term_memory,
    purge_retention,
    recent_chat_messages,
    save_user_config,
    set_todo_done,
    task_history,
    update_task_record,
    usage_summary,
)
from .schemas import (
    ActivityItemOut,
    AgentOut,
    AgentPermissionsOut,
    AgentPermissionsUpdate,
    AuditLogEntryOut,
    CalendarEventCreate,
    CalendarEventOut,
    ChatHistoryPage,
    ChatRequest,
    ChatResponse,
    CommandSuggestRequest,
    CommandSuggestResult,
    ContextOut,
    DailyBriefingOut,
    DataAnalyzeRequest,
    DataAnalyzeResult,
    DataQueryRequest,
    DataQueryResult,
    DebugRequest,
    DebugResult,
    DocumentGenerateRequest,
    GenerateTestsRequest,
    GenerateTestsResult,
    GeminiKeyRequest,
    GitHubIssueCreate,
    GitHubIssueOut,
    GitHubRepoOut,
    GitHubTokenRequest,
    LoginRequest,
    MeetingNoteOut,
    MeetingSummarizeRequest,
    MemoryEntryOut,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryUpsertRequest,
    NotificationOut,
    PlanRequest,
    PlanStep,
    ResearchCompareRequest,
    ResearchReportOut,
    ResearchReportRequest,
    ReviewRequest,
    ReviewResult,
    SessionOut,
    SessionView,
    SystemHealthOut,
    TaskOut,
    TaskStepOut,
    TextSummaryOut,
    TextSummaryRequest,
    ThemePreferenceOut,
    ThemePreferenceUpdate,
    TodoCreate,
    TodoOut,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
    UsageSummaryOut,
    UserCreate,
    UserView,
    VaultEntryOut,
    VoiceOption,
    VoiceSettingsOut,
    VoiceSettingsUpdate,
    WorkflowOut,
    WSAudioMessage,
    WSCloseMessage,
    WSMuteMessage,
    WSPingMessage,
    WSTextMessage,
)
from .secret_service import (
    delete_user_secret,
    get_user_secret,
    has_user_secret,
    set_user_secret,
)
from .security import create_access_token, decode_access_token, hash_password, verify_password
from .sessions import (
    create_session,
    is_session_active,
    list_sessions,
    purge_expired_sessions,
    revoke_all_sessions,
    revoke_session,
)
from .websocket_client import WebSocketClient
from agent.two_factor import generate_secret, provisioning_uri, verify_code

logger = logging.getLogger("jarvis.api")

# Never echo raw exception text to clients (bug: internal exception messages
# can leak paths/implementation details). Log the real error server-side and
# return this instead.
GENERIC_ERROR_DETAIL = "Something went wrong on our end. Please try again."

WS_IDLE_TIMEOUT_SECONDS = 45
WS_MAX_IDLE_CYCLES = 3
WS_MAX_CONNECTION_SECONDS = 6 * 3600
WS_MESSAGE_SCHEMAS = {
    "text": WSTextMessage,
    "audio": WSAudioMessage,
    "mute": WSMuteMessage,
    "ping": WSPingMessage,
    "close": WSCloseMessage,
}


class LiveSessionRegistry:
    def __init__(self):
        self._sessions: dict[str, tuple[Any, WebSocketClient, asyncio.Task]] = {}
        self._lock = asyncio.Lock()

    async def replace(self, user_id: str, engine, client: WebSocketClient, task: asyncio.Task) -> None:
        async with self._lock:
            previous = self._sessions.pop(user_id, None)
            self._sessions[user_id] = (engine, client, task)
        if previous:
            previous[0].request_shutdown()
            previous[2].cancel()

    async def remove(self, user_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            current = self._sessions.get(user_id)
            if current and current[2] is task:
                self._sessions.pop(user_id, None)

    def status(self, user_id: str) -> dict:
        current = self._sessions.get(user_id)
        if not current:
            return {"state": "OFFLINE", "connected": False}
        engine, client, task = current
        return {
            "state": client.state,
            "connected": not task.done(),
            "voice": engine._get_current_voice(),
            "cloud_safe": True,
        }

    async def close_all(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for engine, client, task in sessions:
            engine.request_shutdown()
            task.cancel()
            await client.close()


live_sessions = LiveSessionRegistry()


async def _retention_loop() -> None:
    """Periodically purge chat/task/cache history and expired sessions past
    the configured retention window, so hosted tables don't grow without
    bound (bug: potential unbounded database growth)."""
    interval = 6 * 3600
    while True:
        try:
            await asyncio.sleep(interval)
            deleted = await asyncio.to_thread(purge_retention, settings.retention_days)
            deleted_sessions = await asyncio.to_thread(purge_expired_sessions, 30)
            deleted_short_term = await asyncio.to_thread(prune_short_term_memory, 24)
            logger.info(
                "Retention sweep: %s, sessions=%s, short_term_memory=%s",
                deleted, deleted_sessions, deleted_short_term,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Retention sweep failed")


async def _scheduler_loop() -> None:
    """Periodically run due scheduled tasks (see api/scheduler.py). Ticks
    much more often than the retention sweep since scheduled tasks (and
    reminders, which are just scheduled tasks under the hood) need to run
    close to their due time, not once every few hours."""
    from api.scheduler import run_scheduler_tick

    interval = 30
    while True:
        try:
            await asyncio.sleep(interval)
            ran = await run_scheduler_tick()
            if ran:
                logger.info("Scheduler tick ran %s due task(s)", ran)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler tick failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    if settings.auto_create_tables:
        await asyncio.to_thread(init_db)
    await limiter.connect()
    retention_task = asyncio.create_task(_retention_loop())
    scheduler_task = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        retention_task.cancel()
        scheduler_task.cancel()
        await asyncio.gather(retention_task, scheduler_task, return_exceptions=True)
        await live_sessions.close_all()
        await limiter.close()


app = FastAPI(
    title="JARVIS Cloud API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    from fastapi.responses import JSONResponse

    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_DETAIL})


def _user_view(user: User, db: Session) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        gemini_configured=has_user_secret(db, user.id, "gemini_api_key"),
        totp_enabled=user.totp_enabled,
    )


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_minutes * 60,
        path="/",
        domain=settings.cookie_domain or None,
    )


def _issue_session(response: Response, request: Request, db: Session, user: User) -> SessionView:
    token = create_access_token(user.id)
    payload = decode_access_token(token)
    create_session(
        db,
        jti=str(payload["jti"]),
        user_id=user.id,
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    _set_session_cookie(response, token)
    # The token is still returned in the body for non-browser API clients
    # (CLIs, scripts, the desktop app) that authenticate with a Bearer
    # header instead of relying on cookies. The web frontend ignores this
    # and relies solely on the httpOnly cookie set above.
    return SessionView(access_token=token, user=_user_view(user, db))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "jarvis-api"}


@app.post("/auth/signup", response_model=SessionView, status_code=201)
async def signup(payload: UserCreate, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionView:
    await limiter.consume(payload.email.lower(), "signup", 5, 3600)
    user = User(
        email=payload.email.lower().strip(),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account already exists for this email") from exc
    db.refresh(user)
    log_audit_event(user.id, "signup", ip_address=request.client.host if request.client else "")
    return _issue_session(response, request, db, user)


@app.post("/auth/login", response_model=SessionView)
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionView:
    email = payload.email.lower().strip()
    ip_address = request.client.host if request.client else ""
    await limiter.consume(email, "login", 10, 300)

    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        log_audit_event(user.id if user else None, "login_failed", detail=email, ip_address=ip_address)
        if count_recent_failed_logins(email) >= 5:
            logger.warning("Repeated failed login attempts for %s from %s", email, ip_address)
        raise HTTPException(status_code=401, detail="Email or password is incorrect")

    if user.totp_enabled:
        totp_secret = get_user_secret(db, user.id, "totp_secret")
        if not payload.totp_code or not verify_code(totp_secret, payload.totp_code):
            log_audit_event(user.id, "login_2fa_failed", ip_address=ip_address)
            raise HTTPException(status_code=401, detail="totp_required" if not payload.totp_code else "Invalid authenticator code")

    is_new_location = not has_prior_successful_login_from_ip(user.id, ip_address)
    log_audit_event(user.id, "login_success", ip_address=ip_address)
    if is_new_location:
        create_notification(
            user.id, "New sign-in detected",
            f"Your account was just signed into from a new location (IP {ip_address or 'unknown'}). "
            "If this wasn't you, change your password and review your active sessions.",
            kind="security",
        )
    return _issue_session(response, request, db, user)


@app.get("/auth/me", response_model=UserView)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserView:
    return _user_view(user, db)


@app.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    identity: tuple[User, str] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> None:
    user, jti = identity
    revoke_session(db, user.id, jti)
    log_audit_event(user.id, "logout")
    response.delete_cookie(settings.cookie_name, path="/", domain=settings.cookie_domain or None)
    return None


@app.post("/auth/logout-all", status_code=204)
def logout_all(
    response: Response,
    identity: tuple[User, str] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> None:
    user, _jti = identity
    revoke_all_sessions(db, user.id)
    log_audit_event(user.id, "logout_all_sessions")
    response.delete_cookie(settings.cookie_name, path="/", domain=settings.cookie_domain or None)
    return None


@app.get("/auth/sessions", response_model=list[SessionOut])
def get_sessions(
    identity: tuple[User, str] = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    user, current_jti = identity
    return [
        SessionOut(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            current=row.id == current_jti,
        )
        for row in list_sessions(db, user.id)
    ]


@app.delete("/auth/sessions/{session_id}", status_code=204)
def revoke_one_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not revoke_session(db, user.id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    log_audit_event(user.id, "session_revoked", detail=session_id)
    return None


@app.post("/me/gemini-key")
async def save_gemini_key(
    payload: GeminiKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    await limiter.consume(user.id, "secret", 8, 3600)
    key = normalize_gemini_api_key(payload.api_key)
    if payload.verify_key:
        validation = await asyncio.to_thread(validate_gemini_api_key, key)
        if not validation.valid:
            raise HTTPException(status_code=422, detail=validation.message)
    set_user_secret(db, user.id, "gemini_api_key", key)
    return {"configured": True}


@app.delete("/me/gemini-key", status_code=204)
def remove_gemini_key(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    delete_user_secret(db, user.id, "gemini_api_key")


@app.get("/status")
def get_status(user: User = Depends(get_current_user)) -> dict:
    return live_sessions.status(user.id)


@app.get("/actions")
def get_actions(_: User = Depends(get_current_user)) -> dict:
    from main import get_tool_declarations

    tools = get_tool_declarations(cloud_safe=True)
    return {
        "actions": [
            {"name": item["name"], "description": item.get("description", "")}
            for item in tools
        ]
    }


@app.get("/agents", response_model=list[AgentOut])
def get_agents(_: User = Depends(get_current_user)) -> list[AgentOut]:
    return [
        AgentOut(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            icon=agent.icon,
            desktop_only=agent.desktop_only,
            hosted_capable=bool(agent.hosted_tool_names) or agent.id == "planning" or agent.id == "general",
        )
        for agent in list_agents()
    ]


@app.get("/agents/permissions", response_model=AgentPermissionsOut)
def get_agent_permissions(user: User = Depends(get_current_user)) -> AgentPermissionsOut:
    config = load_user_config(user.id, namespace="agent_permissions")
    return AgentPermissionsOut(disabled_agents=config.get("disabled_agents", []))


@app.put("/agents/permissions", response_model=AgentPermissionsOut)
def update_agent_permissions(
    payload: AgentPermissionsUpdate, user: User = Depends(get_current_user),
) -> AgentPermissionsOut:
    from agent.router import is_known_agent

    for agent_id in payload.disabled_agents:
        if not is_known_agent(agent_id) or agent_id == "general":
            raise HTTPException(status_code=422, detail=f"Cannot disable unknown or general agent: {agent_id!r}")
    save_user_config(user.id, {"disabled_agents": payload.disabled_agents}, namespace="agent_permissions")
    return AgentPermissionsOut(disabled_agents=payload.disabled_agents)


@app.get("/chat/history", response_model=ChatHistoryPage)
def get_chat_history(
    user: User = Depends(get_current_user),
    limit: int = 50,
    before: datetime | None = None,
) -> ChatHistoryPage:
    """Cursor-paginated chat history retrieval, independent of the small
    fixed window used to seed the live model's prompt context."""
    items, next_before = paginated_chat_messages(user.id, limit=limit, before=before)
    return ChatHistoryPage(items=items, next_before=next_before)


def _format_plan_as_text(plan: dict) -> str:
    lines = ["Here's how I'd break that down:", ""]
    for step in plan.get("steps", []):
        lines.append(f"{step.get('step', '?')}. [{step.get('tool', '?')}] {step.get('description', '')}")
    lines.append("")
    lines.append(
        "This is a proposed plan for your awareness — the hosted chat doesn't "
        "execute multi-step plans automatically yet. Ask the Coding, Research, or "
        "another specialist agent to help with an individual step, or run this "
        "through the desktop app to execute it directly."
    )
    return "\n".join(lines)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    await limiter.consume(user.id, "chat", 30, 60)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before starting JARVIS")

    from agent.router import is_known_agent

    if payload.agent and not is_known_agent(payload.agent):
        raise HTTPException(status_code=422, detail=f"Unknown agent: {payload.agent!r}")
    agent_id = payload.agent or route_message(payload.message)
    agent = get_agent(agent_id)

    disabled_agents = load_user_config(user.id, namespace="agent_permissions").get("disabled_agents", [])
    if agent.id in disabled_agents:
        raise HTTPException(status_code=403, detail=f"The {agent.name} agent is disabled in your agent permissions.")

    if agent.desktop_only:
        raise HTTPException(
            status_code=409,
            detail=(
                f"The {agent.name} agent controls your local machine and is only "
                "available from the JARVIS desktop app, not the hosted web dashboard."
            ),
        )

    with tenant_scope(user.id):
        history = recent_chat_messages(user.id, limit=12)
        add_chat_message(user.id, "user", payload.message, agent=agent.id)
        memory = format_memory_for_prompt(load_memory())
        context = "\n".join(f"{message.role.title()}: {message.content}" for message in history)

        if agent.id == "planning":
            from agent.planner import create_plan

            try:
                plan = await asyncio.to_thread(create_plan, payload.message, context)
            except Exception:
                logger.exception("Planning agent failed for user %s", user.id)
                raise HTTPException(status_code=502, detail="Could not generate a plan")
            response_text = _format_plan_as_text(plan)
            plan_steps = [PlanStep(**step) for step in plan.get("steps", [])]
            add_chat_message(user.id, "assistant", response_text, agent=agent.id)
            log_usage_event(user.id, "/chat", input_chars=len(payload.message), output_chars=len(response_text))
            return ChatResponse(response=response_text, agent=agent.id, plan=plan_steps)

        search_snippet = ""
        if agent.id == "research" and "web_search" in agent.hosted_tool_names:
            from agent.tool_runtime import run_web_search

            try:
                search_snippet = await run_web_search(payload.message)
            except Exception:
                logger.exception("Research agent web_search failed for user %s", user.id)
                search_snippet = ""

        def generate() -> str:
            from google import genai
            from google.genai import types
            from main import _load_system_prompt

            client = genai.Client(api_key=api_key)
            prompt_parts = [f"Recent conversation:\n{context}\n\n"]
            if search_snippet:
                prompt_parts.append(f"Web search results:\n{search_snippet}\n\n")
            prompt_parts.append(f"Current user message: {payload.message}")
            prompt = "".join(prompt_parts)

            system_instruction = _load_system_prompt() + "\n\n" + memory
            if agent.system_instruction:
                system_instruction += "\n\n" + agent.system_instruction

            response = client.models.generate_content(
                model=settings.chat_model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction),
            )
            return str(response.text or "").strip()

        try:
            response_text = await asyncio.to_thread(generate)
        except Exception:
            logger.exception("Gemini chat generation failed for user %s", user.id)
            raise HTTPException(status_code=502, detail="The assistant could not generate a response")
        if not response_text:
            raise HTTPException(status_code=502, detail="Gemini returned an empty response")
        add_chat_message(user.id, "assistant", response_text, agent=agent.id)
        log_usage_event(user.id, "/chat", input_chars=len(payload.message), output_chars=len(response_text))
    return ChatResponse(response=response_text, agent=agent.id)


# --- Memory Management -----------------------------------------------------

def _flatten_memory(memory: dict) -> list[MemoryEntryOut]:
    out = []
    for category, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            value = entry.get("value") if isinstance(entry, dict) else entry
            updated = entry.get("updated", "") if isinstance(entry, dict) else ""
            if value:
                out.append(MemoryEntryOut(category=category, key=key, value=str(value), updated=updated))
    return out


@app.get("/memory", response_model=list[MemoryEntryOut])
def get_memory(
    user: User = Depends(get_current_user),
    category: str | None = None,
) -> list[MemoryEntryOut]:
    with tenant_scope(user.id):
        memory = load_memory()
    entries = _flatten_memory(memory)
    if category:
        entries = [entry for entry in entries if entry.category == category]
    return entries


@app.put("/memory", response_model=MemoryEntryOut, status_code=200)
async def upsert_memory(
    payload: MemoryUpsertRequest,
    user: User = Depends(get_current_user),
) -> MemoryEntryOut:
    await limiter.consume(user.id, "memory_write", 60, 300)
    from api.repositories import MEMORY_CATEGORIES

    category = payload.category or "notes"
    if category not in MEMORY_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown memory category: {category!r}")
    with tenant_scope(user.id):
        remember(payload.key, payload.value, category=category)
        memory = load_memory()
    entry = memory.get(category, {}).get(payload.key, {})
    return MemoryEntryOut(category=category, key=payload.key, value=str(entry.get("value", payload.value)), updated=entry.get("updated", ""))


@app.delete("/memory/{category}/{key}", status_code=204)
def delete_memory(
    category: str,
    key: str,
    user: User = Depends(get_current_user),
) -> None:
    with tenant_scope(user.id):
        result = forget(key, category=category)
    if result.startswith("Not found"):
        raise HTTPException(status_code=404, detail=result)
    return None


@app.post("/memory/search", response_model=list[MemorySearchResult])
async def search_memory(
    payload: MemorySearchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MemorySearchResult]:
    await limiter.consume(user.id, "memory_search", 30, 60)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before searching memory")
    with tenant_scope(user.id):
        memory = load_memory()
    results = await asyncio.to_thread(semantic_search_memory, memory, payload.query, api_key, payload.top_k)
    return [MemorySearchResult(**result) for result in results]


# --- AI Task Planner / Task Automation --------------------------------------

@app.post("/planner/plan", response_model=TaskOut, status_code=201)
async def create_plan_endpoint(
    payload: PlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskOut:
    await limiter.consume(user.id, "planner", 15, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before planning a task")
    if payload.scheduled_at and payload.auto_run:
        raise HTTPException(status_code=422, detail="Use either scheduled_at or auto_run, not both")

    from agent.planner import create_plan
    from agent.task_runner import flag_steps_needing_approval, run_task_steps, summarize_task_status

    with tenant_scope(user.id):
        try:
            plan = await asyncio.to_thread(create_plan, payload.goal, payload.context)
        except Exception:
            logger.exception("Planner failed for user %s", user.id)
            raise HTTPException(status_code=502, detail="Could not generate a plan")

        task_id = uuid.uuid4().hex
        steps = flag_steps_needing_approval(plan.get("steps", []))

        if payload.scheduled_at:
            record = add_task_record(user.id, {
                "task_id": task_id, "goal": payload.goal, "status": "scheduled",
                "steps": json.dumps(steps),
                "scheduled_at": payload.scheduled_at, "recurrence": payload.recurrence,
            })
            return TaskOut(**record)

        record = add_task_record(user.id, {
            "task_id": task_id, "goal": payload.goal, "status": "planned",
            "steps": json.dumps(steps),
        })

        if payload.auto_run:
            # Autonomous mode: plan and immediately execute every hosted-safe,
            # non-approval-gated step in one call.
            results = await run_task_steps(steps)
            run_status = summarize_task_status(results)
            summary = "\n".join(f"Step {r['step']} [{r['status']}]: {r['output'][:200]}" for r in results)
            record = update_task_record(
                user.id, task_id, status=run_status, steps=json.dumps(results), result=summary,
            )
    return TaskOut(**record)


@app.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    user: User = Depends(get_current_user),
    limit: int = 20,
    status_filter: str | None = None,
) -> list[TaskOut]:
    records = task_history(user.id, limit=limit, status=status_filter)
    return [TaskOut(**record) for record in records]


@app.get("/tasks/queue-summary")
def get_task_queue_summary(user: User = Depends(get_current_user)) -> dict:
    records = task_history(user.id, limit=200)
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    return {"total": len(records), "by_status": counts}


@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, user: User = Depends(get_current_user)) -> TaskOut:
    record = get_task_record(user.id, task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(**record)


@app.post("/tasks/{task_id}/approve-step/{step_number}", response_model=TaskOut)
def approve_task_step(
    task_id: str, step_number: int, user: User = Depends(get_current_user),
) -> TaskOut:
    record = get_task_record(user.id, task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    steps = record["steps"]
    matched = False
    for step in steps:
        if step.get("step") == step_number:
            step["approved"] = True
            matched = True
    if not matched:
        raise HTTPException(status_code=404, detail=f"No step {step_number} on this task")
    updated = update_task_record(user.id, task_id, steps=json.dumps(steps))
    return TaskOut(**updated)


@app.post("/tasks/{task_id}/run", response_model=TaskOut)
async def run_task(task_id: str, user: User = Depends(get_current_user)) -> TaskOut:
    await limiter.consume(user.id, "task_run", 15, 300)
    record = get_task_record(user.id, task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Task not found")
    if record["status"] not in {"planned", "partial", "failed", "awaiting_approval", "scheduled"}:
        raise HTTPException(status_code=409, detail=f"Task is already {record['status']}")

    from agent.task_runner import run_task_steps, summarize_task_status

    with tenant_scope(user.id):
        results = await run_task_steps(record["steps"])
        status = summarize_task_status(results)
        summary = "\n".join(f"Step {r['step']} [{r['status']}]: {r['output'][:200]}" for r in results)
        updated = update_task_record(
            user.id, task_id,
            status=status, steps=json.dumps(results), result=summary,
        )
    return TaskOut(**updated)


# --- Context Awareness -------------------------------------------------------

@app.get("/context", response_model=ContextOut)
def get_context(user: User = Depends(get_current_user)) -> ContextOut:
    """What JARVIS currently knows about this conversation, for the hosted
    API. Deep OS-level context (active window, screen contents) is only
    available from the desktop app via the `screen_process` tool — a
    headless server has no screen to look at, so this deliberately doesn't
    pretend otherwise."""
    with tenant_scope(user.id):
        memory = load_memory()
    recent = recent_chat_messages(user.id, limit=6)
    recent_topics = [message.content[:80] for message in recent if message.role == "user"]
    active_agent_hint = route_message(recent_topics[-1]) if recent_topics else None
    return ContextOut(
        server_time=datetime.now(timezone.utc),
        active_agent_hint=active_agent_hint,
        recent_topics=recent_topics,
        memory_categories={category: len(items) for category, items in memory.items() if isinstance(items, dict)},
        desktop_features_available=False,
    )


# --- Research: multi-source comparison & reports, text summarization ------

@app.post("/research/compare", response_model=str)
async def research_compare(
    payload: ResearchCompareRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    await limiter.consume(user.id, "research", 10, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before researching")

    from agent.tool_runtime import run_compare

    with tenant_scope(user.id):
        try:
            return await run_compare(payload.items, payload.aspect)
        except Exception:
            logger.exception("Research compare failed for user %s", user.id)
            raise HTTPException(status_code=502, detail="Could not complete the comparison")


@app.post("/research/report", response_model=ResearchReportOut)
async def research_report(
    payload: ResearchReportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchReportOut:
    await limiter.consume(user.id, "research", 10, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before researching")

    from agent.research import run_research_report

    with tenant_scope(user.id):
        try:
            result = await run_research_report(payload.topic, payload.angles, api_key)
        except Exception:
            logger.exception("Research report failed for user %s", user.id)
            raise HTTPException(status_code=502, detail="Could not generate the report")
    log_usage_event(user.id, "/research/report", input_chars=len(payload.topic), output_chars=len(result["report"]))
    return ResearchReportOut(**result)


@app.post("/research/summarize-text", response_model=TextSummaryOut)
async def research_summarize_text(
    payload: TextSummaryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TextSummaryOut:
    await limiter.consume(user.id, "research", 20, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before summarizing")

    from agent.research import summarize_text

    try:
        result = await summarize_text(payload.text, payload.context, api_key)
    except Exception:
        logger.exception("Text summarization failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not summarize that text")
    return TextSummaryOut(**result)


# --- To-Do Manager -----------------------------------------------------------

@app.get("/todos", response_model=list[TodoOut])
def get_todos(user: User = Depends(get_current_user), done: bool | None = None) -> list[TodoOut]:
    return [TodoOut(**row.__dict__) for row in list_todos(user.id, done=done)]


@app.post("/todos", response_model=TodoOut, status_code=201)
def post_todo(payload: TodoCreate, user: User = Depends(get_current_user)) -> TodoOut:
    row = create_todo(user.id, payload.text, payload.due_at)
    return TodoOut(**row.__dict__)


@app.put("/todos/{todo_id}/done", response_model=TodoOut)
def put_todo_done(todo_id: str, done: bool = True, user: User = Depends(get_current_user)) -> TodoOut:
    row = set_todo_done(user.id, todo_id, done)
    if not row:
        raise HTTPException(status_code=404, detail="To-do not found")
    return TodoOut(**row.__dict__)


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo_endpoint(todo_id: str, user: User = Depends(get_current_user)) -> None:
    if not delete_todo(user.id, todo_id):
        raise HTTPException(status_code=404, detail="To-do not found")
    return None


# --- Calendar (local; not synced with Google Calendar) ----------------------

@app.get("/calendar/events", response_model=list[CalendarEventOut])
def get_calendar_events(
    user: User = Depends(get_current_user),
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[CalendarEventOut]:
    return [CalendarEventOut(**row.__dict__) for row in list_calendar_events(user.id, start, end)]


@app.post("/calendar/events", response_model=CalendarEventOut, status_code=201)
def post_calendar_event(payload: CalendarEventCreate, user: User = Depends(get_current_user)) -> CalendarEventOut:
    row = create_calendar_event(user.id, payload.title, payload.start_at, payload.end_at, payload.notes)
    return CalendarEventOut(**row.__dict__)


@app.delete("/calendar/events/{event_id}", status_code=204)
def delete_calendar_event_endpoint(event_id: str, user: User = Depends(get_current_user)) -> None:
    if not delete_calendar_event(user.id, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return None


# --- Notification Center -----------------------------------------------------

@app.get("/notifications", response_model=list[NotificationOut])
def get_notifications(user: User = Depends(get_current_user), unread_only: bool = False) -> list[NotificationOut]:
    return [NotificationOut(**row.__dict__) for row in list_notifications(user.id, unread_only)]


@app.post("/notifications/{notification_id}/read", status_code=204)
def read_notification(notification_id: str, user: User = Depends(get_current_user)) -> None:
    if not mark_notification_read(user.id, notification_id):
        raise HTTPException(status_code=404, detail="Notification not found or already read")
    return None


@app.delete("/notifications/{notification_id}", status_code=204)
def delete_notification_endpoint(notification_id: str, user: User = Depends(get_current_user)) -> None:
    if not delete_notification(user.id, notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return None


# --- Meeting Assistant --------------------------------------------------

@app.post("/meetings/summarize", response_model=MeetingNoteOut, status_code=201)
async def summarize_meeting_endpoint(
    payload: MeetingSummarizeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeetingNoteOut:
    await limiter.consume(user.id, "meeting", 10, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before summarizing a meeting")

    from agent.research import summarize_meeting

    try:
        result = await summarize_meeting(payload.transcript, api_key)
    except Exception:
        logger.exception("Meeting summarization failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not summarize that transcript")

    row = create_meeting_note(user.id, payload.title, result["summary"], result["action_items"])
    log_usage_event(user.id, "/meetings/summarize", input_chars=len(payload.transcript), output_chars=len(result["summary"]))
    if payload.create_todos:
        for item in result["action_items"]:
            create_todo(user.id, item)
    return MeetingNoteOut(id=row.id, title=row.title, summary=row.summary, action_items=result["action_items"], created_at=row.created_at)


@app.get("/meetings", response_model=list[MeetingNoteOut])
def get_meetings(user: User = Depends(get_current_user)) -> list[MeetingNoteOut]:
    return [
        MeetingNoteOut(id=row.id, title=row.title, summary=row.summary, action_items=json.loads(row.action_items or "[]"), created_at=row.created_at)
        for row in list_meeting_notes(user.id)
    ]


# --- Document Generator (Word export) ---------------------------------------

@app.post("/documents/generate")
async def generate_document(
    payload: DocumentGenerateRequest,
    user: User = Depends(get_current_user),
) -> Response:
    await limiter.consume(user.id, "documents", 10, 300)
    from agent.document_generator import generate_docx, generate_pdf

    filename = "".join(c for c in payload.title if c.isalnum() or c in " -_").strip() or "document"
    if payload.format == "pdf":
        content = await asyncio.to_thread(generate_pdf, payload.title, payload.content)
        return Response(
            content=content, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    content = await asyncio.to_thread(generate_docx, payload.title, payload.content)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
    )


# --- Daily Personal Assistant -------------------------------------------

@app.get("/daily-briefing", response_model=DailyBriefingOut)
def get_daily_briefing(user: User = Depends(get_current_user)) -> DailyBriefingOut:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    from .repositories import as_aware_utc

    todos_today = [
        TodoOut(**row.__dict__) for row in list_todos(user.id, done=False)
        if row.due_at is not None and day_start <= as_aware_utc(row.due_at) < day_end
    ]
    events_today = [CalendarEventOut(**row.__dict__) for row in list_calendar_events(user.id, day_start, day_end)]
    unread = len(list_notifications(user.id, unread_only=True))
    scheduled_today = sum(
        1 for record in task_history(user.id, limit=200)
        if record["scheduled_at"] and day_start <= as_aware_utc(record["scheduled_at"]) < day_end
    )

    parts = [f"Good {'morning' if now.hour < 12 else 'afternoon' if now.hour < 18 else 'evening'}."]
    if events_today:
        parts.append(f"You have {len(events_today)} event(s) today.")
    if todos_today:
        parts.append(f"{len(todos_today)} to-do(s) are due today.")
    if unread:
        parts.append(f"{unread} unread notification(s).")
    if len(parts) == 1:
        parts.append("Nothing due today — a clear day.")

    return DailyBriefingOut(
        date=day_start.date().isoformat(),
        todos_due_today=todos_today,
        events_today=events_today,
        unread_notifications=unread,
        scheduled_tasks_today=scheduled_today,
        greeting=" ".join(parts),
    )


# --- Developer Features -----------------------------------------------------

@app.post("/dev/debug", response_model=DebugResult)
async def dev_debug(
    payload: DebugRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> DebugResult:
    await limiter.consume(user.id, "dev", 15, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key first")
    from agent.dev_assistant import debug_code

    try:
        result = await debug_code(payload.code, payload.error, payload.language, api_key)
    except Exception:
        logger.exception("Debug assistant failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not debug that code")
    log_usage_event(user.id, "/dev/debug", input_chars=len(payload.code), output_chars=len(result["fix"]))
    return DebugResult(**result)


@app.post("/dev/generate-tests", response_model=GenerateTestsResult)
async def dev_generate_tests(
    payload: GenerateTestsRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> GenerateTestsResult:
    await limiter.consume(user.id, "dev", 15, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key first")
    from agent.dev_assistant import generate_tests

    try:
        result = await generate_tests(payload.code, payload.language, api_key)
    except Exception:
        logger.exception("Test generation failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not generate tests")
    return GenerateTestsResult(**result)


@app.post("/dev/review", response_model=ReviewResult)
async def dev_review(
    payload: ReviewRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> ReviewResult:
    await limiter.consume(user.id, "dev", 15, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key first")
    from agent.dev_assistant import review_project

    try:
        result = await review_project(payload.description, api_key)
    except Exception:
        logger.exception("Project review failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not review that")
    return ReviewResult(**result)


@app.post("/dev/suggest-command", response_model=CommandSuggestResult)
async def dev_suggest_command(
    payload: CommandSuggestRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> CommandSuggestResult:
    await limiter.consume(user.id, "dev", 20, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key first")
    from agent.dev_assistant import suggest_command

    try:
        result = await suggest_command(payload.task, payload.shell, api_key)
    except Exception:
        logger.exception("Command suggestion failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not suggest a command")
    return CommandSuggestResult(**result)


# --- Git/GitHub integration (uses the user's own personal access token) -----

@app.post("/me/github-token", status_code=200)
def save_github_token(payload: GitHubTokenRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    set_user_secret(db, user.id, "github_token", payload.token)
    return {"configured": True}


@app.delete("/me/github-token", status_code=204)
def remove_github_token(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    delete_user_secret(db, user.id, "github_token")


def _github_token_or_409(user: User, db: Session) -> str:
    token = get_user_secret(db, user.id, "github_token")
    if not token:
        raise HTTPException(status_code=409, detail="Add a GitHub personal access token first (see /me/github-token)")
    return token


@app.get("/dev/github/repos", response_model=list[GitHubRepoOut])
async def github_repos(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[GitHubRepoOut]:
    await limiter.consume(user.id, "github", 20, 300)
    token = _github_token_or_409(user, db)
    from agent.github_client import list_repos

    try:
        repos = await list_repos(token)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("GitHub repo listing failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not reach GitHub")
    return [GitHubRepoOut(**repo) for repo in repos]


@app.get("/dev/github/repos/{owner}/{repo}/issues", response_model=list[GitHubIssueOut])
async def github_issues(
    owner: str, repo: str, state: str = "open",
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[GitHubIssueOut]:
    await limiter.consume(user.id, "github", 20, 300)
    token = _github_token_or_409(user, db)
    from agent.github_client import list_issues

    try:
        issues = await list_issues(token, owner, repo, state)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("GitHub issue listing failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not reach GitHub")
    return [GitHubIssueOut(**issue) for issue in issues]


@app.post("/dev/github/repos/{owner}/{repo}/issues", response_model=GitHubIssueOut, status_code=201)
async def github_create_issue(
    owner: str, repo: str, payload: GitHubIssueCreate,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> GitHubIssueOut:
    await limiter.consume(user.id, "github", 10, 300)
    token = _github_token_or_409(user, db)
    from agent.github_client import create_issue

    try:
        issue = await create_issue(token, owner, repo, payload.title, payload.body)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("GitHub issue creation failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not reach GitHub")
    return GitHubIssueOut(number=issue["number"], title=issue["title"], state="open", url=issue["url"], is_pull_request=False)


# --- Data & AI: CSV analysis and natural-language SQL -----------------------

@app.post("/data/analyze", response_model=DataAnalyzeResult)
async def analyze_data(payload: DataAnalyzeRequest, user: User = Depends(get_current_user)) -> DataAnalyzeResult:
    await limiter.consume(user.id, "data", 20, 300)
    from agent.data_analyst import analyze_csv

    try:
        result = await asyncio.to_thread(analyze_csv, payload.csv_text)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse that as CSV: {exc}")
    return DataAnalyzeResult(**result)


@app.post("/data/query", response_model=DataQueryResult)
async def query_data_endpoint(
    payload: DataQueryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> DataQueryResult:
    await limiter.consume(user.id, "data", 15, 300)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before querying data")
    from agent.data_analyst import query_data

    try:
        result = await query_data(payload.csv_text, payload.question, api_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("Data query failed for user %s", user.id)
        raise HTTPException(status_code=502, detail="Could not answer that question about the data")
    log_usage_event(user.id, "/data/query", input_chars=len(payload.question), output_chars=len(str(result.get("rows", ""))))
    return DataQueryResult(**result)


# --- Two-Factor Authentication -----------------------------------------

@app.post("/auth/2fa/setup", response_model=TwoFactorSetupOut)
def setup_two_factor(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TwoFactorSetupOut:
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="2FA is already enabled")
    secret = generate_secret()
    set_user_secret(db, user.id, "totp_secret_pending", secret)
    return TwoFactorSetupOut(secret=secret, provisioning_uri=provisioning_uri(secret, user.email))


@app.post("/auth/2fa/enable", response_model=TwoFactorStatusOut)
def enable_two_factor(
    payload: TwoFactorEnableRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TwoFactorStatusOut:
    pending_secret = get_user_secret(db, user.id, "totp_secret_pending")
    if not pending_secret:
        raise HTTPException(status_code=409, detail="Call /auth/2fa/setup first")
    if not verify_code(pending_secret, payload.code):
        raise HTTPException(status_code=401, detail="Incorrect authenticator code")
    set_user_secret(db, user.id, "totp_secret", pending_secret)
    delete_user_secret(db, user.id, "totp_secret_pending")
    user.totp_enabled = True
    db.commit()
    log_audit_event(user.id, "2fa_enabled")
    return TwoFactorStatusOut(enabled=True)


@app.post("/auth/2fa/disable", response_model=TwoFactorStatusOut)
def disable_two_factor(
    payload: TwoFactorDisableRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> TwoFactorStatusOut:
    # Sensitive action confirmation: disabling 2FA requires re-entering the
    # account password, not just an active session, since a hijacked
    # session shouldn't be enough to turn off a security control.
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    delete_user_secret(db, user.id, "totp_secret")
    user.totp_enabled = False
    db.commit()
    log_audit_event(user.id, "2fa_disabled")
    return TwoFactorStatusOut(enabled=False)


# --- Security audit log & credential vault ----------------------------------

@app.get("/security/audit-log", response_model=list[AuditLogEntryOut])
def get_audit_log(user: User = Depends(get_current_user)) -> list[AuditLogEntryOut]:
    return [
        AuditLogEntryOut(event_type=row.event_type, detail=row.detail, ip_address=row.ip_address, created_at=row.created_at)
        for row in list_audit_log(user.id)
    ]


@app.get("/security/vault", response_model=list[VaultEntryOut])
def get_vault(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[VaultEntryOut]:
    entries = []
    for name, label in (("gemini_api_key", "Gemini API key"), ("github_token", "GitHub token")):
        value = get_user_secret(db, user.id, name)
        configured = bool(value)
        preview = f"{'•' * max(0, len(value) - 4)}{value[-4:]}" if configured and len(value) > 4 else ("configured" if configured else "")
        entries.append(VaultEntryOut(name=label, configured=configured, masked_preview=preview))
    return entries


# --- Dashboard: system health, AI usage, activity timeline, themes --------

@app.get("/system/health", response_model=SystemHealthOut)
def system_health(_: User = Depends(get_current_user)) -> SystemHealthOut:
    """Resource usage of the hosted API process itself. There is no
    concept of "the user's CPU/RAM" for a hosted, multi-tenant server —
    that's the desktop app's job (see actions/computer_settings.py) — this
    is real monitoring of the service everyone's requests run through."""
    import time as _time

    import psutil

    process = psutil.Process()
    return SystemHealthOut(
        cpu_percent=psutil.cpu_percent(interval=0.05),
        memory_percent=psutil.virtual_memory().percent,
        disk_percent=psutil.disk_usage("/").percent,
        uptime_seconds=_time.time() - process.create_time(),
        active_live_sessions=len(live_sessions._sessions),
    )


@app.get("/usage/summary", response_model=UsageSummaryOut)
def get_usage_summary(user: User = Depends(get_current_user), days: int = 30) -> UsageSummaryOut:
    return UsageSummaryOut(**usage_summary(user.id, days))


@app.get("/dashboard/activity", response_model=list[ActivityItemOut])
def get_activity_timeline(user: User = Depends(get_current_user), limit: int = 30) -> list[ActivityItemOut]:
    items: list[ActivityItemOut] = []
    for message in recent_chat_messages(user.id, limit=10):
        items.append(ActivityItemOut(kind="chat", title=f"{message.role} message", detail=message.content[:120], at=message.created_at))
    for task in task_history(user.id, limit=10):
        items.append(ActivityItemOut(kind="task", title=task["goal"][:120], detail=f"status: {task['status']}", at=datetime.strptime(task["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)))
    for notification in list_notifications(user.id, limit=10):
        items.append(ActivityItemOut(kind="notification", title=notification.title, detail=notification.body[:120], at=notification.created_at))
    for meeting in list_meeting_notes(user.id, limit=5):
        items.append(ActivityItemOut(kind="meeting", title=meeting.title, detail=meeting.summary[:120], at=meeting.created_at))
    items.sort(key=lambda item: item.at, reverse=True)
    return items[:limit]


@app.get("/preferences/theme", response_model=ThemePreferenceOut)
def get_theme(user: User = Depends(get_current_user)) -> ThemePreferenceOut:
    config = load_user_config(user.id, namespace="ui")
    return ThemePreferenceOut(theme=config.get("theme", "terminal"))


@app.put("/preferences/theme", response_model=ThemePreferenceOut)
def set_theme(payload: ThemePreferenceUpdate, user: User = Depends(get_current_user)) -> ThemePreferenceOut:
    save_user_config(user.id, {"theme": payload.theme}, namespace="ui")
    return ThemePreferenceOut(theme=payload.theme)


# --- Voice personalities & language preference -----------------------------

@app.get("/voice/settings", response_model=VoiceSettingsOut)
def get_voice_settings(user: User = Depends(get_current_user)) -> VoiceSettingsOut:
    from actions.tts_engine import DEFAULT_VOICE_ID, PROVIDER_VOICES

    config = load_user_config(user.id, namespace="voice")
    available = [VoiceOption(id=voice_id, name=name) for name, voice_id in PROVIDER_VOICES["gemini"]]
    return VoiceSettingsOut(
        voice_id=config.get("voice_id", DEFAULT_VOICE_ID),
        language=config.get("language"),
        available_voices=available,
    )


@app.put("/voice/settings", response_model=VoiceSettingsOut)
def update_voice_settings(
    payload: VoiceSettingsUpdate,
    user: User = Depends(get_current_user),
) -> VoiceSettingsOut:
    from actions.tts_engine import PROVIDER_VOICES

    valid_ids = {voice_id for _, voice_id in PROVIDER_VOICES["gemini"]}
    updates: dict = {}
    if payload.voice_id is not None:
        if payload.voice_id not in valid_ids:
            raise HTTPException(status_code=422, detail=f"Unknown voice id: {payload.voice_id!r}")
        updates["voice_id"] = payload.voice_id
    if payload.language is not None:
        updates["language"] = payload.language.strip() or None
    if updates:
        save_user_config(user.id, updates, namespace="voice")
    return get_voice_settings(user=user)


# --- Workflow Recording (management; recording/replay happen on desktop) ---

@app.get("/workflows", response_model=list[WorkflowOut])
def get_workflows(user: User = Depends(get_current_user)) -> list[WorkflowOut]:
    return [
        WorkflowOut(id=row.id, name=row.name, steps=json.loads(row.steps or "[]"), created_at=row.created_at)
        for row in list_workflows(user.id)
    ]


@app.delete("/workflows/{workflow_id}", status_code=204)
def delete_workflow_endpoint(workflow_id: str, user: User = Depends(get_current_user)) -> None:
    if not delete_workflow(user.id, workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return None


@app.websocket("/ws")
async def live_socket(websocket: WebSocket) -> None:
    from main import JarvisLive

    with SessionLocal() as db:
        try:
            user, session_id = websocket_user(websocket, db)
            await limiter.consume(user.id, "websocket", 12, 60)
            api_key = get_user_secret(db, user.id, "gemini_api_key")
        except HTTPException as exc:
            await websocket.close(code=4401, reason=str(exc.detail))
            return

    await websocket.accept()
    if not api_key:
        await websocket.send_json({
            "type": "error",
            "code": "gemini_key_required",
            "message": "Add a Gemini API key before starting JARVIS.",
        })
        await websocket.close(code=4403)
        return

    client = WebSocketClient(websocket, user.id)
    engine = JarvisLive(
        client,
        cloud_safe=True,
        api_key=api_key,
        external_audio=True,
    )
    sender_task = asyncio.create_task(client.send_events())
    with tenant_scope(user.id):
        engine_task = asyncio.create_task(engine.run())
    await live_sessions.replace(user.id, engine, client, engine_task)
    client._emit({
        "type": "ready",
        "state": "CONNECTING",
        "audio": {"input_rate": 16000, "output_rate": 24000, "encoding": "pcm_s16le"},
    })

    connection_started = time.monotonic()
    idle_cycles = 0
    try:
        while True:
            remaining = WS_MAX_CONNECTION_SECONDS - (time.monotonic() - connection_started)
            if remaining <= 0:
                await websocket.close(code=4000, reason="Session refresh required")
                break

            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=min(WS_IDLE_TIMEOUT_SECONDS, remaining)
                )
            except asyncio.TimeoutError:
                idle_cycles += 1
                if idle_cycles >= WS_MAX_IDLE_CYCLES:
                    await websocket.close(code=4000, reason="Idle timeout")
                    break
                # Re-check the session hasn't been revoked mid-connection
                # (e.g. the user logged out or revoked this device from
                # another tab) instead of only validating once at connect
                # time, then nudge the client with a heartbeat.
                with SessionLocal() as heartbeat_db:
                    if not is_session_active(heartbeat_db, session_id, user.id):
                        await websocket.close(code=4401, reason="Session has ended")
                        break
                client._emit({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
                continue

            idle_cycles = 0
            if message.get("bytes") is not None:
                await engine.send_audio_chunk(message["bytes"])
                continue
            raw = message.get("text")
            if raw is None:
                continue

            import json

            try:
                event = json.loads(raw)
            except (ValueError, TypeError):
                client._emit({"type": "error", "code": "invalid_json", "message": "Message was not valid JSON."})
                continue

            event_type = event.get("type") if isinstance(event, dict) else None
            schema = WS_MESSAGE_SCHEMAS.get(event_type)
            if schema is None:
                client._emit({"type": "error", "code": "unknown_message_type", "message": f"Unsupported message type: {event_type!r}"})
                continue
            try:
                parsed = schema.model_validate(event)
            except ValidationError as exc:
                client._emit({"type": "error", "code": "invalid_message", "message": f"Malformed '{event_type}' message."})
                logger.debug("WS validation error for user %s: %s", user.id, exc)
                continue

            if isinstance(parsed, WSTextMessage):
                await limiter.consume(user.id, "live_text", 60, 60)
                with tenant_scope(user.id):
                    await engine.send_text(parsed.content)
            elif isinstance(parsed, WSAudioMessage):
                try:
                    data = base64.b64decode(parsed.data, validate=True)
                except (ValueError, TypeError):
                    client._emit({"type": "error", "code": "invalid_audio", "message": "Audio payload was not valid base64."})
                    continue
                await engine.send_audio_chunk(data, parsed.mime_type)
            elif isinstance(parsed, WSMuteMessage):
                client.muted = parsed.muted
                client.set_state("MUTED" if client.muted else "LISTENING")
            elif isinstance(parsed, WSPingMessage):
                client._emit({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            elif isinstance(parsed, WSCloseMessage):
                break
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("Live WebSocket session crashed for user %s", user.id)
        try:
            await websocket.send_json({"type": "error", "message": GENERIC_ERROR_DETAIL})
        except Exception:
            pass
    finally:
        engine.request_shutdown()
        engine_task.cancel()
        await asyncio.gather(engine_task, return_exceptions=True)
        await live_sessions.remove(user.id, engine_task)
        await client.close()
        try:
            await sender_task
        except (Exception, asyncio.CancelledError):
            pass
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass
