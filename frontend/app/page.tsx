"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  API,
  authStatus,
  chatStream,
  getHistory,
  getTodayActivity,
  loginUrl,
  speak,
  transcribe,
  type ActivityEntry,
  type ChatResponse,
  type HistoryItem,
} from "@/lib/api";

// ── Icons ─────────────────────────────────────────────────────────────────────
const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
    <path
      fill="#4285F4"
      d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.53-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-8.81z"
    />
    <path
      fill="#34A853"
      d="M12 24c3.24 0 5.97-1.08 7.96-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.08 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.15C3.28 20.22 7.36 24 12 24z"
    />
    <path
      fill="#FBBC05"
      d="M5.27 14.24A7.17 7.17 0 0 1 4.88 12c0-.79.13-1.56.39-2.24V6.61H1.29A11.94 11.94 0 0 0 0 12c0 1.92.45 3.74 1.29 5.39l3.98-3.15z"
    />
    <path
      fill="#EA4335"
      d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.22 0 12 0 7.36 0 3.28 3.78 1.29 7.61l3.98 3.15c.95-2.85 3.6-4.96 6.73-4.96z"
    />
  </svg>
);

const CalendarIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="16" height="16">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

const TaskIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="16" height="16">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
  </svg>
);

const ContactIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="16" height="16">
    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
  </svg>
);

const MicIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="20" height="20">
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
  </svg>
);

const SendIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="18" height="18">
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const LockIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="16" height="16">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0110 0v4" />
  </svg>
);

const LogoutIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="16" height="16">
    <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </svg>
);

const ActivityIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="16" height="16">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

const ClockIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14" height="14">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
);

const RefreshIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14" height="14">
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.228 9H18.01" />
  </svg>
);

const ChevronCloseIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={className} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" width="14" height="14">
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
);

// ── Types ─────────────────────────────────────────────────────────────────────
type Item =
  | { id: number; kind: "user" | "error"; text: string; isAuthError?: boolean }
  | { id: number; kind: "assistant"; text: string; metrics?: ChatResponse["metrics"] }
  | { id: number; kind: "tool"; text: string; state: "run" | "done" | "err" }
  | { id: number; kind: "confirm"; res: ChatResponse }
  | { id: number; kind: "disambig"; res: ChatResponse };

let _id = 0;
const nextId = () => ++_id;

// ── Constants ─────────────────────────────────────────────────────────────────
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;      // 5 minutes — must match backend
const IDLE_WARN_MS    = IDLE_TIMEOUT_MS - 30_000; // warn 30s before lock
const SESSION_MAX_MS  = 8 * 60 * 60 * 1000; // 8h cookie lifetime

// ── Tool display names ────────────────────────────────────────────────────────
const TOOL_LABELS: Record<string, string> = {
  search_calendar_events: "📅 Calendar search",
  create_calendar_event:  "📅 Created event",
  update_calendar_event:  "✏️ Updated event",
  delete_calendar_event:  "🗑️ Deleted event",
  list_tasks:             "✅ Task list",
  create_task:            "➕ Created task",
  update_task:            "✏️ Updated task",
  complete_task:          "✅ Completed task",
  delete_task:            "🗑️ Deleted task",
  search_contacts:        "👤 Contact search",
};

