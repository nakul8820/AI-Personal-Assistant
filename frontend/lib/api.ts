export const API = typeof window !== "undefined"
  ? (process.env.NEXT_PUBLIC_BACKEND_URL || "").replace(/\/+$/, "")
  : (process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_API_URL || "").replace(/\/+$/, "");

const tz = () =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

export type ChatResponse = {
  type: "message" | "confirmation_required" | "disambiguation_required" | "error";
  text: string;
  tool_calls?: any[];
  action?: string | null;
  details?: any;
  candidates?: any[] | null;
  error_code?: string | null;
  language?: string | null;
  metrics?: {
    api_hits: number;
    total_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    model: string;
    providers_used: string;
  };
};

export type StreamEvent =
  | { kind: "status"; text: string }
  | { kind: "tool"; name: string; result_summary?: string; error?: string; arguments?: any }
  | { kind: "final"; response: ChatResponse };

export type HistoryItem = { role: "user" | "assistant"; text: string };

export type ActivityEntry = {
  timestamp: string;
  tool_name: string;
  tool_args: string | null;
  result_summary: string | null;
  provider: string | null;
  api_hits: number;
  total_tokens: number;
};

export function getAuthHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (typeof window !== "undefined") {
    try {
      const params = new URLSearchParams(window.location.search);
      const tokenFromUrl = params.get("auth_token");
      if (tokenFromUrl) {
        localStorage.setItem("auth_token", tokenFromUrl);
        // Clean URL query parameter without reloading
        const cleanUrl = window.location.pathname + window.location.hash;
        window.history.replaceState({}, document.title, cleanUrl);
      }
      const token = localStorage.getItem("auth_token");
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
    } catch {
      // Ignore window/storage access errors
    }
  }
  return headers;
}

export async function authStatus() {
  const r = await fetch(`${API}/auth/status`, { credentials: "include", headers: getAuthHeaders() });
  const data = await r.json();
  if (data && data.authenticated === false && typeof window !== "undefined") {
    // If backend reports unauthenticated, clear local auth token
    localStorage.removeItem("auth_token");
  }
  return data as { authenticated: boolean; email?: string; name?: string; error_code?: string };
}

export function loginUrl() {
  if (typeof window !== "undefined") {
    return `${API}/auth/login?redirect=${encodeURIComponent(window.location.origin)}`;
  }
  return `${API}/auth/login`;
}

export async function logoutApi() {
  const r = await fetch(`${API}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: getAuthHeaders(),
  });
  if (typeof window !== "undefined") {
    localStorage.removeItem("auth_token");
  }
  return r.json();
}

/** Fetch today's conversation history for UI restoration on page load. */
export async function getHistory(): Promise<{ session_id: string; date: string; items: HistoryItem[] }> {
  const r = await fetch(`${API}/chat/history`, {
    credentials: "include",
    headers: getAuthHeaders({ "X-User-Timezone": tz() }),
  });
  if (r.status === 401) {
    throw new Error("SESSION_TIMEOUT");
  }
  if (!r.ok) return { session_id: "", date: "", items: [] };
  return r.json();
}

/** Fetch today's tool-call activity log. */
export async function getTodayActivity(): Promise<{ date: string; actions: ActivityEntry[] }> {
  const r = await fetch(`${API}/chat/activity`, {
    credentials: "include",
    headers: getAuthHeaders({ "X-User-Timezone": tz() }),
  });
  if (r.status === 401) {
    throw new Error("SESSION_TIMEOUT");
  }
  if (!r.ok) return { date: "", actions: [] };
  return r.json();
}

/** POST /chat/stream and yield SSE events as they arrive. */
export async function* chatStream(
  sessionId: string,
  message: string,
  language?: string | null
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: getAuthHeaders({ "Content-Type": "application/json", "X-User-Timezone": tz() }),
    body: JSON.stringify({ session_id: sessionId, message, language: language ?? null }),
  });
  if (!res.ok) {
    try {
      const err = await res.json();
      yield {
        kind: "final",
        response: {
          type: "error",
          text: err.message || "Unauthorized",
          error_code: err.error_code || "AUTH_EXPIRED",
        },
      };
    } catch {
      yield {
        kind: "final",
        response: {
          type: "error",
          text: "Session connection error",
          error_code: "CONNECTION_ERROR",
        },
      };
    }
    return;
  }
  if (!res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (buf.trim()) {
        const lines = buf.split("\n");
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const data = JSON.parse(trimmed.slice(6).trim());
              yield data;
            } catch (err) {
              console.error("Error parsing final line:", trimmed, err);
            }
          }
        }
      }
      break;
    }
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      const lines = part.split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("data: ")) {
          try {
            const data = JSON.parse(trimmed.slice(6).trim());
            yield data;
          } catch (err) {
            console.error("Error parsing SSE line:", trimmed, err);
          }
        }
      }
    }
  }
}

export async function transcribe(blob: Blob) {
  const fd = new FormData();
  fd.append("file", blob, "audio.webm");
  const r = await fetch(`${API}/voice/transcribe`, {
    method: "POST",
    credentials: "include",
    headers: getAuthHeaders(),
    body: fd,
  });
  return r.json() as Promise<{ transcript?: string; language?: string; error_code?: string }>;
}

export async function speak(text: string, language: string) {
  const fd = new FormData();
  fd.append("text", text);
  fd.append("language", language || "en-IN");
  const r = await fetch(`${API}/voice/speak`, {
    method: "POST",
    credentials: "include",
    headers: getAuthHeaders(),
    body: fd,
  });
  const ct = r.headers.get("content-type") || "";
  if (!ct.includes("audio")) return null; // graceful voice fallback
  return r.blob();
}
