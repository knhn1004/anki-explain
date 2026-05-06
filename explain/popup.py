"""Explain chat popup dialog (non-modal, anchored right)."""
from __future__ import annotations

import uuid
from pathlib import Path

from aqt import mw  # type: ignore
from aqt.qt import (  # type: ignore
    QDialog, QHBoxLayout, QKeySequence, QLabel, QLineEdit, QPushButton,
    QShortcut, QSizePolicy, QVBoxLayout, Qt,
)
from aqt.utils import showWarning  # type: ignore

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
    # Fallback defaults if config missing
    return {
        "model": cfg.get("model", "openrouter/free"),
        "max_response_words": cfg.get("max_response_words", 80),
        "web_search": cfg.get("web_search", True),
        "web_search_max_results": cfg.get("web_search_max_results", 5),
        "popup_width": cfg.get("popup_width", 480),
        "popup_height": cfg.get("popup_height", 640),
    }


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

        self.setWindowTitle("Explain")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.resize(self._cfg["popup_width"], self._cfg["popup_height"])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._front_label = QLabel()
        self._front_label.setWordWrap(True)
        self._front_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self._front_label)

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

        # Defer initial load until webview's HTML is ready
        self._chat.loadFinished.connect(self._on_webview_ready)

    def _on_webview_ready(self, ok: bool) -> None:
        if not ok:
            return
        self._chat.loadFinished.disconnect(self._on_webview_ready)
        self._load_or_explain()

    def _deck_name(self) -> str:
        try:
            return mw.col.decks.name(self._card.did) or ""
        except Exception:
            return ""

    def _load_or_explain(self) -> None:
        front, back = card_text.front_back(self._card)
        deck = self._deck_name()
        preview = front[:120] + ("..." if len(front) > 120 else "")
        header = f"[{deck}] {preview}" if deck else f"Card: {preview}"
        self._front_label.setText(header)

        history = self._store.history(self._card.id)
        if history:
            for t in history:
                if t.role in ("user", "assistant"):
                    self._chat.add_message(t.role, t.content)
            # If last turn was user (prior attempt failed mid-stream), re-fire.
            if history[-1].role == "user":
                self._fire_completion()
            return

        first_msg = prompt.first_user_message(front, back, deck=deck)
        self._chat.add_message("user", first_msg)
        self._store.append(self._card.id, "user", first_msg)
        self._fire_completion()

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._chat.add_message("user", text)
        self._store.append(self._card.id, "user", text)
        self._fire_completion()

    def _fire_completion(self) -> None:
        try:
            api_key = get_api_key()
        except KeychainError as e:
            self._chat.show_error(f"Keychain error: {e}")
            return
        if not api_key:
            self._chat.show_error(
                "API key not set. Tools → anki-explain → Set API Key."
            )
            return

        # Build full message list: system + persisted history
        history = self._store.history(self._card.id)
        messages = [{"role": "system", "content": prompt.system_prompt(self._cfg["max_response_words"])}]
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
            self._store.append(self._card.id, "assistant", full)
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
