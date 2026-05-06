"""Explain chat popup dialog (non-modal, anchored right)."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from aqt import mw  # type: ignore
from aqt.qt import (  # type: ignore
    QAction, QDialog, QHBoxLayout, QKeySequence, QLabel, QLineEdit, QMenu,
    QPushButton, QShortcut, QSizePolicy, QToolButton, QVBoxLayout, Qt,
)
from aqt.utils import askUser, showWarning  # type: ignore

from . import card_text, prompt
from .client import ChatRequest
from .keychain import KeychainError, get_api_key
from .store import Store
from .webview import ChatWebView
from .worker import StreamWorker, run_in_thread


def _addon_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _config() -> dict:
    cfg = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    return {
        "model": cfg.get("model", "openrouter/free"),
        "max_response_words": cfg.get("max_response_words", 80),
        "web_search": cfg.get("web_search", True),
        "web_search_max_results": cfg.get("web_search_max_results", 5),
        "popup_width": cfg.get("popup_width", 480),
        "popup_height": cfg.get("popup_height", 640),
    }


def _fmt_ts(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


class ExplainPopup(QDialog):
    def __init__(self, card, parent=None):
        super().__init__(parent)
        self._card = card
        self._cfg = _config()
        self._store = Store(_addon_dir() / "user_files" / "chat.sqlite")
        self._worker: StreamWorker | None = None
        self._thread = None
        self._current_assistant_id: str | None = None
        self._current_assistant_buf: list[str] = []
        # Active session: latest existing, or 1 if none yet.
        self._session_id: int = self._store.latest_session_id(card.id)

        self.setWindowTitle("Explain")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.resize(self._cfg["popup_width"], self._cfg["popup_height"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._front_label = QLabel()
        self._front_label.setWordWrap(True)
        self._front_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self._front_label)

        # Session toolbar: New | History | Clear
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self._new_btn = QPushButton("New")
        self._new_btn.setToolTip("Start a fresh explanation session for this card")
        self._new_btn.clicked.connect(self._on_new_session)

        self._history_btn = QToolButton()
        self._history_btn.setText("History")
        self._history_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._history_menu = QMenu(self._history_btn)
        self._history_btn.setMenu(self._history_menu)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setToolTip("Delete the current session")
        self._clear_btn.clicked.connect(self._on_clear_session)

        toolbar.addWidget(self._new_btn)
        toolbar.addWidget(self._history_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addStretch(1)
        self._session_label = QLabel()
        self._session_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self._session_label)
        layout.addLayout(toolbar)

        self._chat = ChatWebView(self)
        self._chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._chat, stretch=1)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask a follow-up...")
        self._input.returnPressed.connect(self._on_send)
        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._on_send)
        row.addWidget(self._input, stretch=1)
        row.addWidget(self._send_btn)
        layout.addLayout(row)

        QShortcut(QKeySequence("Esc"), self, activated=self.close)

        self._chat.loadFinished.connect(self._on_webview_ready)

    def _on_webview_ready(self, ok: bool) -> None:
        if not ok:
            return
        self._chat.loadFinished.disconnect(self._on_webview_ready)
        self._render_header()
        self._refresh_history_menu()
        self._render_session()

    def _deck_name(self) -> str:
        try:
            return mw.col.decks.name(self._card.did) or ""
        except Exception:
            return ""

    def _render_header(self) -> None:
        front, _back = card_text.front_back(self._card)
        deck = self._deck_name()
        preview = front[:120] + ("..." if len(front) > 120 else "")
        header = f"[{deck}] {preview}" if deck else f"Card: {preview}"
        self._front_label.setText(header)

    def _refresh_history_menu(self) -> None:
        self._history_menu.clear()
        sessions = self._store.list_sessions(self._card.id)
        if not sessions:
            no_act = QAction("(no past sessions)", self._history_menu)
            no_act.setEnabled(False)
            self._history_menu.addAction(no_act)
            self._session_label.setText("session 1 (new)")
            return

        for sess in sessions:
            preview = sess.first_user_preview or "(empty)"
            label = f"#{sess.session_id}  {_fmt_ts(sess.started_at)}  {preview[:60]}"
            action = QAction(label, self._history_menu)
            if sess.session_id == self._session_id:
                action.setText("● " + label)
            action.triggered.connect(
                lambda _checked=False, sid=sess.session_id: self._switch_to_session(sid)
            )
            self._history_menu.addAction(action)

        total = len(sessions)
        self._session_label.setText(f"session #{self._session_id} of {total}")

    def _render_session(self) -> None:
        """Load current session into the webview, or fire fresh explain if empty."""
        front, back = card_text.front_back(self._card)
        deck = self._deck_name()

        # Reset the webview by reloading its HTML.
        self._chat.reset()

        history = self._store.history(self._card.id, session_id=self._session_id)
        if history:
            for t in history:
                if t.role in ("user", "assistant"):
                    self._chat.add_message(t.role, t.content)
            if history[-1].role == "user":
                # Prior assistant call failed mid-stream — re-fire.
                self._fire_completion()
            return

        # Empty session: fire the auto-explain.
        first_msg = prompt.first_user_message(front, back, deck=deck)
        self._chat.add_message("user", first_msg)
        self._store.append(self._card.id, "user", first_msg, session_id=self._session_id)
        self._fire_completion()

    def _switch_to_session(self, session_id: int) -> None:
        if session_id == self._session_id:
            return
        self._session_id = session_id
        self._refresh_history_menu()
        self._render_session()

    def _on_new_session(self) -> None:
        self._session_id = self._store.new_session_id(self._card.id)
        self._refresh_history_menu()
        self._render_session()

    def _on_clear_session(self) -> None:
        if not askUser(
            f"Delete session #{self._session_id} for this card?",
            parent=self,
            defaultno=True,
        ):
            return
        self._store.clear_session(self._card.id, self._session_id)
        # Switch to latest remaining session, or start fresh.
        sessions = self._store.list_sessions(self._card.id)
        if sessions:
            self._session_id = sessions[0].session_id
        else:
            self._session_id = self._store.new_session_id(self._card.id)
        self._refresh_history_menu()
        self._render_session()

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._chat.add_message("user", text)
        self._store.append(self._card.id, "user", text, session_id=self._session_id)
        self._fire_completion()

    def _fire_completion(self) -> None:
        try:
            api_key = get_api_key()
        except KeychainError as e:
            self._chat.show_error(f"Keychain error: {e}")
            return
        if not api_key:
            self._chat.show_error(
                "API key not set. Tools -> anki-explain -> Set API Key."
            )
            return

        history = self._store.history(self._card.id, session_id=self._session_id)
        messages = [{
            "role": "system",
            "content": prompt.system_prompt(self._cfg["max_response_words"]),
        }]
        for t in history:
            if t.role in ("user", "assistant"):
                messages.append({"role": t.role, "content": t.content})

        req = ChatRequest(
            model=self._cfg["model"],
            messages=messages,
            web_search=self._cfg["web_search"],
            web_search_max_results=self._cfg["web_search_max_results"],
        )

        self._send_btn.setEnabled(False)
        self._input.setEnabled(False)

        self._current_assistant_id = f"a-{uuid.uuid4().hex}"
        self._current_assistant_buf = []
        self._chat.start_assistant(self._current_assistant_id)

        self._worker = StreamWorker(req, api_key)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._thread = run_in_thread(self, self._worker)

    def _on_chunk(self, chunk: str) -> None:
        if not self._current_assistant_id:
            return
        self._current_assistant_buf.append(chunk)
        self._chat.append_chunk(self._current_assistant_id, chunk)

    def _on_finished(self, _full: str) -> None:
        full = "".join(self._current_assistant_buf)
        if full:
            self._store.append(
                self._card.id, "assistant", full, session_id=self._session_id
            )
        self._refresh_history_menu()
        self._reset_input()

    def _on_failed(self, msg: str) -> None:
        self._chat.show_error(msg)
        self._reset_input()

    def _reset_input(self) -> None:
        self._send_btn.setEnabled(True)
        self._input.setEnabled(True)
        self._input.setFocus()
        self._current_assistant_id = None
        self._current_assistant_buf = []

    def closeEvent(self, event):
        try:
            self._store.close()
        except Exception:
            pass
        super().closeEvent(event)


_open_popup: ExplainPopup | None = None


def open_for_current_card() -> None:
    global _open_popup
    if mw.reviewer is None or mw.reviewer.card is None:
        showWarning("Open a card in the reviewer first.")
        return
    if _open_popup is not None:
        try:
            _open_popup.close()
        except Exception:
            pass
    _open_popup = ExplainPopup(mw.reviewer.card, parent=mw)
    _open_popup.show()
    _open_popup.raise_()
    _open_popup.activateWindow()
