# anki-explain config

- **model**: OpenRouter model slug. Default `deepseek/deepseek-chat-v3-0324:free`.
- **max_response_words**: Soft cap on assistant reply length (used in system prompt).
- **shortcut**: Reviewer keyboard shortcut to open Explain popup.
- **web_search**: Attach `openrouter:web_search` server tool. Costs ~$0.02 per search.
- **web_search_max_results**: Max results returned per search call.
- **popup_width / popup_height**: Initial popup size in px.

API key is **not** stored here. Use **Tools → anki-explain → Set API Key** (writes to macOS Keychain).
