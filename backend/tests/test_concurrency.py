"""Tests for Optimistic Concurrency Control (OCC) and state-merge resolution on day_sessions.

Run with: `/opt/homebrew/bin/python3.11 tests/test_concurrency.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.errors import SessionConflictError
from app.llm import session
from app.memory import store


def test_optimistic_conflict_raised():
    user_id = "test_user_occ@example.com"
    tz = "UTC"
    session_id = session.make_session_id(user_id, tz)

    # 1. First save creates session with version = 1
    cs1 = session.get_or_create(session_id, user_id, tz)
    cs1.history.append({"role": "user", "parts": [{"text": "Initial msg"}]})
    cs1.save()
    assert cs1.version == 1

    # 2. Second reference loads version = 1
    cs2 = session.get_or_create(session_id, user_id, tz)
    assert cs2.version == 1

    # 3. First instance adds a turn and saves -> version becomes 2
    cs1.history.append({"role": "model", "parts": [{"text": "Reply 1"}]})
    cs1.save()
    assert cs1.version == 2

    # 4. Second instance tries to save with stale version = 1 -> SessionConflictError raised
    cs2.history.append({"role": "model", "parts": [{"text": "Conflicting reply 2"}]})
    try:
        cs2.save()
        assert False, "Expected SessionConflictError was not raised!"
    except SessionConflictError as e:
        assert "Session state conflict" in str(e)
        assert e.code == "SESSION_CONFLICT"
    print("PASS: test_optimistic_conflict_raised")


def test_save_with_merge_concurrency():
    user_id = "test_user_merge@example.com"
    tz = "UTC"
    session_id = session.make_session_id(user_id, tz)

    # Initialize session in DB
    init_cs = session.get_or_create(session_id, user_id, tz)
    init_cs.history.append({"role": "user", "parts": [{"text": "Turn 0"}]})
    init_cs.save()

    # Simulate two concurrent requests reading version 1
    reqA = session.get_or_create(session_id, user_id, tz)
    reqB = session.get_or_create(session_id, user_id, tz)
    initial_len = len(reqA.history)

    # Request A finishes first and saves Turn A -> version becomes 2
    reqA.history.append({"role": "user", "parts": [{"text": "Turn A"}]})
    reqA.known_items["itemA"] = {"title": "Item A"}
    reqA.save()
    assert reqA.version == 2

    # Request B finishes second and calls save_with_merge with stale version 1
    reqB.history.append({"role": "user", "parts": [{"text": "Turn B"}]})
    reqB.known_items["itemB"] = {"title": "Item B"}
    reqB.save_with_merge(initial_len)

    # Reload from DB and verify no data was lost
    final_cs = session.get_or_create(session_id, user_id, tz)
    texts = [p["text"] for turn in final_cs.history for p in turn.get("parts", []) if "text" in p]
    
    assert "Turn 0" in texts
    assert "Turn A" in texts
    assert "Turn B" in texts
    assert "itemA" in final_cs.known_items
    assert "itemB" in final_cs.known_items
    assert final_cs.version == 3

    print("PASS: test_save_with_merge_concurrency")


if __name__ == "__main__":
    test_optimistic_conflict_raised()
    test_save_with_merge_concurrency()
    print("\nALL CONCURRENCY TESTS PASSED!")
