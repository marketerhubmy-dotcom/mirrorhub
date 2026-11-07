const BASE = "/api/v1/agents";

export interface GoalProgress {
  total: number;
  completed: number;
  failed: number;
  pct: number;
}

export interface AgentGoal {
  id: number;
  goal_text: string;
  platform: string;
  product: string;
  target_count: number;
  priority: number;
  status: string;
  campaign_id: number | null;
  plan: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string | null;
  progress: GoalProgress;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentTask {
  id: number;
  goal_id: number;
  task_type: string;
  agent: string;
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AgentDecision {
  id: number;
  goal_id: number | null;
  task_id: number | null;
  agent: string;
  decision: string;
  reason: string;
  confidence: number;
  confidence_pct: number;
  alternative: string;
  expected_result: string;
  was_failsafe: boolean;
  created_at: string | null;
}

export interface MemoryEntry {
  id: number;
  key: string;
  category: string;
  summary: string;
  value: Record<string, unknown>;
  relevance_score: number;
  access_count: number;
  last_used_at: string | null;
  created_at: string | null;
}

export interface AgentStatus {
  active_goals: number;
  goals: AgentGoal[];
  pending_content_tasks: number;
  recent_decisions: AgentDecision[];
  loop_interval_s: number;
  tick_count: number;
}

export interface OptimizationSuggestion {
  area: string;
  severity: string;
  recommendation: string;
  data: Record<string, unknown>;
  device_id?: string;
  platform?: string;
}

export interface TimelineEvent {
  type: "decision" | "task";
  ts: string | null;
  agent: string;
  summary: string;
  detail: AgentDecision | AgentTask;
}

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Goals ─────────────────────────────────────────────────────────────────────

export const listGoals = (status?: string) =>
  req<AgentGoal[]>(status ? `/goals?status=${status}` : "/goals");

export const submitGoal = (data: {
  goal_text: string;
  platform: string;
  product: string;
  target_count: number;
  priority: number;
  audience?: string;
  visual_style?: string;
}) => req<AgentGoal>("/goals", { method: "POST", body: JSON.stringify(data) });

export const getGoal = (id: number) => req<AgentGoal>(`/goals/${id}`);
export const pauseGoal = (id: number) => req<AgentGoal>(`/goals/${id}/pause`, { method: "POST" });
export const resumeGoal = (id: number) => req<AgentGoal>(`/goals/${id}/resume`, { method: "POST" });
export const cancelGoal = (id: number) => req<AgentGoal>(`/goals/${id}/cancel`, { method: "POST" });

// ── Tasks ─────────────────────────────────────────────────────────────────────

export const listTasks = (goalId?: number, status?: string, limit = 50) => {
  const params = new URLSearchParams();
  if (goalId) params.set("goal_id", String(goalId));
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return req<AgentTask[]>(`/tasks?${params}`);
};
export const getTask = (id: number) => req<AgentTask>(`/tasks/${id}`);

// ── Status ────────────────────────────────────────────────────────────────────

export const getAgentStatus = () => req<AgentStatus>("/status");

// ── Decisions ─────────────────────────────────────────────────────────────────

export const listDecisions = (goalId?: number, limit = 50) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (goalId) params.set("goal_id", String(goalId));
  return req<AgentDecision[]>(`/decisions?${params}`);
};

// ── Memory ────────────────────────────────────────────────────────────────────

export const getMemory = (category?: string) =>
  req<MemoryEntry[]>(category ? `/memory?category=${category}` : "/memory");
export const forgetMemory = (key: string) =>
  req<void>(`/memory/${encodeURIComponent(key)}`, { method: "DELETE" });

// ── Optimization ──────────────────────────────────────────────────────────────

export const getSuggestions = () => req<OptimizationSuggestion[]>("/suggestions");
export const runOptimization = () => req<OptimizationSuggestion[]>("/optimize", { method: "POST" });

// ── Recovery ──────────────────────────────────────────────────────────────────

export const recoverJob = (campaignJobId: number, action = "auto") =>
  req<Record<string, unknown>>("/recover", {
    method: "POST",
    body: JSON.stringify({ campaign_job_id: campaignJobId, action }),
  });

// ── Timeline ─────────────────────────────────────────────────────────────────

export const getTimeline = (goalId?: number, limit = 100) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (goalId) params.set("goal_id", String(goalId));
  return req<TimelineEvent[]>(`/timeline?${params}`);
};