// ─────────────────────────────────────────────────────────────────────────────
export default function Home() {
  const [auth, setAuth] = useState<{ authenticated: boolean; email?: string; name?: string; error_code?: string } | null>(null);
  const [items, setItems]       = useState<Item[]>([]);
  const [input, setInput]       = useState("");
  const [busy, setBusy]         = useState(false);
  const [status, setStatus]     = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [showActivity, setShowActivity] = useState(false);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [answeredCardIds, setAnsweredCardIds] = useState<number[]>([]);

  // Session timer
  const [loginTime, setLoginTime]       = useState<number | null>(null);
  const [, setTick]                     = useState(0);

  // Idle timeout
  const lastActivityRef                 = useRef<number>(Date.now());
  const [sessionLocked, setSessionLocked] = useState(false);
  const [idleWarning, setIdleWarning]   = useState(false);

  const streamRef  = useRef<HTMLDivElement>(null);
  const recorder   = useRef<MediaRecorder | null>(null);
  const chunks     = useRef<Blob[]>([]);

  // ── Track last user activity ───────────────────────────────────────────────
  const resetIdleTimer = useCallback(() => {
    lastActivityRef.current = Date.now();
    setIdleWarning(false);
    setSessionLocked(false);
  }, []);

  // Global window presence events to detect actual user active viewing
  useEffect(() => {
    const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
    const handler = () => resetIdleTimer();
    events.forEach((ev) => window.addEventListener(ev, handler));
    return () => events.forEach((ev) => window.removeEventListener(ev, handler));
  }, [resetIdleTimer]);

  // Keep-alive ping to backend when user is actively using the page
  useEffect(() => {
    const pingInterval = setInterval(() => {
      const idle = Date.now() - lastActivityRef.current;
      if (idle < IDLE_TIMEOUT_MS && auth?.authenticated) {
        authStatus().catch(() => {});
      }
    }, 2 * 60 * 1000); // ping every 2 minutes
    return () => clearInterval(pingInterval);
  }, [auth, resetIdleTimer]);

  // ── Auth ───────────────────────────────────────────────────────────────────
  const refreshAuth = useCallback(() =>
    authStatus()
      .then((res) => {
        setAuth(res);
        if (res.authenticated && res.email) {
          // Stable day-scoped session key
          const today = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
          setSessionId(`${res.email}:${today}`);

          let stored = localStorage.getItem("g_login_time");
          if (!stored) {
            stored = Date.now().toString();
            localStorage.setItem("g_login_time", stored);
          }
          setLoginTime(parseInt(stored, 10));
        } else {
          localStorage.removeItem("g_login_time");
          setLoginTime(null);
        }
      })
      .catch(() => {
        setAuth({ authenticated: false });
        localStorage.removeItem("g_login_time");
        setLoginTime(null);
      }), []);

  useEffect(() => { refreshAuth(); }, [refreshAuth]);

  // ── Load today's history once auth resolves ────────────────────────────────
  useEffect(() => {
    if (!auth?.authenticated || historyLoaded) return;
    setHistoryLoaded(true);
    getHistory().then(({ items: hist }) => {
      if (!hist || hist.length === 0) return;
      const restored: Item[] = hist.map((h: HistoryItem) => ({
        id: nextId(),
        kind: h.role === "user" ? "user" : "assistant",
        text: h.text,
      }));
      setItems(restored);
    }).catch((err) => {
      if (err?.message === "SESSION_TIMEOUT") {
        setSessionLocked(true);
      }
    });
  }, [auth, historyLoaded]);

  // ── Idle timeout enforcement ───────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      const idle = Date.now() - lastActivityRef.current;
      if (idle >= IDLE_TIMEOUT_MS) {
        setSessionLocked(true);
        setIdleWarning(false);
      } else if (idle >= IDLE_WARN_MS) {
        setIdleWarning(true);
      }
      setTick(t => t + 1); // also drives the session age display
    }, 5000); // check every 5s
    return () => clearInterval(interval);
  }, []);

  // ── Session expiry auto-check ──────────────────────────────────────────────
  useEffect(() => {
    if (!loginTime) return;
    const remaining = SESSION_MAX_MS - (Date.now() - loginTime);
    if (remaining <= 0) { refreshAuth(); return; }
    const t = setTimeout(() => refreshAuth(), remaining + 500);
    return () => clearTimeout(t);
  }, [loginTime, refreshAuth]);

  // ── Auto scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: "smooth" });
  }, [items, status]);

  const handleLogout = async () => {
    localStorage.removeItem("g_login_time");
    try {
      await fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });
    } catch (e) {
      console.error(e);
    }
    setItems([]);
    setHistoryLoaded(false);
    refreshAuth();
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const push = (it: any) => setItems((p) => [...p, { ...it, id: nextId() } as Item]);

  // ── Send message ───────────────────────────────────────────────────────────
  async function send(text: string, opts?: { fromVoice?: boolean; language?: string; cardId?: number }) {
    if (!text.trim() || busy) return;
    resetIdleTimer();
    if (opts?.cardId !== undefined) {
      setAnsweredCardIds((prev) => [...prev, opts.cardId!]);
    }
    push({ kind: "user", text });
    setInput("");
    setBusy(true);
    setStatus("Thinking");
    try {
      for await (const ev of chatStream(sessionId, text, opts?.language)) {
        if (ev.kind === "status") {
          setStatus(ev.text);
        } else if (ev.kind === "tool") {
          const label = ev.error ? `⚠️ ${ev.name}` : `${ev.name} · ${ev.result_summary ?? "done"}`;
          push({ kind: "tool", text: label, state: ev.error ? "err" : "done" });
        } else if (ev.kind === "final") {
          setStatus(null);
          await handleFinal(ev.response, opts);
        }
      }
    } catch {
      push({ kind: "error", text: "Connection problem — please try again." });
    } finally {
      setStatus(null);
      setBusy(false);
      // Automatically refresh the activity log if it is active/open
      if (showActivity) {
        loadActivity();
      }
    }
  }

  async function handleFinal(res: ChatResponse, opts?: { fromVoice?: boolean; language?: string }) {
    if (res.type === "confirmation_required") { push({ kind: "confirm", res }); return; }
    if (res.type === "disambiguation_required") { push({ kind: "disambig", res }); return; }
    if (res.type === "error") {
      if (res.error_code === "SESSION_TIMEOUT") {
        setSessionLocked(true);
        return;
      }
      push({ kind: "error", text: res.text, isAuthError: res.error_code === "AUTH_EXPIRED" });
      if (res.error_code === "AUTH_EXPIRED") refreshAuth();
      return;
    }
    push({ kind: "assistant", text: res.text, metrics: res.metrics });
    if (opts?.fromVoice && res.text) {
      const blob = await speak(res.text, opts.language || res.language || "en-IN");
      if (blob) new Audio(URL.createObjectURL(blob)).play().catch(() => {});
      else setVoiceNote("Voice reply unavailable — showing text.");
    }
  }

  // ── Voice ──────────────────────────────────────────────────────────────────
  async function toggleRecord() {
    if (recording) { recorder.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunks.current = [];
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setStatus("Transcribing");
        const blob = new Blob(chunks.current, { type: "audio/webm" });
        const r = await transcribe(blob);
        setStatus(null);
        if (r.error_code || !r.transcript) { setVoiceNote("Voice unavailable — please type."); return; }
        setVoiceNote(null);
        send(r.transcript, { fromVoice: true, language: r.language });
      };
      recorder.current = mr;
      mr.start();
      setRecording(true);
    } catch { setVoiceNote("Mic permission denied."); }
  }

  // ── Activity panel ────────────────────────────────────────────────────────
  const loadActivity = () => {
    getTodayActivity().then(({ actions }) => setActivity(actions)).catch((err) => {
      if (err?.message === "SESSION_TIMEOUT") {
        setSessionLocked(true);
      }
    });
  };

  const toggleActivity = () => {
    if (!showActivity) loadActivity();
    setShowActivity(s => !s);
  };

  // ── Session display ────────────────────────────────────────────────────────
  const getSessionAgeStr = () => {
    if (!loginTime) return "";
    const mins = Math.floor((Date.now() - loginTime) / 60000);
    const hours = Math.floor(mins / 60);
    return hours > 0 ? `Uptime: ${hours}h ${mins % 60}m` : `Uptime: ${mins}m`;
  };

  const getIdleStr = () => {
    const idle = Math.floor((Date.now() - lastActivityRef.current) / 1000);
    const remaining = Math.ceil((IDLE_TIMEOUT_MS - idle * 1000) / 1000);
    return `Locks in ${Math.ceil(remaining / 60)}m ${remaining % 60}s`;
  };

  const sessionExpiringSoon = () => loginTime && (Date.now() - loginTime) >= SESSION_MAX_MS * 0.9;

  // ── Loading Splash screen ──────────────────────────────────────────────────
  if (auth === null) {
    return (
      <div className="full-screen-container">
        <div className="bg-ambient-blobs">
          <div className="ambient-blob one" />
          <div className="ambient-blob two" />
        </div>
        <div className="center-card">
          <div className="splash-loader-circle">
            <div className="splash-loader-inner" />
          </div>
          <div className="brand-title">Executive Assistant</div>
          <div className="brand-desc" style={{ marginBottom: 0 }}>Starting secure workspace session…</div>
        </div>
      </div>
    );
  }

  // ── Sign-in screen ─────────────────────────────────────────────────────────
  if (!auth.authenticated) {
    return (
      <div className="full-screen-container">
        <div className="bg-ambient-blobs">
          <div className="ambient-blob one" />
          <div className="ambient-blob two" />
        </div>
        <div className="center-card">
          <div className="sidebar-brand-icon" style={{ width: 28, height: 28, margin: "0 auto 20px", boxShadow: "0 0 16px var(--accent)" }} />
          <div className="brand-title">Executive Assistant</div>
          <p className="brand-desc">
            A warm, bilingual (English / हिंदी) voice &amp; text workspace assistant for managing your Google Calendar, Tasks, and Contacts.
          </p>
          {auth.error_code === "AUTH_EXPIRED" && (
            <p className="badge danger" style={{ marginBottom: 24, padding: "8px 12px", width: "100%", justifyContent: "center" }}>
              ⚠️ Your Google connection expired. Please reconnect.
            </p>
          )}
          <button className="connect-google-btn" onClick={() => (window.location.href = loginUrl())}>
            <GoogleIcon />
            Connect Google Account
          </button>
        </div>
      </div>
    );
  }

  // ── Session locked overlay ─────────────────────────────────────────────────
  if (sessionLocked) {
    return (
      <div className="full-screen-container">
        <div className="bg-ambient-blobs">
          <div className="ambient-blob one" />
          <div className="ambient-blob two" />
        </div>
        <div className="center-card">
          <div style={{ fontSize: 44, marginBottom: 16 }}>🔒</div>
          <div className="brand-title">Session Locked</div>
          <p className="brand-desc">
            Locked due to inactivity. Your active workspace conversation history has been saved and will resume upon re-authenticating.
          </p>
          <button className="connect-google-btn" onClick={() => (window.location.href = loginUrl())}>
            <GoogleIcon />
            🔑 Sign in to Unlock
          </button>
          <p style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 20 }}>
            Session email: <b>{auth.email}</b>
          </p>
        </div>
      </div>
    );
  }

  // ── Main chat UI ───────────────────────────────────────────────────────────
  return (
    <div className={`app-container ${showActivity ? "with-activity" : ""}`}>
      
      {/* LEFT SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <span className="sidebar-brand-icon" />
            Executive Portal
          </div>
          <div className="sidebar-brand-sub">Voice AI Workspace</div>
          
          <div className="sidebar-menu">
            <div className="sidebar-card">
              <div className="sidebar-card-title">Assistant Tools</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)" }}>
                  <CalendarIcon /> Calendar Schedule
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)" }}>
                  <TaskIcon /> Tasks Checklist
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)" }}>
                  <ContactIcon /> Contacts Search
                </div>
              </div>
            </div>

            <div className="sidebar-card">
              <div className="sidebar-card-title">Quick Tips</div>
              <div style={{ color: "var(--text-secondary)", lineHeight: 1.4 }}>
                Try speaking in Hindi: <br/>
                <i style={{ color: "var(--text-muted)", fontSize: 12 }}>&quot;कल दोपहर 3 बजे मेरी मीटिंग रख दो&quot;</i>
              </div>
            </div>
          </div>
        </div>

        {/* Profile Card / Sign Out */}
        <div className="sidebar-profile">
          <div className="sidebar-profile-avatar">
            {auth.name ? auth.name.substring(0, 1).toUpperCase() : auth.email ? auth.email.substring(0, 1).toUpperCase() : "U"}
          </div>
          <div className="sidebar-profile-info">
            <div className="sidebar-profile-email" title={auth.email} style={{ fontWeight: 700 }}>
              {auth.name || auth.email?.split("@")[0]}
            </div>
            <div style={{ color: "var(--text-muted)", fontSize: 11 }}>Active User</div>
          </div>
          <button className="sidebar-profile-logout" onClick={handleLogout} title="Sign Out of Portal">
            <LogoutIcon />
          </button>
        </div>
      </aside>

      {/* CENTER WORKSPACE */}
      <main className="main-chat-area">
        
        {/* Header toolbar */}
        <header className="dashboard-header">
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 14, fontWeight: 700 }}>Workspace Control</span>
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Secure Session Interface</span>
          </div>

          <div className="header-status-group">
            {voiceNote && <span className="badge danger">{voiceNote}</span>}
            
            {idleWarning && (
              <button 
                className="badge warn" 
                style={{ cursor: "pointer", border: "1px solid rgba(255, 159, 10, 0.3)" }} 
                onClick={resetIdleTimer}
                title="Tap to prevent lock"
              >
                ⏳ {getIdleStr()} — Stay active
              </button>
            )}

            {loginTime && (
              <span className="badge" style={{ color: sessionExpiringSoon() ? "var(--danger)" : undefined }}>
                <ClockIcon /> {getSessionAgeStr()}
              </span>
            )}

            <button
              className={`btn secondary ${showActivity ? "primary" : ""}`}
              style={{ fontSize: 12, padding: "6px 12px", height: 32 }}
              onClick={toggleActivity}
              title="Toggle activity sidebar"
            >
              <ActivityIcon /> {showActivity ? "Hide Logs" : "Activity"}
            </button>

            <button
              className="btn secondary"
              style={{ fontSize: 12, padding: "6px 12px", height: 32 }}
              onClick={() => (window.location.href = loginUrl())}
              title="Refresh credentials connection"
            >
              <RefreshIcon /> Reconnect
            </button>

            <button
              className="btn secondary"
              style={{ fontSize: 12, padding: "6px 12px", height: 32, borderColor: "var(--danger-glow)" }}
              onClick={handleLogout}
              title="Sign Out of Portal"
            >
              <LogoutIcon /> Sign Out
            </button>
          </div>
        </header>

        {/* Chat message flow */}
        <div className="chat-container" ref={streamRef}>
          {items.length === 0 && (
            <div className="bubble-row assistant-row">
              <div className="chat-bubble assistant">
                Hello, <span style={{ color: "var(--accent)", fontWeight: 700 }}>{auth?.name ? auth.name.split(" ")[0] : "there"}</span>! Welcome to your Executive Assistant. I can manage your Google calendar, tasks, and search contacts. <br/><br/>
                Try asking me: <b>&quot;What&apos;s on my calendar today?&quot;</b>, <b>&quot;Schedule a sync tomorrow at 10 AM&quot;</b>, or speak directly in English or Hindi. 🎙️
              </div>
            </div>
          )}
          
          {items.map((it) => renderItem(it, send, busy, answeredCardIds))}
          
          {status && (
            <div className="tool-indicator">
              <span className="dots-loader"><span>●</span><span><span>●</span></span><span>●</span></span>
              <span>{status}…</span>
            </div>
          )}
        </div>

        {/* Floating input bar */}
        <div className="chat-composer-container">
          <div className="chat-composer">
            <button
              className={`btn-icon record ${recording ? "recording" : ""}`}
              onClick={toggleRecord}
              title={recording ? "Stop Recording" : "Speak to Assistant"}
            >
              {recording ? <span style={{ fontSize: 8 }}>■</span> : <MicIcon />}
            </button>
            
            <input
              value={input}
              placeholder="Type your message or click the microphone to speak…"
              onChange={(e) => { setInput(e.target.value); resetIdleTimer(); }}
              onKeyDown={(e) => e.key === "Enter" && send(input)}
              disabled={busy}
            />

            <button 
              className="btn-icon send" 
              onClick={() => send(input)} 
              disabled={busy || !input.trim()} 
              title="Send Command"
            >
              <SendIcon />
            </button>
          </div>
        </div>
      </main>

      {/* RIGHT ACTIVITY DRAWER */}
      {showActivity && (
        <aside className="activity-drawer">
          <div className="activity-drawer-header">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <ActivityIcon />
              <span>Session Log</span>
            </div>
            <button 
              className="sidebar-profile-logout" 
              style={{ padding: 4 }} 
              onClick={toggleActivity}
              title="Close Panel"
            >
              <ChevronCloseIcon />
            </button>
          </div>

          <div className="activity-list">
            {activity.length === 0 ? (
              <div style={{ color: "var(--text-muted)", fontSize: 13, textAlign: "center", marginTop: 20 }}>
                No active operations processed in this session yet.
              </div>
            ) : (
              activity.map((a, i) => (
                <div key={i} className="activity-timeline-item">
                  <div className={`activity-timeline-dot ${a.result_summary && !a.result_summary.includes("error") ? "done" : "err"}`} />
                  <div className="activity-time">
                    {new Date(a.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </div>
                  <div className="activity-title">
                    {TOOL_LABELS[a.tool_name] ?? a.tool_name}
                  </div>
                  <div className="activity-desc">
                    {a.result_summary ?? "Executed successfully"}
                  </div>
                  <div className="activity-stats">
                    {a.total_tokens > 0 && <span>📊 {a.total_tokens} tkn</span>}
                    {a.provider && <span>🤖 {a.provider}</span>}
                  </div>
                </div>
              ))
            )}
          </div>
        </aside>
      )}

    </div>
  );
}

