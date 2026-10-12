"""Agent internals extracted from run_agent.py so it stays focused on AIAgent."""
from pathlib import Path

_JARVIS_AGENT_DIR = str(Path(__file__).resolve().parent.parent.parent / "agent")
if _JARVIS_AGENT_DIR not in __path__:
    __path__.append(_JARVIS_AGENT_DIR)

try:
    from . import jiter_preload as _jiter_preload  # noqa: F401
except ImportError:
    pass
