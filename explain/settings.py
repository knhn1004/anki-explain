"""Settings dialog: Set / clear API key in macOS Keychain."""
from __future__ import annotations

from aqt.qt import (  # type: ignore
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)
from aqt.utils import showInfo, showWarning  # type: ignore

from .keychain import KeychainError, delete_api_key, get_api_key, set_api_key


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("anki-explain - Settings")
        self.resize(420, 180)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("OpenRouter API key (stored in macOS Keychain):"))

        self._field = QLineEdit()
        self._field.setEchoMode(QLineEdit.EchoMode.Password)
        try:
            existing = get_api_key()
        except KeychainError:
            existing = None
        if existing:
            self._field.setPlaceholderText("(already set; type to replace)")
        else:
            self._field.setPlaceholderText("sk-or-v1-...")
        layout.addWidget(self._field)

        row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        row.addWidget(save_btn)
        row.addWidget(clear_btn)
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _save(self) -> None:
        key = self._field.text().strip()
        if not key:
            showWarning("Enter a key first.")
            return
        try:
            set_api_key(key)
        except KeychainError as e:
            showWarning(f"Failed to save: {e}")
            return
        self._field.clear()
        showInfo("Saved to Keychain.")
        self.close()

    def _clear(self) -> None:
        try:
            delete_api_key()
        except KeychainError as e:
            showWarning(str(e))
            return
        showInfo("Cleared.")
        self.close()


def open_settings() -> None:
    from aqt import mw  # type: ignore
    dlg = SettingsDialog(parent=mw)
    dlg.show()
