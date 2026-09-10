from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, min_length=6, max_length=6)


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    gemini_configured: bool = False
    totp_enabled: bool = False


class SessionView(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class GeminiKeyRequest(BaseModel):
    api_key: str = Field(min_length=20, max_length=500)
    verify_key: bool = Field(default=True, alias="validate")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    # Explicit agent id ("research", "coding", "email", "computer", "data",
    # "planning", or "general"). Omit to auto-route based on the message.
    agent: str | None = Field(default=None, max_length=40)


class PlanStep(BaseModel):
    step: int
    tool: str
    description: str


class ChatResponse(BaseModel):
    response: str
    agent: str
    # Populated only when the Planning agent handled the request.
    plan: list[PlanStep] | None = None


class ChatHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    agent: str = "general"
    created_at: datetime


class AgentOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    desktop_only: bool
    hosted_capable: bool


class ChatHistoryPage(BaseModel):
    items: list[ChatHistoryItem]
    next_before: datetime | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str
    ip_address: str
    current: bool = False


# --- Strictly validated WebSocket message payloads ---------------------
# Every inbound `/ws` text frame is parsed into one of these before it
# reaches any application logic (see api/server.py), instead of accepting
# arbitrary/loosely-typed JSON.

class WSTextMessage(BaseModel):
    type: Literal["text"]
    content: str = Field(min_length=1, max_length=12000)


class WSAudioMessage(BaseModel):
    type: Literal["audio"]
    data: str = Field(min_length=1, max_length=400_000)
    mime_type: str = Field(default="audio/pcm;rate=16000", max_length=80)


class WSMuteMessage(BaseModel):
    type: Literal["mute"]
    muted: bool = True


class WSPingMessage(BaseModel):
    type: Literal["ping"]


class WSCloseMessage(BaseModel):
    type: Literal["close"]


# --- Memory Management ---------------------------------------------------

class MemoryEntryOut(BaseModel):
    category: str
    key: str
    value: str
    updated: str


class MemoryUpsertRequest(BaseModel):
    category: str = Field(max_length=64)
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2000)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class MemorySearchResult(BaseModel):
    category: str
    key: str
    value: str
    score: float


# --- AI Task Planner / Task Automation ------------------------------------

class PlanRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    context: str = Field(default="", max_length=4000)
    auto_run: bool = False
    scheduled_at: datetime | None = None
    recurrence: Literal["none", "daily", "weekly", "monthly"] = "none"


class TaskStepOut(BaseModel):
    step: int
    tool: str
    description: str
    status: str = "pending"
    output: str = ""
    requires_approval: bool = False
    approved: bool = True
    attempts: int = 0


class TaskOut(BaseModel):
    task_id: str
    goal: str
    status: str
    result: str
    error: str
    steps: list[TaskStepOut]
    scheduled_at: datetime | None = None
    recurrence: str = "none"
    timestamp: str


# --- Context Awareness -----------------------------------------------------

class ContextOut(BaseModel):
    server_time: datetime
    active_agent_hint: str | None
    recent_topics: list[str]
    memory_categories: dict[str, int]
    desktop_features_available: bool


# --- Voice & Language preferences -------------------------------------------

class VoiceOption(BaseModel):
    id: str
    name: str


class VoiceSettingsOut(BaseModel):
    voice_id: str
    language: str | None
    available_voices: list[VoiceOption]


class VoiceSettingsUpdate(BaseModel):
    voice_id: str | None = Field(default=None, max_length=40)
    language: str | None = Field(default=None, max_length=60)


# --- Workflow Recording ------------------------------------------------------

class WorkflowStepOut(BaseModel):
    tool: str
    parameters: dict = Field(default_factory=dict)


class WorkflowOut(BaseModel):
    id: str
    name: str
    steps: list[WorkflowStepOut]
    created_at: datetime


# --- Agent Permissions --------------------------------------------------

class AgentPermissionsOut(BaseModel):
    disabled_agents: list[str] = Field(default_factory=list)


class AgentPermissionsUpdate(BaseModel):
    disabled_agents: list[str] = Field(default_factory=list)


# --- Research (multi-source, comparison, reports) ---------------------------

class ResearchCompareRequest(BaseModel):
    items: list[str] = Field(min_length=2, max_length=6)
    aspect: str = Field(default="general", max_length=200)


class ResearchReportRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    angles: list[str] = Field(default_factory=list, max_length=5)


