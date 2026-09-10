"""Shared pytest configuration.

Sets a headless-safe Qt platform default before any test module has a
chance to import PyQt6, so GUI tests behave consistently regardless of
import order or which test file pytest happens to collect first (see the
individual test_ui_*.py / test_vision_preview.py / test_graphics_quality.py
/ test_research_progress_ui.py files, which each additionally guard their
own PyQt6 import and skip cleanly when it — or a working display — isn't
"""
import os

import core.qt_init  # noqa: F401 - Initialize Qt6 DLLs on Windows before importing PyQt6

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

