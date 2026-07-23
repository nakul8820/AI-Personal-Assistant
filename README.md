# Executive AI Personal Assistant

A warm, bilingual (English / हिंदी / Hinglish) voice + text assistant that manages your
**Google Calendar, Google Tasks, and Google Contacts** through natural language.

- **Backend:** FastAPI · Gemini (function calling, raw REST) · Sarvam (STT/TTS) · Google APIs
- **Frontend:** Next.js (App Router) with streaming tool cards, tappable confirmation/disambiguation UI, and mic input
- **Safety:** a backend state machine enforces read-before-write, disambiguation, and destructive-action confirmation — independent of what the LLM outputs.

---

## Architecture

```
Browser (Next.js)
  │  text / mic
  ▼
/voice/transcribe ──► Sarvam STT ─┐
                                   ▼
                              /chat/stream (SSE)
                                   │
                          ┌────────┴─────────┐
                          │  Orchestrator    │   custom state machine
                          │  (state machine) │   AWAITING_INPUT / DISAMBIGUATION /
                          │  + safety gate   │   CONFIRMATION
                          └────────┬─────────┘
             system prompt ┌───────┴────────┐ tool calls
                 Gemini ◄──┤   loop (≤6)     ├──► Google Calendar / Tasks / Contacts
                           └────────────────┘
                                   │ reply text
                                   ▼
                          /voice/speak ──► Sarvam TTS ──► audio playback
```

The state machine is the single source of truth. Voice is a presentation layer: STT
produces a text message that flows through the exact same `/chat` pipeline, and the reply
is optionally spoken. A Sarvam outage degrades to text and never blocks a Calendar/Tasks
action.

---

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env      # fill in the keys below
docker compose up --build
# frontend → http://localhost:3000   backend → http://localhost:8000
```

## Quick start (local, no Docker)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # fill in keys
uvicorn app.main:app --reload

# frontend (new terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

---

## Environment / API keys

Fill `backend/.env` (see `backend/.env.example`):

| Var | Where to get it |
|-----|-----------------|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud Console → APIs & Services → Credentials → **OAuth client ID** (type *Web application*). Add redirect URI `http://localhost:8000/auth/callback`. Enable the **Calendar API, Tasks API, People API**. |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `SARVAM_API_KEY` | https://dashboard.sarvam.ai |
| `SESSION_SECRET` | any long random string |
| `TOKEN_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

OAuth requests **offline access** and the scopes `calendar`, `tasks`,
`contacts.readonly`. Tokens are Fernet-encrypted and stored in SQLite (`DB_PATH`), so they
survive restarts as long as `TOKEN_ENCRYPTION_KEY` is set.

---

## Rule → implementation map

Every system-prompt rule (`backend/app/llm/prompt.py`) has a concrete enforcer:

| System-prompt rule | Enforced in |
|---|---|
| 0. Bilingual (EN/HI/Hinglish) | `prompt.py` (instruction) + language hint injected in `orchestrator.run()`; STT language from `voice/sarvam.py` selects the TTS voice |
| 1. Temporal grounding | `llm/prompt.py::build_system_prompt()` injects UTC/local/timezone/day per request |
| 2. Two-phase mutation (read-before-write) | `orchestrator._needs_gate()` + conversation-scoped `session.known_items` — mutation IDs must come from a prior search |
| 3. Disambiguation | `orchestrator.run()` → `disambiguation_required`; frontend renders tappable candidate cards |
| 4. Destructive confirmation | **`orchestrator._needs_gate()` hard gate** — `delete_*` / `complete_task` can only run out of a confirmed `pending_action`. Proven in `tests/test_safety.py` |
| 5. Recurring events | `_needs_gate()` detects `recurring_event_id`; scope (occurrence/following/all) via `intent.parse_scope()` chooses occurrence vs series id |
| 6. Contact lookup / attendee auto-fill | `tools/contacts.py` + model-driven `search_contacts`; multi-match reuses the disambiguation flow |
| 7. Missing info | model-side (prompt §7) — creation tools require title/start in their declarations |
| 8. Task lists | `tools/tasks.py::_default_list_id()` defaults to the primary list |
| 9. Error recovery | typed exceptions in `core/errors.py`, translated in `tools/_google.py`; surfaced by `orchestrator._friendly()` |
| 10. Voice formatting | prompt §10 + concise code-generated confirmations |

The yes/no and scope parsing (`llm/intent.py`) lives in **code, not the LLM**, so the
confirmation gate never depends on the model remembering it.

---

## Tests

```bash
cd backend && source .venv/bin/activate
python app/llm/intent.py      # keyword parser self-check
python tests/test_safety.py   # 5 safety flows, fully offline (Gemini + Google mocked)
```

`test_safety.py` proves the four required Sprint-3 flows **and** that an adversarial model
telling the backend to "skip confirmation" still cannot delete anything.

---

## Resilience matrix

See [`docs/RESILIENCE.md`](docs/RESILIENCE.md) for the scenario checklist. Summary:

| Scenario | Behaviour |
|---|---|
| Auth expiry | `AUTH_EXPIRED` error → UI shows *Connect Google Account*; never claims success |
| No results | model says "nothing found, want to rephrase?" |
| Rate limit (429) | `tools/_google.py` retries 3× with exponential backoff, then a friendly retry message |
| Google 5xx / network | typed `GOOGLE_API_ERROR`, no crash |
| Sarvam outage | `/voice/*` returns 200 with a fallback note; text chat unaffected |
| Runaway loop | capped at 6 tool round-trips → graceful "could you rephrase?" |

---

## Deploy

**Frontend (Vercel):** import the repo, set **Root Directory = `frontend`**, add env var
`NEXT_PUBLIC_API_URL=https://<your-backend-host>`. Next.js is auto-detected.

**Backend (Render / Railway / Fly.io):** deploy `backend/` (Dockerfile included). Set all
env vars, set `OAUTH_REDIRECT_URI` and `FRONTEND_ORIGIN` to the production URLs, add the
production redirect URI in Google Cloud Console, and set `ENABLE_DEBUG_ROUTES=false`.

> Cross-site cookies: in production set `https_only=True` and `same_site="none"` on the
> `SessionMiddleware` in `app/main.py` if the frontend and backend are on different domains.

## Known limitations

- **"This and following"** on recurring events is applied to the whole series (a true
  RRULE split is not implemented) — occurrence-only and entire-series are exact.
- **Session state is in-process** (`llm/session.py`) → single backend worker. Add Redis to
  scale horizontally.
- Mic capture uses `MediaRecorder` (all modern browsers; Safari may need a recent version).
- Single LLM provider (Gemini) by design — keeps the tool-calling loop simple.
