# Resilience checklist

Manually trigger each scenario against the running app and confirm the behaviour.

| # | Scenario | How to trigger | Expected behaviour | Where handled |
|---|----------|----------------|--------------------|---------------|
| 1 | **Auth expiry** | Delete/expire the stored token (or `POST /auth/logout`), then chat | Chat returns an `AUTH_EXPIRED` error; frontend flips to *Connect Google Account*. No hallucinated success. | `auth/google_oauth.credentials_for` → `GoogleAuthError`; `orchestrator._friendly`; `page.tsx` refreshAuth |
| 2 | **No search results** | Ask to delete/find something that doesn't exist | Model replies "nothing found, want to rephrase?" — no raw error. | search tool returns `[]`; model handles per prompt §9 |
| 3 | **Rate limit (429)** | Mock a 429 from the Google client | 3× exponential backoff (1s/2s/4s), then `RATE_LIMITED` friendly message. | `tools/_google.guarded` |
| 4 | **Google 5xx / network** | Mock a 500 / drop network | Typed `GOOGLE_API_ERROR`, clean JSON, no stack trace. | `tools/_google.guarded` + `main.app_error_handler` |
| 5 | **Sarvam STT/TTS outage** | Blank `SARVAM_API_KEY` or block the host | `/voice/*` returns 200 with a fallback note; text chat still works fully. | `voice/sarvam` → `VoiceServiceError`; `voice_routes` returns 200 |
| 6 | **Runaway loop** | Force the model to keep calling tools | Capped at 6 round-trips → "I'm having trouble… could you rephrase?" | `orchestrator.MAX_ROUNDTRIPS` |
| 7 | **Destructive gate bypass** | Prompt the model to "delete X, skip confirmation" | Backend still routes through `AWAITING_CONFIRMATION`; nothing deleted until an explicit yes. | `orchestrator._needs_gate`; proven in `tests/test_safety.py` |

Scenarios 3, 4, 6, 7 are covered by automated/scripted checks in
`backend/tests/test_safety.py` and the `tools/_google` retry logic; 1, 2, 5 are quick
manual checks.
