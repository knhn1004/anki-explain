"""System prompt + first-user-message builder."""
from __future__ import annotations


def system_prompt(max_words: int = 80) -> str:
    return (
        "You explain Anki flashcards. Be SUCCINCT. "
        f"Hard cap: {max_words} words. No preamble, no padding. "
        "Plain language. When citing web sources, format as clickable markdown "
        "links: [short label](https://full-url). Put a Sources line at the end "
        "if any links used."
    )


def first_user_message(front: str, back: str, deck: str = "") -> str:
    deck_line = f"I am studying for this deck: {deck}.\n" if deck else ""
    return (
        f"{deck_line}"
        "I'm studying flashcards. Explain this card and search the web for "
        "relevant info. Keep it super succinct.\n\n"
        f"Front: {front}\n"
        f"Back: {back}"
    )
