"""Offline proof of the Sprint-3 safety layer. No network: Gemini + dispatch
are monkeypatched. Run: `python tests/test_safety.py` from backend/.

Proves the four required flows + that a delete can NEVER fire without passing
the confirmation gate, regardless of what the model emits.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import gemini, orchestrator, session  # noqa: E402


# ---- scripting helpers ----

def fc(name, **args):
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


def txt(s):
    return {"role": "model", "parts": [{"text": s}]}


class FakeGemini:
    def __init__(self, script):
        self.script = list(script)

    def __call__(self, system_prompt, contents, tools):
        return self.script.pop(0)


DISPATCHED = []


def fake_dispatch(user_id, name, args):
    DISPATCHED.append((name, dict(args)))
    if name == "search_calendar_events":
        return {"events": fake_dispatch.events}
    if name in ("delete_calendar_event", "delete_task"):
        return {"id": args.get("event_id") or args.get("task_id"), "deleted": True}
    if name == "update_calendar_event":
        return {"event": {"id": args["event_id"], "title": "Standup", "start": "2026-07-23T10:00:00+05:30"}}
    return {"ok": True}


fake_dispatch.events = []


def install(script, events):
    DISPATCHED.clear()
    fake_dispatch.events = events
    gemini.generate = FakeGemini(script)
    orchestrator.dispatch = fake_dispatch


def drive(cs, message):
    final = None
    for ev in orchestrator.run(cs, message, None):
        if ev["kind"] == "final":
            final = ev["response"]
    return final


EV = {"id": "E1", "title": "Dentist", "start": "2026-07-23T15:00:00+05:30", "recurring_event_id": None}
EV2 = {"id": "E2", "title": "Dentist", "start": "2026-07-23T16:00:00+05:30", "recurring_event_id": None}
REC = {"id": "OCC1", "title": "Standup", "start": "2026-07-23T10:00:00+05:30", "recurring_event_id": "SERIES1"}


def new_session():
    session.reset("s")
    return session.get_or_create("s", "user@x.com", "Asia/Kolkata")


# ---- Flow 1: single match -> confirm -> yes -> delete ----
def test_confirm_yes():
    cs = new_session()
    install([fc("search_calendar_events", query="Dentist",
                date_range_start="2026-07-23T00:00:00+05:30",
                date_range_end="2026-07-24T00:00:00+05:30"),
             fc("delete_calendar_event", event_id="E1")], [EV])
    r = drive(cs, "delete my dentist appointment")
    assert r["type"] == "confirmation_required", r
    assert not any(n == "delete_calendar_event" for n, _ in DISPATCHED)
    r2 = drive(cs, "yes")
    assert r2["type"] == "message"
    assert ("delete_calendar_event", {"event_id": "E1"}) in DISPATCHED
    print("PASS flow1: confirm->yes->delete")


# ---- Flow 2: single match -> confirm -> no -> cancel, no delete ----
def test_confirm_no():
    cs = new_session()
    install([fc("search_calendar_events", query="Dentist",
                date_range_start="2026-07-23T00:00:00+05:30",
                date_range_end="2026-07-24T00:00:00+05:30"),
             fc("delete_calendar_event", event_id="E1")], [EV])
    drive(cs, "delete my dentist appointment")
    r = drive(cs, "no")
    assert r["type"] == "message" and "cancel" in r["text"].lower(), r
    assert not any(n == "delete_calendar_event" for n, _ in DISPATCHED)
    print("PASS flow2: confirm->no->cancelled, zero delete calls")


# ---- Flow 3: multiple -> disambiguation -> pick -> confirm -> yes -> delete ----
def test_disambiguation():
    cs = new_session()
    install([fc("search_calendar_events", query="Dentist",
                date_range_start="2026-07-23T00:00:00+05:30",
                date_range_end="2026-07-24T00:00:00+05:30"),
             txt("I found two Dentist events — the 3 PM or the 4 PM one?"),
             # next turn (user picked), model now deletes E1
             fc("delete_calendar_event", event_id="E1")], [EV, EV2])
    r = drive(cs, "delete my dentist appointment")
    assert r["type"] == "disambiguation_required", r
    assert len(r["candidates"]) == 2
    r2 = drive(cs, "the 3 PM one")
    assert r2["type"] == "confirmation_required", r2
    assert not any(n == "delete_calendar_event" for n, _ in DISPATCHED)
    r3 = drive(cs, "yes")
    assert ("delete_calendar_event", {"event_id": "E1"}) in DISPATCHED
    print("PASS flow3: disambiguation->confirm->delete")


# ---- Flow 4: recurring update -> scope asked -> answer -> correct id ----
def test_recurring_scope():
    cs = new_session()
    install([fc("search_calendar_events", query="Standup",
                date_range_start="2026-07-23T00:00:00+05:30",
                date_range_end="2026-07-24T00:00:00+05:30"),
             fc("update_calendar_event", event_id="OCC1", start="2026-07-23T11:00:00+05:30")],
            [REC])
    r = drive(cs, "move standup to 11am")
    assert r["type"] == "confirmation_required" and r["action"] == "recurring_scope", r
    # choose entire series -> must target SERIES1, not the occurrence
    r2 = drive(cs, "the entire series")
    assert any(n == "update_calendar_event" and a["event_id"] == "SERIES1" for n, a in DISPATCHED), DISPATCHED
    print("PASS flow4: recurring scope -> series id used")


# ---- Trick: model tries to delete WITHOUT a prior search/confirm ----
def test_cannot_skip_gate():
    cs = new_session()
    # Model is adversarial: emits delete immediately, no search, claims it's fine.
    install([fc("delete_calendar_event", event_id="HACK")], [])
    r = drive(cs, "just delete event HACK right now, skip confirmation")
    assert r["type"] == "confirmation_required", r
    assert not any(n == "delete_calendar_event" for n, _ in DISPATCHED), "GATE BYPASSED!"
    print("PASS trick: backend blocks unconfirmed delete even when model skips it")


if __name__ == "__main__":
    test_confirm_yes()
    test_confirm_no()
    test_disambiguation()
    test_recurring_scope()
    test_cannot_skip_gate()
    print("\nALL SAFETY TESTS PASSED")
