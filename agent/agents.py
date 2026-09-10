"""The multi-agent registry: Research, Coding, Email, Computer, Data, and
Planning agents, plus an implicit "general" fallback.

Each agent is a persona (its own system prompt) associated with a subset of
the tools declared in `main.TOOL_DECLARATIONS`. Two things vary by
*runtime*, not by agent:

- Desktop JARVIS (`main.JarvisLive`, `cloud_safe=False`) can execute every
  tool a persona is associated with, including local machine control.
- The hosted REST/WS API (`cloud_safe=True`) can only ever execute tools
  that are safe to run on a shared, headless, multi-tenant server: no local
  filesystem writes, no subprocess execution, no browser automation. Today
  that's exactly `web_search` (see `agent/tool_runtime.py`). Everything else
  a hosted agent does is still real and useful — a specialized system
  prompt shapes a genuinely different response — but it does not yet call
  out to the underlying tool the way the desktop app does.

`hosted_tool_names` intentionally is NOT just "this agent's tools filtered
by main.CLOUD_SAFE_ACTIONS": several tools in that set (`flight_finder`,
`youtube_video`) actually shell out to local browser automation under the
hood and are not safe/functional on a headless server despite being
network-exposed to end users. Only tools verified side-effect-free for
server execution are listed here; the rest are surfaced to the UI as
"desktop app only" rather than silently pretending to work.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    description: str
    icon: str
    system_instruction: str
    # Tools this persona is conceptually responsible for (informational —
    # shown in the UI, used to decide the desktop app's tool subset).
    tool_names: tuple[str, ...] = field(default_factory=tuple)
    # Tools this persona can actually execute from the hosted REST/WS API
    # today (see module docstring). Empty means "prompt-only for now".
    hosted_tool_names: tuple[str, ...] = field(default_factory=tuple)
    # True if this agent's primary job requires the desktop app (local
    # machine access) and is not meaningfully usable from the hosted web
    # dashboard at all.
    desktop_only: bool = False


AGENTS: dict[str, AgentDefinition] = {
    "research": AgentDefinition(
        id="research",
        name="Research",
        description="Web search, multi-source research, and document/video summarization.",
        icon="search",
        system_instruction=(
            "You are the Research agent, a specialist module of JARVIS. Ground your "
            "answers in the search results you're given, cite what you can, note when "
            "sources disagree, and say plainly when something couldn't be verified. "
            "Be thorough but concise — lead with the answer, then the supporting detail."
        ),
        tool_names=("web_search", "deep_research", "youtube_video", "file_processor"),
        hosted_tool_names=("web_search",),
    ),
    "coding": AgentDefinition(
        id="coding",
        name="Coding",
        description="Writes, explains, and debugs code.",
        icon="code",
        system_instruction=(
            "You are the Coding agent, a specialist module of JARVIS. Write clean, "
            "correct, idiomatic code with brief explanations of non-obvious choices. "
            "When asked to debug, identify the root cause before proposing a fix. "
            "Prefer complete, runnable examples over fragments."
        ),
        tool_names=("code_helper", "dev_agent"),
        hosted_tool_names=(),
    ),
    "email": AgentDefinition(
        id="email",
        name="Email",
        description="Reads, drafts, and organizes Gmail (once connected).",
        icon="mail",
        system_instruction=(
            "You are the Email agent, a specialist module of JARVIS. Help draft, "
            "summarize, and organize email. Keep drafts professional and concise "
            "unless the user asks for a different tone. Never claim to have sent or "
            "read a real email unless a tool result confirms it."
        ),
        tool_names=("email_control",),
        hosted_tool_names=(),
    ),
    "computer": AgentDefinition(
        id="computer",
        name="Computer",
        description="Controls the local machine: apps, files, mouse/keyboard, screen.",
        icon="monitor",
        system_instruction=(
            "You are the Computer Control agent, a specialist module of JARVIS with "
            "direct access to the user's machine. Confirm the target application or "
            "file before taking a destructive action, and describe what you did in "
            "plain language afterward."
        ),
        tool_names=(
            "computer_control", "open_app", "file_controller", "media_control",
            "desktop_control", "computer_settings", "browser_control", "screen_process",
        ),
        hosted_tool_names=(),
        desktop_only=True,
    ),
    "data": AgentDefinition(
        id="data",
        name="Data",
        description="Analyzes uploaded files, spreadsheets, and data.",
        icon="bar-chart",
        system_instruction=(
            "You are the Data agent, a specialist module of JARVIS. Explain findings "
            "in plain language before diving into numbers, call out data quality "
            "issues (missing values, outliers, small sample sizes), and never invent "
            "figures that aren't in the data you were given."
        ),
        tool_names=("file_processor", "code_helper"),
        hosted_tool_names=(),
    ),
    "planning": AgentDefinition(
        id="planning",
        name="Planning",
        description="Breaks a complex goal into an ordered, executable step plan.",
        icon="list-checks",
        system_instruction=(
            "You are the Planning agent, a specialist module of JARVIS that turns a "
            "goal into an ordered list of concrete steps."
        ),
        tool_names=("agent_task", "task_status"),
        hosted_tool_names=(),
    ),
}

GENERAL_AGENT = AgentDefinition(
    id="general",
    name="General",
    description="JARVIS's default assistant persona for everything else.",
    icon="sparkles",
    system_instruction="",
)


def get_agent(agent_id: str | None) -> AgentDefinition:
    if not agent_id:
        return GENERAL_AGENT
    return AGENTS.get(agent_id, GENERAL_AGENT)


def list_agents() -> list[AgentDefinition]:
    return [GENERAL_AGENT, *AGENTS.values()]
