# anki-explain — Design Doc

**Date:** 2026-05-04
**Status:** Draft, ready for implementation
**Author:** Oliver

## 1. Overview

`anki-explain` is a personal Anki addon that adds an **Explain** action to the reviewer. Triggering it opens a side chat popup that:

1. Auto-generates an explanation of the current flashcard using an LLM, grounded in real-time web results.
2. Lets the user follow up conversationally about the same card.
3. Persists chat history per card so reopening the same card resumes the prior conversation.

LLM access goes through OpenRouter, using a hardcoded free model with the `openrouter:web_search` server tool for live grounding. Cost target: ~$0 for tokens (free model), ~$0.02 per Explain when web search runs.

This is single-user, macOS-only.

## 2. Goals & non-goals

**Goals**
- One-click "Explain this card" during review.
- Conversational follow-up in same popup.
- Markdown rendering with citations from web search.
- Streaming response (token-by-token).
- Persistent per-card chat history.
- API key stored in macOS Keychain.

**Non-goals**
- Cross-platform support (macOS only for now).
- Editing or writing back into card fields.
- Multi-user / sync (Anki's AnkiWeb sync ignores addon data here).
- Model switching UI (hardcoded; can be unhardcoded later).
- Cost tracking dashboard.

## 3. User stories

- As a learner reviewing a card I don't fully understand, I press `Ctrl+E` and a popup explains the concept in <200 words with web-cited context.
- As a learner who wants more depth, I type "go deeper on X" in the same popup and get a follow-up reply that streams in.
- As a learner returning to the same card next session, I reopen the popup and see my prior conversation.

## 4. Architecture

### 4.1 Repo layout

```
anki-explain/
├── manifest.json              # Anki addon metadata
├── __init__.py                # entry: register hooks, menus, shortcuts
├── config.json                # default addon config
├── config.md                  # user-facing config docs
├── explain/
│   ├── __init__.py
│   ├── triggers.py            # toolbar btn, shortcut, context menu wiring
│   ├── popup.py               # QDialog chat window
│   ├── webview.py             # QWebEngineView for markdown render
│   ├── client.py              # OpenRouter HTTP client (streaming SSE)
│   ├── prompt.py              # system prompt + card→user-msg builder
│   ├── keychain.py            # macOS `security` CLI wrapper
│   ├── store.py               # SQLite chat history
│   └── card_text.py           # strip HTML from front/back
├── vendor/                    # bundled deps (markdown-it-py, etc.)
└── tests/                     # unit tests for pure modules
```

### 4.2 Runtime constraints

- **Anki:** 25.x, Qt6 (PyQt6 / aqt).
- **Python:** Anki-bundled (3.9+).
- **Threading:** Qt main thread for UI; `QThread` worker for network I/O. Communicate via `pyqtSignal`.
- **No async:** Anki's loop is sync Qt; use `requests` + manual SSE parsing (no `aiohttp`).
- **Storage:** single SQLite at `<addon-dir>/user_files/chat.sqlite`.
- **Secrets:** macOS Keychain via `security` CLI subprocess. Service `anki-explain`, account `openrouter`.

### 4.3 Module boundaries

| Module | Pure? | Imports |
|--------|-------|---------|
| `client.py` | yes | `requests`, stdlib |
| `prompt.py` | yes | stdlib |
| `card_text.py` | yes | stdlib (`html.parser`) |
| `store.py` | yes | `sqlite3` |
| `keychain.py` | yes | `subprocess` |
| `popup.py` / `webview.py` / `triggers.py` | no | `aqt`, `PyQt6` |

Pure modules unit-testable outside Anki.

## 5. UX flow

### 5.1 Triggers

Three entry points, all open the same popup for the current card:

1. **Toolbar button** in reviewer (`mw.reviewer`).
2. **Keyboard shortcut** `Ctrl+E` (configurable via Anki shortcut hook).
3. **Right-click context menu** item "Explain this card".

### 5.2 Popup behavior

- `QDialog`, non-modal, anchored right side of main window.
- Top: card front preview (collapsed).
- Middle: chat scroll area (`QWebEngineView` rendering markdown).
- Bottom: text input + Send button.
- On open:
  - Load prior history for `card.id` from SQLite.
  - If no history → auto-fire first Explain request with built-in prompt.
  - If history exists → render it, await user input.

### 5.3 Streaming render

- Worker thread reads SSE chunks from OpenRouter.
- Each chunk emitted via signal → popup appends to last assistant message → JS injection into webview to update DOM (`.innerHTML += chunk`, then re-render markdown).
- On stream end → save full assistant message to SQLite.

## 6. LLM integration

### 6.1 Endpoint

`POST https://openrouter.ai/api/v1/chat/completions` with `stream: true`.

### 6.2 Request shape

```json
{
  "model": "deepseek/deepseek-chat-v3-0324:free",
  "stream": true,
  "messages": [
    {"role": "system", "content": "<see prompt.py>"},
    {"role": "user", "content": "Front:\n...\n\nBack:\n..."},
    ...prior turns...
  ],
  "tools": [
    {"type": "openrouter:web_search"}
  ]
}
```

### 6.3 System prompt (initial)

```
You are helping a learner review an Anki flashcard. Explain the concept on
this card concisely (under 200 words unless they ask to expand). Use the
web_search tool when current facts, definitions, or context would help.
Cite sources inline as [1], [2] with a short reference list at the end.
Match the language of the card.
```

### 6.4 Card → first user message

`card_text.py` strips HTML, collapses whitespace, produces:

```
Front:
{stripped_front}

Back:
{stripped_back}
```

No tags, no deck name, no other fields (per Q3).

### 6.5 Headers

```
Authorization: Bearer <key from keychain>
HTTP-Referer: https://github.com/oliver/anki-explain
X-Title: anki-explain
Content-Type: application/json
```

## 7. Data model

### 7.1 SQLite schema

```sql
CREATE TABLE IF NOT EXISTS chats (
  card_id      INTEGER NOT NULL,
  turn_idx     INTEGER NOT NULL,
  role         TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
  content      TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  PRIMARY KEY (card_id, turn_idx)
);

CREATE INDEX IF NOT EXISTS idx_chats_card ON chats(card_id);
```

`card_id` matches Anki's `card.id`. `turn_idx` orders messages within a card.

### 7.2 Migrations

Versioned via `PRAGMA user_version`. v0 → v1 = create above table.

## 8. Configuration

`config.json` defaults:

```json
{
  "model": "deepseek/deepseek-chat-v3-0324:free",
  "max_response_words": 200,
  "shortcut": "Ctrl+E",
  "web_search": true,
  "web_search_max_results": 5
}
```

API key NOT in config — Keychain only. Settings dialog has "Set API Key" button → prompt → write to Keychain.

## 9. Error handling

| Failure | Behavior |
|--------|----------|
| No API key in Keychain | Popup shows banner "Set API key in Settings → anki-explain". |
| Network error | Inline error in chat, retry button. |
| 401 / bad key | Banner "Invalid API key". |
| 429 rate limit | Inline "Rate limited, wait N s" using `Retry-After` header. |
| Model returns empty | Show "(no response)" + retry button. |
| SSE chunk parse fail | Log to Anki console, abort that stream, show error. |
| SQLite write fail | Log + toast; chat continues but history won't persist. |

No silent failures. No retry storms.

## 10. Testing

- **Unit (pure modules):** `pytest` over `client.py` (with mocked `requests`), `prompt.py`, `card_text.py`, `store.py`, `keychain.py` (with mocked `subprocess`).
- **Manual:** install via `.ankiaddon` zip into local Anki, run through review flow.
- **No Anki integration tests** — too slow, low ROI for personal addon.

## 11. Packaging

- `make build` → zips repo into `anki-explain.ankiaddon`.
- Excludes `tests/`, `docs/`, `.git`, `__pycache__`.
- Drop into Anki via Tools → Add-ons → Install from File.

## 12. Open items / future

- Cross-platform Keychain (Linux Secret Service, Windows Credential Manager) via `keyring` lib if ever needed.
- Model picker UI when default underperforms.
- "Save explanation to card field" action.
- Cost meter pulled from OpenRouter `/credits` endpoint.

## 13. Implementation order

1. `card_text.py` + `prompt.py` + tests.
2. `keychain.py` + tests.
3. `client.py` (non-streaming first) + tests with recorded fixture.
4. `store.py` + tests.
5. `client.py` streaming.
6. Minimal `popup.py` (no streaming, no history) — get end-to-end with one trigger.
7. Add three triggers + shortcut.
8. Wire history load/save.
9. Wire streaming render.
10. Settings dialog for API key.
11. Polish: error banners, retry, cost display.
