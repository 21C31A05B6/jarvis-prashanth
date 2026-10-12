"""Hermes Agent Core Engine integrated into JARVIS-OS."""
import sys
from pathlib import Path

_HERMES_DIR = Path(__file__).resolve().parent
if str(_HERMES_DIR) not in sys.path:
    sys.path.insert(0, str(_HERMES_DIR))
