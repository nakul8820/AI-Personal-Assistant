"""Cheap keyword parsers for yes/no and recurring-scope, EN + Hindi/Hinglish.

Kept in code (not the LLM) so the confirmation gate never depends on the model
remembering it — see Sprint 3 acceptance criteria.
"""

_YES = {
    "yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
    "do it", "go ahead", "please", "haan", "haa", "ha", "ji", "ji haan", "theek",
    "theek hai", "kar do", "karo", "bilkul", "sahi",
}
_NO = {
    "no", "n", "nope", "nah", "cancel", "stop", "don't", "dont", "do not",
    "nahi", "na", "mat", "mat karo", "rehne do", "ruko", "cancel karo",
}

_SCOPE = {
    "occurrence": {"this", "only this", "just this", "this one", "this occurrence",
                   "sirf yeh", "ye wala", "yeh wala", "single"},
    "following": {"following", "this and following", "and after", "onwards",
                  "aage se", "iske baad", "future"},
    "all": {"all", "series", "entire", "every", "whole", "poori", "saare", "sab"},
}


def _norm(text: str) -> str:
    return " ".join(text.lower().strip().strip(".!?").split())


def _hit(t: str, words: set[str]) -> bool:
    tokens = set(t.split())
    singles = {w for w in words if " " not in w}
    phrases = {w for w in words if " " in w}
    return bool(tokens & singles) or any(p in t for p in phrases)


def is_affirmative(text: str) -> bool | None:
    """True=yes, False=no, None=unclear."""
    t = _norm(text)
    yes, no = _hit(t, _YES), _hit(t, _NO)
    if yes and not no:
        return True
    if no and not yes:
        return False
    return None  # unclear or contradictory ("yes no")


def parse_scope(text: str) -> str | None:
    """Return 'occurrence' | 'following' | 'all' | None."""
    t = _norm(text)
    # priority: "following"/"all" win over "occurrence" ("this and following"
    # contains the word "this").
    for scope in ("following", "all", "occurrence"):
        if any(w in t for w in _SCOPE[scope]):
            return scope
    return None


if __name__ == "__main__":
    assert is_affirmative("yes") is True
    assert is_affirmative("haan kar do") is True
    assert is_affirmative("no, cancel") is False
    assert is_affirmative("nahi") is False
    assert is_affirmative("maybe later") is None
    assert parse_scope("just this one") == "occurrence"
    assert parse_scope("the entire series") == "all"
    assert parse_scope("this and following") == "following"
    assert parse_scope("blah") is None
    print("intent ok")
