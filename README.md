# anki-explain

Anki addon. Adds an **Explain** action to the reviewer that opens a side chat
popup. The popup auto-explains the current card via OpenRouter (free model +
optional web search) and supports follow-up chat. Per-card chat history
persists in SQLite.

## Status

Alpha. macOS-only (uses macOS Keychain for the API key).

## Features

- One-click explain via Tools menu, `Ctrl+Shift+E` (Cmd+Shift+E on macOS),
  or right-click "Explain this card".
- Streaming responses, token-by-token render with a thinking-dots indicator.
- Markdown rendering with clickable web-source links (open in system browser).
- Per-card sessions: **New** starts a fresh explanation, **History** lists
  past sessions for the card, **Clear** deletes the current one.
- API key stored in macOS Keychain — never written to disk in plaintext.

## Setup (from source)

1. Get an OpenRouter API key: https://openrouter.ai/keys
2. Install:
   ```
   just install
   ```
   This drops the addon into `~/Library/Application Support/Anki2/addons21/anki_explain/`.
3. Restart Anki.
4. **Tools → anki-explain: Set API Key…** → paste your key.
5. Open a card in the reviewer → press `Cmd+Shift+E` (or right-click → "Explain this card").

## Install from `.ankiaddon`

```
just build
```

Produces `anki-explain.ankiaddon`. In Anki: **Tools → Add-ons → Install from File…** and pick the zip.

## Config

Edit via **Anki → Add-ons → anki-explain → Config**, or directly in `config.json`.
See `config.md` for fields.

Default model: `openrouter/free` (auto-router across free models). Default web
search: `openrouter:web_search` plugin (~$0.02 / explain via Exa). Toggle
`web_search: false` in config to remove the cost.

## Cost

- LLM tokens: free (free-tier models).
- Web search: ~$0.02 per Explain when enabled.

If you hit upstream `429` rate limits, add your own provider keys at
https://openrouter.ai/settings/integrations (BYOK) — OpenRouter then routes
through your account and rate limits relax dramatically.

## Publishing to AnkiWeb

This project is packaged to AnkiWeb's spec:

- Top-level files in the zip (no parent folder).
- No `__pycache__` directories (excluded by `just build`).
- `manifest.json` with `package`, `name`, `conflicts`, `mod`.

To publish:

1. `just build` to produce `anki-explain.ankiaddon`.
2. Sign in / register a developer account at https://ankiweb.net/account/login.
3. Upload at https://ankiweb.net/shared/addons/ and fill in description, tags,
   and supported Anki versions.

## Dev

```
python3.13 -m venv .venv
.venv/bin/pip install pytest
just test
```

Pure modules (`card_text`, `prompt`, `client`, `store`, `keychain`) are
unit-tested. Qt UI (`popup`, `webview`, `triggers`, `worker`, `settings`) is
verified by AST parse + manual install in Anki.

## Architecture

See `docs/plans/2026-05-04-anki-explain-design.md` for the original design doc.
Layout summary:

- `__init__.py` — addon entry point; calls `register_all()`.
- `explain/triggers.py` — Tools menu, state shortcut, context menu hooks.
- `explain/popup.py` — `ExplainPopup` QDialog with session toolbar.
- `explain/webview.py` — `ChatWebView` (markdown render, clickable links).
- `explain/client.py` — OpenRouter HTTP + SSE streaming (no Qt deps).
- `explain/worker.py` — `QThread` worker bridging streaming -> Qt signals.
- `explain/store.py` — SQLite chat history with per-card sessions.
- `explain/keychain.py` — macOS Keychain via `security` CLI.
- `explain/settings.py` — Set / clear API key dialog.
- `explain/prompt.py` — system prompt + first-user-message builder.
- `explain/card_text.py` — strip HTML from Anki card fields.

## License

MIT — see `LICENSE`.
