"""Markdown-rendering chat transcript via QWebEngineView.

Renders messages as HTML with a tiny embedded markdown converter (no deps).
JS callable from Python for incremental updates during streaming.

Safety:
- All untrusted text (Python args, LLM output) is HTML-escaped before any
  markdown transformation.
- Role labels are inserted via textContent.
- Python -> JS data crosses via JSON.stringify (json.dumps), so no string
  injection into JS source.
"""
from __future__ import annotations

import json

from aqt.qt import (  # type: ignore
    QDesktopServices, QUrl, QWebEnginePage, QWebEngineView,
)


_HTML = """\
<!doctype html>
<html><head><meta charset='utf-8'>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; font-size: 14px;
         margin: 0; padding: 12px; background: #1e1e1e; color: #e8e8e8;
         line-height: 1.5; }
  .msg { margin: 0 0 14px; padding: 10px 12px; border-radius: 10px; }
  .user { background: #2d4a6b; }
  .assistant { background: #2a2a2a; }
  .role { font-size: 11px; opacity: 0.6; text-transform: uppercase;
          margin-bottom: 4px; letter-spacing: 0.5px; }
  pre { background: #111; padding: 8px; border-radius: 6px; overflow-x: auto; }
  code { font-family: ui-monospace, monospace; font-size: 13px; }
  .err { background: #5a2222; color: #ffd; }
  a { color: #6cb6ff; }
  .thinking { display: inline-flex; gap: 4px; padding: 4px 0; }
  .thinking span { width: 6px; height: 6px; border-radius: 50%;
                   background: #888; animation: bounce 1.2s infinite ease-in-out; }
  .thinking span:nth-child(2) { animation-delay: 0.15s; }
  .thinking span:nth-child(3) { animation-delay: 0.3s; }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
    30% { transform: translateY(-4px); opacity: 1; }
  }
</style></head>
<body><div id='log'></div>
<script>
function escHTML(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
          .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function md(text) {
  // Escape FIRST, then apply a safe markdown subset on the escaped string.
  let html = escHTML(text);
  html = html.replace(/```([\\s\\S]*?)```/g, function(_, c) { return '<pre><code>' + c + '</code></pre>'; });
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  html = html.replace(/(?<!\\*)\\*([^*]+)\\*(?!\\*)/g, '<em>$1</em>');
  // Links: only allow http(s) URLs after escaping; href contents are already escaped.
  html = html.replace(/\\[([^\\]]+)\\]\\((https?:\\/\\/[^)\\s]+)\\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/\\n/g, '<br>');
  return html;
}
function buildMsg(role, msgId) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  if (msgId) div.id = msgId;
  const r = document.createElement('div');
  r.className = 'role';
  r.textContent = role;            // safe: textContent
  const b = document.createElement('div');
  b.className = 'body';
  div.appendChild(r);
  div.appendChild(b);
  document.getElementById('log').appendChild(div);
  return b;
}
function addMsg(role, text, msgId) {
  const body = buildMsg(role, msgId || null);
  body.dataset.raw = text;
  body.innerHTML = md(text);       // text is escaped inside md()
  scrollBottom();
}
function startAssistant(msgId) {
  const body = buildMsg('assistant', msgId);
  body.dataset.raw = '';
  // Show animated thinking dots until first chunk arrives.
  const dots = document.createElement('div');
  dots.className = 'thinking';
  dots.dataset.role = 'thinking';
  dots.appendChild(document.createElement('span'));
  dots.appendChild(document.createElement('span'));
  dots.appendChild(document.createElement('span'));
  body.appendChild(dots);
  scrollBottom();
}
function appendChunk(msgId, chunk) {
  const div = document.getElementById(msgId);
  if (!div) return;
  const body = div.querySelector('.body');
  // Strip the thinking indicator on first real content.
  const dots = body.querySelector('[data-role="thinking"]');
  if (dots) dots.remove();
  body.dataset.raw = (body.dataset.raw || '') + chunk;
  body.innerHTML = md(body.dataset.raw);
  scrollBottom();
}
function showError(text) {
  const body = buildMsg('err', null);
  body.parentElement.querySelector('.role').textContent = 'error';
  body.dataset.raw = text;
  body.innerHTML = md(text);
  scrollBottom();
}
function scrollBottom() { window.scrollTo(0, document.body.scrollHeight); }
</script>
</body></html>
"""


class _ChatPage(QWebEnginePage):
    """QWebEnginePage that opens external links in the system browser.

    Without this, http(s) link clicks would either navigate the chat view
    away from its HTML (replacing the UI) or, when target="_blank" is set,
    silently drop because the default createWindow() returns nullptr.
    """

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # type: ignore[override]
        # Allow the initial setHtml() data: load and any same-doc anchors.
        if url.scheme() in ("data", "about"):
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _wtype):  # type: ignore[override]
        # Route target="_blank" clicks through self.acceptNavigationRequest
        # so they end up opened externally instead of being dropped.
        return self


class ChatWebView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPage(_ChatPage(self))
        self.setHtml(_HTML, QUrl("about:blank"))

    def reset(self) -> None:
        """Clear all rendered messages without reloading the page (synchronous)."""
        self.page().runJavaScript("document.getElementById('log').innerHTML = '';")

    def add_message(self, role: str, text: str, msg_id: str | None = None) -> None:
        rid = json.dumps(msg_id) if msg_id else "null"
        js = f"addMsg({json.dumps(role)}, {json.dumps(text)}, {rid});"
        self.page().runJavaScript(js)

    def start_assistant(self, msg_id: str) -> None:
        self.page().runJavaScript(f"startAssistant({json.dumps(msg_id)});")

    def append_chunk(self, msg_id: str, chunk: str) -> None:
        js = f"appendChunk({json.dumps(msg_id)}, {json.dumps(chunk)});"
        self.page().runJavaScript(js)

    def show_error(self, text: str) -> None:
        self.page().runJavaScript(f"showError({json.dumps(text)});")
