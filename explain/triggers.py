"""Wire the three triggers: toolbar button, shortcut, context menu, plus
a Tools-menu entry for Settings.
"""
from __future__ import annotations

from aqt import gui_hooks, mw  # type: ignore
from aqt.qt import QAction  # type: ignore

from .popup import open_for_current_card
from .settings import open_settings


def _config() -> dict:
    cfg = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    return cfg


def _on_state_shortcuts(state: str, shortcuts: list) -> None:
    if state == "review":
        seq = _config().get("shortcut", "Ctrl+Shift+E")
        shortcuts.append((seq, open_for_current_card))
        # Diagnostic: confirm the hook fired. Visible in Anki debug console.
        print(f"[anki-explain] registered shortcut '{seq}' for review state")


def _on_reviewer_will_show_context_menu(_reviewer, menu) -> None:
    action = QAction("Explain this card", menu)
    action.triggered.connect(open_for_current_card)
    menu.addAction(action)


def _on_webview_will_show_context_menu(webview, menu) -> None:
    # Fallback: Anki's reviewer uses a QWebEngineView, which has its own
    # context menu hook separate from reviewer_will_show_context_menu.
    try:
        from aqt.reviewer import ReviewerBottomBar  # type: ignore  # noqa: F401
    except Exception:
        pass
    if webview is getattr(mw, "web", None) or webview is getattr(mw.reviewer, "web", None):
        action = QAction("Explain this card", menu)
        action.triggered.connect(open_for_current_card)
        menu.addAction(action)


def _add_tools_menu_items() -> None:
    explain_action = QAction("anki-explain: Explain current card", mw)
    explain_action.triggered.connect(open_for_current_card)
    mw.form.menuTools.addAction(explain_action)

    settings_action = QAction("anki-explain: Set API Key...", mw)
    settings_action.triggered.connect(open_settings)
    mw.form.menuTools.addAction(settings_action)


def register_all() -> None:
    _add_tools_menu_items()
    gui_hooks.state_shortcuts_will_change.append(_on_state_shortcuts)
    gui_hooks.reviewer_will_show_context_menu.append(_on_reviewer_will_show_context_menu)
    gui_hooks.webview_will_show_context_menu.append(_on_webview_will_show_context_menu)
