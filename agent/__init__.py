"""JARVIS agent package with unified Hermes agent submodule bridge."""
import sys
from pathlib import Path

_HERMES_AGENT_DIR = str(Path(__file__).resolve().parent.parent / "hermes_core" / "agent")
if _HERMES_AGENT_DIR not in __path__:
    __path__.append(_HERMES_AGENT_DIR)
