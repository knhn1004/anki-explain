"""anki-explain addon entry point.

Loaded by Anki at startup. Wires triggers, menu items, and settings.
"""
from __future__ import annotations

try:
    from aqt import mw  # type: ignore
except ImportError:
    mw = None

if mw is not None:
    from .explain.triggers import register_all
    register_all()
