"""QThread worker that streams OpenRouter responses into Qt signals."""
from __future__ import annotations

from aqt.qt import QObject, QThread, pyqtSignal  # type: ignore

from .client import ChatRequest, OpenRouterError, stream


class StreamWorker(QObject):
    chunk = pyqtSignal(str)
    finished = pyqtSignal(str)         # full text
    failed = pyqtSignal(str)           # error message

    def __init__(self, req: ChatRequest, api_key: str):
        super().__init__()
        self._req = req
        self._api_key = api_key

    def run(self) -> None:
        full = []
        try:
            for delta in stream(self._req, self._api_key):
                full.append(delta)
                self.chunk.emit(delta)
        except OpenRouterError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"unexpected: {e}")
            return
        self.finished.emit("".join(full))


def run_in_thread(parent: QObject, worker: StreamWorker) -> QThread:
    """Move worker onto a fresh QThread, start it, return the thread.

    Caller must keep both worker and thread alive (e.g., as attributes on a
    QDialog) until `thread.finished` fires, then both can be deleted.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.start()
    return thread
