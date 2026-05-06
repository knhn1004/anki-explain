from explain.prompt import first_user_message, system_prompt


def test_system_prompt_contains_word_cap():
    assert "150 words" in system_prompt(max_words=150)


def test_system_prompt_default():
    sp = system_prompt()
    assert "80 words" in sp
    assert "SUCCINCT" in sp


def test_first_user_message_no_deck():
    msg = first_user_message("Q", "A")
    assert "deck" not in msg.lower()
    assert "Front: Q" in msg
    assert "Back: A" in msg
    assert "succinct" in msg.lower()


def test_first_user_message_with_deck():
    msg = first_user_message("Q", "A", deck="Spanish::Verbs")
    assert "studying for this deck: Spanish::Verbs" in msg
    assert "Front: Q" in msg
    assert "Back: A" in msg
