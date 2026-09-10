export type User = {
  id: string;
  email: string;
  display_name: string;
  gemini_configured: boolean;
};

export type Session = { access_token: string; token_type: string; user: User };
export type Action = { name: string; description: string };

export type Agent = {
  id: string;
  name: string;
  description: string;
  icon: string;
  desktop_only: boolean;
  hosted_capable: boolean;
};

export type PlanStep = { step: number; tool: string; description: string };

export type AgentChatMessage = {
  role: "user" | "assistant";
  content: string;
  agent: string;
  plan?: PlanStep[] | null;
};

export type ChatApiResponse = { response: string; agent: string; plan?: PlanStep[] | null };

export type MemoryEntryItem = { category: string; key: string; value: string; updated: string };
export type MemorySearchResult = MemoryEntryItem & { score: number };

export type TaskStep = { step: number; tool: string; description: string; status: string; output: string };
export type Task = { task_id: string; goal: string; status: string; result: string; error: string; steps: TaskStep[]; timestamp: string };

export type Context = {
  server_time: string;
  active_agent_hint: string | null;
  recent_topics: string[];
  memory_categories: Record<string, number>;
  desktop_features_available: boolean;
};

export type DataColumn = {
  name: string; dtype: string; non_null: number; null_count: number;
  min?: number | null; max?: number | null; mean?: number | null; std?: number | null;
  top_values?: { value: string; count: number }[] | null;
};
export type DataChart = { chart_type: string; title: string; labels: string[]; values: number[] };
export type DataAnalyzeResult = { row_count: number; column_count: number; columns: DataColumn[]; chart: DataChart | null };

export type Todo = { id: string; text: string; done: boolean; due_at: string | null; created_at: string };
export type CalendarEvent = { id: string; title: string; notes: string; start_at: string; end_at: string | null; created_at: string };
export type Notification = { id: string; title: string; body: string; kind: string; read_at: string | null; created_at: string };
export type DailyBriefing = {
  date: string;
  todos_due_today: Todo[];
  events_today: CalendarEvent[];
  unread_notifications: number;
  scheduled_tasks_today: number;
  greeting: string;
};

const HTTP_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const WS_URL = (process.env.NEXT_PUBLIC_WS_URL || HTTP_URL.replace(/^http/, "ws")).replace(/\/$/, "");

// The session token lives in an httpOnly cookie set by the API on
// /auth/signup and /auth/login (see api/server.py's _issue_session). It is
// intentionally never stored in localStorage/sessionStorage or attached
// manually as an Authorization header from client-side JS: keeping it out
// of reach of JavaScript means an XSS bug in this app can't be used to
// steal the session. `credentials: "include"` makes the browser send that
// cookie automatically with every request (and with the WebSocket upgrade
// request too, so /ws needs no token in its URL either).

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${HTTP_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
