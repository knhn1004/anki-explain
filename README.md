# anki-explain

Personal Anki addon. Adds an **Explain** action to the reviewer that opens a side chat popup. The popup auto-explains the current card via OpenRouter (free model + web search) and supports follow-up chat. Per-card chat history persists in SQLite.

## Status

Early work-in-progress. macOS only. Single-user.

## Features

- One-click explain via toolbar / `Ctrl+E` / right-click context menu.
- Streaming responses (token-by-token render).
- Markdown rendering with web-cited references.
- Persistent per-card chat history.
- API key in macOS Keychain (no plaintext config).

## Setup

1. Get an OpenRouter API key: https://openrouter.ai/keys
2. Build & install:
   ```
   just install
   ```
3. Restart Anki.
4. Tools → **anki-explain: Set API Key…** → paste your key.
5. Open a card in the reviewer, press `Ctrl+E`.

## Config

Edit `config.json` (or via Anki's Add-ons → Config). See `config.md`.

Default model: `deepseek/deepseek-chat-v3-0324:free` with `openrouter:web_search` tool.

## Cost

- LLM tokens: free.
- Web search: ~$0.02 per Explain (5 results via Exa). Toggle off in config to make it $0.

## Dev

```
python3.13 -m venv .venv
.venv/bin/pip install pytest
just test
```

## Layout

See `docs/plans/2026-05-04-anki-explain-design.md`.
