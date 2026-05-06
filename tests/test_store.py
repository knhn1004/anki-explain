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


def test_sessions_isolated(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    sid1 = s.new_session_id(7)
    s.append(7, "user", "first session q", session_id=sid1)
    s.append(7, "assistant", "first session a", session_id=sid1)
    sid2 = s.new_session_id(7)
    assert sid2 == sid1 + 1
    s.append(7, "user", "second session q", session_id=sid2)
    h1 = s.history(7, session_id=sid1)
    h2 = s.history(7, session_id=sid2)
    assert [t.content for t in h1] == ["first session q", "first session a"]
    assert [t.content for t in h2] == ["second session q"]
    s.close()


def test_default_history_returns_latest_session(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    s.append(1, "user", "old", session_id=s.new_session_id(1))
    new_sid = s.new_session_id(1)
    s.append(1, "user", "new", session_id=new_sid)
    latest = s.history(1)
    assert [t.content for t in latest] == ["new"]
    s.close()


def test_list_sessions(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    sid1 = s.new_session_id(3)
    s.append(3, "user", "alpha", session_id=sid1)
    sid2 = s.new_session_id(3)
    s.append(3, "user", "beta", session_id=sid2)
    sessions = s.list_sessions(3)
    assert [se.session_id for se in sessions] == [sid2, sid1]
    assert sessions[0].first_user_preview == "beta"
    s.close()


def test_clear_session_keeps_others(tmp_path):
    s = Store(tmp_path / "chat.sqlite")
    sid1 = s.new_session_id(9)
    s.append(9, "user", "keep", session_id=sid1)
    sid2 = s.new_session_id(9)
    s.append(9, "user", "delete", session_id=sid2)
    s.clear_session(9, sid2)
    assert [t.content for t in s.history(9, session_id=sid1)] == ["keep"]
    assert s.history(9, session_id=sid2) == []
    s.close()