// ── Item renderer ─────────────────────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function renderItem(it: Item, send: (t: string, o?: any) => void, busy: boolean, answeredCardIds: number[]) {
  switch (it.kind) {
    case "user":
      return (
        <div key={it.id} className="bubble-row user-row">
          <div className="chat-bubble user">{it.text}</div>
        </div>
      );
    case "assistant":
      return (
        <div key={it.id} className="bubble-row assistant-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
          <div className="chat-bubble assistant">{it.text}</div>
          {it.metrics && (
            <div className="chat-bubble-meta">
              <span className="chat-bubble-meta-item">
                ⚡ <b>{it.metrics.api_hits}</b> API {it.metrics.api_hits === 1 ? "hit" : "hits"}
              </span>
              <span className="chat-bubble-meta-item">
                📊 <b>{it.metrics.total_tokens}</b> tokens ({it.metrics.prompt_tokens}↑ / {it.metrics.completion_tokens}↓)
              </span>
              <span className="chat-bubble-meta-item">
                🤖 {it.metrics.providers_used
                  ? it.metrics.providers_used.includes("openrouter")
                    ? <><span style={{ color: "var(--danger)" }}>⚠️ fallback:</span> {it.metrics.providers_used}</>
                    : <b>{it.metrics.providers_used}</b>
                  : <b>{it.metrics.model}</b>
                }
              </span>
            </div>
          )}
        </div>
      );
    case "error":
      return (
        <div key={it.id} className="card-wrapper" style={{ margin: "8px 0" }}>
          <div className="card danger">
            <h4>System Alert</h4>
            <div className="sub">{it.text}</div>
            {it.isAuthError && (
              <div className="card-choices">
                <button
                  className="btn danger"
                  onClick={() => (window.location.href = loginUrl())}
                >
                  🔑 Reconnect Google Connection
                </button>
              </div>
            )}
          </div>
        </div>
      );
    case "tool":
      return (
        <div key={it.id} className={`tool-indicator ${it.state === "err" ? "err" : "done"}`} style={{ margin: "4px 0" }}>
          <span className="icon">{it.state === "err" ? "⚠️" : "✓"}</span>
          <span>{it.text}</span>
        </div>
      );
    case "confirm":
      return <ConfirmCard key={it.id} cardId={it.id} res={it.res} send={send} busy={busy} answered={answeredCardIds.includes(it.id)} />;
    case "disambig":
      return <DisambigCard key={it.id} cardId={it.id} res={it.res} send={send} busy={busy} answered={answeredCardIds.includes(it.id)} />;
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ConfirmCard({ cardId, res, send, busy, answered }: { cardId: number; res: ChatResponse; send: any; busy: boolean; answered: boolean }) {
  const isDelete = (res.action || "").startsWith("delete");
  const disabled = busy || answered;
  
  if (res.action === "recurring_scope") {
    return (
      <div className="card-wrapper" style={{ margin: "8px 0", opacity: answered ? 0.55 : 1, transition: "opacity 0.2s" }}>
        <div className="card">
          <h4>Recurring Calendar Event Range</h4>
          <div className="sub">{res.text}</div>
          <div className="card-choices">
            <button className="btn secondary" disabled={disabled} onClick={() => send("this occurrence only", { cardId })}>This occurrence</button>
            <button className="btn secondary" disabled={disabled} onClick={() => send("this and following", { cardId })}>This &amp; following</button>
            <button className="btn primary" disabled={disabled} onClick={() => send("the entire series", { cardId })}>Entire series</button>
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="card-wrapper" style={{ margin: "8px 0", opacity: answered ? 0.55 : 1, transition: "opacity 0.2s" }}>
      <div className={`card ${isDelete ? "danger" : ""}`}>
        <h4>{isDelete ? "Confirm Event Deletion" : "Confirm Action Request"}</h4>
        <div className="sub">{res.text}</div>
        <div className="card-choices">
          <button className={`btn ${isDelete ? "danger" : "primary"}`} disabled={disabled} onClick={() => send("yes", { cardId })}>
            {isDelete ? "Delete Event" : "Confirm"}
          </button>
          <button className="btn secondary" disabled={disabled} onClick={() => send("no", { cardId })}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function DisambigCard({ cardId, res, send, busy, answered }: { cardId: number; res: ChatResponse; send: any; busy: boolean; answered: boolean }) {
  const disabled = busy || answered;
  return (
    <div className="card-wrapper" style={{ margin: "8px 0", opacity: answered ? 0.55 : 1, transition: "opacity 0.2s" }}>
      <div className="card">
        <h4>Resolve Disambiguation Query</h4>
        <div className="sub">{res.text}</div>
        <div className="card-choices" style={{ flexDirection: "column", alignItems: "stretch", width: "100%" }}>
          {(res.candidates || []).map((c, i) => (
            <button
              key={i}
              className="btn secondary"
              style={{ justifyContent: "space-between", textAlign: "left", width: "100%", padding: "10px 14px", height: "auto" }}
              disabled={disabled}
              onClick={() => send(`${c.title}${c.when ? " at " + c.when : ""}`, { cardId })}
            >
              <span>{c.title}</span>
              {c.when && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{c.when}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
