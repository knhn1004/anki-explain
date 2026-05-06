from explain.store import Store


def test_append_and_history(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    s.append(42, "user", "hi")
    s.append(42, "assistant", "hello")
    s.append(99, "user", "other card")
    turns = s.history(42)
    assert [(t.role, t.content) for t in turns] == [("user", "hi"), ("assistant", "hello")]
    assert len(s.history(99)) == 1
    s.close()


def test_append_many(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    s.append_many(7, [("user", "a"), ("assistant", "b"), ("user", "c")])
    turns = s.history(7)
    assert [t.content for t in turns] == ["a", "b", "c"]
    s.close()


def test_clear(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    s.append(1, "user", "x")
    s.clear(1)
    assert s.history(1) == []
    s.close()


def test_persists_across_instances(tmp_path):
    db = tmp_path / "chat.sqlite"
    s1 = Store(db)
    s1.append(5, "user", "persisted")
    s1.close()
    s2 = Store(db)
    assert [t.content for t in s2.history(5)] == ["persisted"]
    s2.close()


def test_role_check(tmp_path):
    import sqlite3
    s = Store(tmp_path / "chat.sqlite")
    try:
        s.append(1, "bogus", "x")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("expected IntegrityError on bad role")
    s.close()
