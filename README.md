# Executive AI Personal Assistant

A warm, bilingual (English / हिंदी / Hinglish) voice + text assistant that manages your **Google Calendar, Google Tasks, and Google Contacts** through natural language.

- **Backend:** FastAPI · Groq / Gemini (bilingual tool calling) · OpenRouter (fallback) · Sarvam (STT/TTS) · Google APIs · PostgreSQL / Supabase / SQLite
- **Frontend:** Next.js (App Router) with streaming tool cards, tappable confirmation/disambiguation UI, and mic voice input
- **Safety & Security:** Backend state machine enforcing read-before-write, contact disambiguation, destructive-action hard gates, and email whitelisting — completely independent of LLM output.

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
      Groq / Gemini / ◄────┤   loop (≤6)     ├──► Google Calendar / Tasks / Contacts
      OpenRouter Fallback  └────────────────┘
                                   │ reply text
                                   ▼
                          /voice/speak ──► Sarvam TTS ──► audio playback
```

The state machine is the single source of truth. Voice is a presentation layer: STT produces a text message that flows through the exact same `/chat` pipeline, and the reply is optionally spoken. A Sarvam outage degrades gracefully to text mode and never blocks Calendar or Task operations.

---

## Quick start (Docker)

```bash
cp backend/.env.example backend/.env      # fill in required keys (Google OAuth, Groq/Gemini API key)
docker compose up --build
# frontend → http://localhost:3000   backend → http://localhost:8000
```

## Quick start (local, no Docker)

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # fill in environment variables
uvicorn app.main:app --reload

# 2. Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local                  # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

---

## Environment & Configuration

Fill `backend/.env` (see `backend/.env.example`):

| Variable | Default / Description | Where to get / Instructions |
|---|---|---|
| `LLM_PROVIDER` | `groq` | Choose `groq` or `gemini` as primary model provider. |
| `GROQ_API_KEY` | *(required if using Groq)* | Obtain from [Groq Console](https://console.groq.com/keys). |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | High-speed LLM model on Groq. |
| `GEMINI_API_KEY` | *(required if using Gemini)* | Obtain from [Google AI Studio](https://aistudio.google.com/apikey). |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model identifier. |
| `OPENROUTER_API_KEY` | *(optional)* | Fallback key if Groq reaches rate limits. |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini-search-preview:free` | Fallback model identifier. |
| `SARVAM_API_KEY` | *(optional)* | Obtain from [Sarvam AI Dashboard](https://dashboard.sarvam.ai). If omitted, system runs in text mode. |
| `GOOGLE_CLIENT_ID` | *(required)* | Google Cloud Console → APIs & Services → Credentials → **OAuth client ID** (Web application). |
| `GOOGLE_CLIENT_SECRET` | *(required)* | Google Cloud OAuth Client Secret. |
| `OAUTH_REDIRECT_URI` | `http://localhost:8000/auth/callback` | Authorized redirect URI configured in Google Cloud Console. |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Frontend web application origin for CORS & cookie policy. |
| `DATABASE_URL` | *(optional)* | PostgreSQL / Supabase connection URL. If set, uses PostgreSQL; otherwise defaults to local SQLite. |
| `DB_PATH` | `tokens.db` | SQLite database filepath used when `DATABASE_URL` is omitted. |
| `ALLOWED_USER_EMAILS` | `[]` | JSON array of allowed emails (e.g. `["user@example.com"]`) to restrict access. |
| `SESSION_SECRET` | *(required)* | Random secret key used to sign HTTP session cookies. |
| `TOKEN_ENCRYPTION_KEY` | *(required)* | Fernet encryption key for Google tokens. Generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `ENABLE_DEBUG_ROUTES` | `true` | Set to `false` in production to disable debug endpoints. |

### OAuth & Security
OAuth requests **offline access** and scopes: `calendar`, `tasks`, `contacts.readonly`, `openid`, and `userinfo.email`. 
Tokens are Fernet-encrypted and stored securely in PostgreSQL or SQLite. Access can be locked down strictly to authorized user emails via `ALLOWED_USER_EMAILS`.

---

## Database & Persistence

The assistant supports dual storage engines managed automatically by `app/db/connection.py`:

- **Development:** Local SQLite database (`tokens.db`).
- **Production:** PostgreSQL / Supabase database specified via `DATABASE_URL`. Includes automatic resolution of Supabase IPv6 direct URLs to verified IPv4 Pooler hosts.
- **Stored Data:** Encrypted Google OAuth tokens (`tokens`), user daily conversation history & state (`day_sessions`), and audit logs (`action_log`).

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

The yes/no and scope parsing (`llm/intent.py`) lives in **code, not the LLM**, so the confirmation gate never depends on the model remembering it.

---

## Tests

```bash
cd backend && source .venv/bin/activate
python app/llm/intent.py      # keyword parser self-check
python tests/test_safety.py   # 5 safety flows, fully offline (LLM + Google mocked)
```

`test_safety.py` proves the required Sprint-3 safety flows **and** verifies that an adversarial model attempting to skip confirmation cannot trigger destructive actions.

---

## Resilience Matrix

See [`docs/RESILIENCE.md`](docs/RESILIENCE.md) for the scenario checklist. Summary:

| Scenario | Behaviour |
|---|---|
| Auth expiry | `AUTH_EXPIRED` error → UI shows *Connect Google Account*; never claims success |
| No results | Model says "nothing found, want to rephrase?" |
| Rate limit (429) | `tools/_google.py` retries 3× with exponential backoff; fallback to OpenRouter when enabled |
| Google 5xx / network | Typed `GOOGLE_API_ERROR`, no crash |
| Sarvam outage | `/voice/*` returns 200 with a fallback note; text chat unaffected |
| Runaway loop | Capped at 6 tool round-trips → graceful "could you rephrase?" |

---

## Production Deployment

For detailed, step-by-step instructions on deploying the full stack to production using **Vercel** (Frontend), **Render** (Backend), and **Supabase** (PostgreSQL), refer to the official deployment guide:

📖 **[Deployment Guide](docs/deployment_guide.md)**

---

## Known Limitations

- **"This and following"** on recurring events is applied to the whole series (a true RRULE split is not implemented) — occurrence-only and entire-series are exact.
- **Session state is in-process** (`llm/session.py`) + backed by PostgreSQL/SQLite for state preservation across restarts.
- Mic capture uses `MediaRecorder` (supported by all modern desktop and mobile browsers).
