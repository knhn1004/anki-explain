"""Strip HTML and normalize whitespace from Anki card fields."""
from __future__ import annotations

import re
from html.parser import HTMLParser


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in ("br", "p", "div", "li", "tr"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str):
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_NEWLINES = re.compile(r"\n{3,}")
_SOUND_TAG = re.compile(r"\[sound:[^\]]+\]")


def strip(html: str) -> str:
    """Strip HTML tags, normalize whitespace, drop Anki [sound:...] tags."""
    if not html:
        return ""
    p = _Stripper()
    p.feed(html)
    out = p.text()
    out = _SOUND_TAG.sub("", out)
    out = _WHITESPACE.sub(" ", out)
    out = _NEWLINES.sub("\n\n", out)
    return out.strip()


def front_back(card) -> tuple[str, str]:
    """Extract stripped front/back from an Anki card object.

    Anki's Card has `question()` and `answer()` returning rendered HTML.
    Answer includes the question + separator; we slice it out.
    """
    front_html = card.question()
    answer_html = card.answer()
    front = strip(front_html)
    full_answer = strip(answer_html)
    if full_answer.startswith(front):
        back = full_answer[len(front):].lstrip("\n -")
    else:
        back = full_answer
    return front, back
