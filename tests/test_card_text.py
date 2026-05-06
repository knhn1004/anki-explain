from explain.card_text import strip


def test_strip_basic_html():
    assert strip("<p>hello <b>world</b></p>") == "hello world"


def test_strip_collapses_whitespace():
    assert strip("a   \t  b") == "a b"


def test_strip_drops_sound_tags():
    assert strip("<p>word [sound:foo.mp3] meaning</p>") == "word  meaning".replace("  ", " ")


def test_strip_drops_script_style():
    html = "<style>.x{color:red}</style><p>visible</p><script>alert(1)</script>"
    assert strip(html) == "visible"


def test_strip_preserves_block_breaks():
    assert "\n" in strip("<div>line1</div><div>line2</div>")


def test_strip_empty():
    assert strip("") == ""
    assert strip(None) == ""  # type: ignore[arg-type]