class ResearchReportOut(BaseModel):
    topic: str
    report: str
    sources_queried: list[str]


class TextSummaryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50000)
    context: str = Field(default="", max_length=200)


class TextSummaryOut(BaseModel):
    summary: str
    key_points: list[str]


# --- Todos --------------------------------------------------------------

class TodoOut(BaseModel):
    id: str
    text: str
    done: bool
    due_at: datetime | None
    created_at: datetime


class TodoCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None


# --- Calendar -----------------------------------------------------------

class CalendarEventOut(BaseModel):
    id: str
    title: str
    notes: str
    start_at: datetime
    end_at: datetime | None
    created_at: datetime


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    start_at: datetime
    end_at: datetime | None = None


# --- Notifications --------------------------------------------------------

class NotificationOut(BaseModel):
    id: str
    title: str
    body: str
    kind: str
    read_at: datetime | None
    created_at: datetime


# --- Meeting Assistant ------------------------------------------------------

class MeetingSummarizeRequest(BaseModel):
    title: str = Field(default="Untitled meeting", max_length=200)
    transcript: str = Field(min_length=1, max_length=80000)
    create_todos: bool = False


class MeetingNoteOut(BaseModel):
    id: str
    title: str
    summary: str
    action_items: list[str]
    created_at: datetime


# --- Document Generator -----------------------------------------------------

class DocumentGenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=100000)
    format: Literal["docx", "pdf"] = "docx"


# --- Daily Personal Assistant -------------------------------------------

class DailyBriefingOut(BaseModel):
    date: str
    todos_due_today: list[TodoOut]
    events_today: list[CalendarEventOut]
    unread_notifications: int
    scheduled_tasks_today: int
    greeting: str


# --- Developer Features -----------------------------------------------------

class DebugRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    error: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="python", max_length=40)


class DebugResult(BaseModel):
    explanation: str
    fix: str


class GenerateTestsRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20000)
    language: str = Field(default="python", max_length=40)


class GenerateTestsResult(BaseModel):
    tests: str
    framework: str


class ReviewRequest(BaseModel):
    description: str = Field(min_length=1, max_length=40000)


class ReviewResult(BaseModel):
    summary: str
    strengths: list[str]
    concerns: list[str]
    suggestions: list[str]


class CommandSuggestRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    shell: str = Field(default="bash", max_length=40)


class CommandSuggestResult(BaseModel):
    command: str
    explanation: str
    caution: str


class GitHubTokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=500)


class GitHubRepoOut(BaseModel):
    full_name: str
    description: str
    private: bool
    default_branch: str
    open_issues: int
    url: str


class GitHubIssueOut(BaseModel):
    number: int
    title: str
    state: str
    url: str
    is_pull_request: bool


class GitHubIssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    body: str = Field(default="", max_length=10000)


# --- Data & AI ------------------------------------------------------------

class DataAnalyzeRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)


class DataColumnOut(BaseModel):
    name: str
    dtype: str
    non_null: int
    null_count: int
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    std: float | None = None
    top_values: list[dict] | None = None


class DataChartOut(BaseModel):
    chart_type: str
    title: str
    labels: list[str]
    values: list[float]


class DataAnalyzeResult(BaseModel):
    row_count: int
    column_count: int
    columns: list[DataColumnOut]
    chart: DataChartOut | None = None


class DataQueryRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    question: str = Field(min_length=1, max_length=500)


class DataQueryResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list]


# --- Security: 2FA, audit log, vault ------------------------------------

class TwoFactorSetupOut(BaseModel):
    secret: str
    provisioning_uri: str


class TwoFactorEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TwoFactorDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class TwoFactorStatusOut(BaseModel):
    enabled: bool


class AuditLogEntryOut(BaseModel):
    event_type: str
    detail: str
    ip_address: str
    created_at: datetime


class VaultEntryOut(BaseModel):
    name: str
    configured: bool
    masked_preview: str


# --- Dashboard: system health, usage, activity timeline --------------------

class SystemHealthOut(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_seconds: float
    active_live_sessions: int


class UsageSummaryOut(BaseModel):
    total_calls: int
    by_endpoint: dict[str, dict]
    days: int


class ActivityItemOut(BaseModel):
    kind: str
    title: str
    detail: str
    at: datetime


class ThemePreferenceOut(BaseModel):
    theme: str


class ThemePreferenceUpdate(BaseModel):
    theme: Literal["terminal", "glass", "light"]
