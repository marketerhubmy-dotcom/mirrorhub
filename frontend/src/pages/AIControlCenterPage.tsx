import { useEffect, useRef, useState } from "react";
import {
  listGoals,
  submitGoal,
  pauseGoal,
  resumeGoal,
  cancelGoal,
  getAgentStatus,
  listDecisions,
  getMemory,
  forgetMemory,
  getSuggestions,
  runOptimization,
  getTimeline,
  type AgentGoal,
  type AgentDecision,
  type MemoryEntry,
  type OptimizationSuggestion,
  type TimelineEvent,
  type AgentStatus,
} from "../services/agentApi";

// ── Helpers ───────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  PLANNING: "bg-blue-800 text-blue-200",
  RUNNING:  "bg-green-800 text-green-200",
  PAUSED:   "bg-yellow-800 text-yellow-200",
  COMPLETED:"bg-gray-700 text-gray-300",
  FAILED:   "bg-red-900 text-red-300",
  CANCELLED:"bg-gray-800 text-gray-400",
};

const SEVERITY_COLOR: Record<string, string> = {
  warning: "border-yellow-600 bg-yellow-950",
  info:    "border-blue-600 bg-blue-950",
  error:   "border-red-600 bg-red-950",
};

const AGENT_ICON: Record<string, string> = {
  planner: "📐",
  content: "✍️",
  execution: "⚙️",
  recovery: "🔄",
  optimization: "📊",
};

function Badge({ label, cls }: { label: string; cls: string }) {
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>{label}</span>;
}

function ConfidenceBar({ pct }: { pct: number }) {
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-20 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400">{pct.toFixed(0)}%</span>
    </div>
  );
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
      <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

// ── Goal Card ─────────────────────────────────────────────────────────────────

function GoalCard({
  goal,
  onPause,
  onResume,
  onCancel,
}: {
  goal: AgentGoal;
  onPause: (id: number) => void;
  onResume: (id: number) => void;
  onCancel: (id: number) => void;
}) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-white font-medium leading-snug">{goal.goal_text}</p>
        <Badge label={goal.status} cls={STATUS_COLOR[goal.status] || "bg-gray-700 text-gray-300"} />
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-gray-400">
        <span>🎯 {goal.platform}</span>
        {goal.product && <span>📦 {goal.product}</span>}
        <span>🎬 {goal.target_count} videos</span>
        {goal.campaign_id && <span>📋 Campaign #{goal.campaign_id}</span>}
      </div>
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{goal.progress.completed}/{goal.progress.total} completed</span>
          <span>{goal.progress.pct.toFixed(0)}%</span>
        </div>
        <ProgressBar pct={goal.progress.pct} />
      </div>
      {goal.progress.failed > 0 && (
        <p className="text-xs text-red-400">{goal.progress.failed} failed</p>
      )}
      {goal.error && <p className="text-xs text-red-400 truncate">{goal.error}</p>}
      <div className="flex gap-2 pt-1">
        {goal.status === "RUNNING" && (
          <button onClick={() => onPause(goal.id)} className="text-xs px-2 py-1 bg-yellow-700 hover:bg-yellow-600 rounded text-white">Pause</button>
        )}
        {goal.status === "PAUSED" && (
          <button onClick={() => onResume(goal.id)} className="text-xs px-2 py-1 bg-green-700 hover:bg-green-600 rounded text-white">Resume</button>
        )}
        {!["COMPLETED","CANCELLED","FAILED"].includes(goal.status) && (
          <button onClick={() => onCancel(goal.id)} className="text-xs px-2 py-1 bg-red-800 hover:bg-red-700 rounded text-white">Cancel</button>
        )}
      </div>
    </div>
  );
}

// ── Decision Row ──────────────────────────────────────────────────────────────

function DecisionRow({ d }: { d: AgentDecision }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-gray-700 py-2">
      <button className="w-full text-left flex items-center gap-2" onClick={() => setOpen(!open)}>
        <span className="text-sm">{AGENT_ICON[d.agent] || "🤖"}</span>
        <span className="text-xs font-mono text-indigo-300">{d.agent}</span>
        <span className="text-xs text-white flex-1 truncate">{d.decision}</span>
        <ConfidenceBar pct={d.confidence_pct} />
        {d.was_failsafe && <span className="text-xs text-yellow-400">⚠ failsafe</span>}
      </button>
      {open && (
        <div className="mt-2 ml-6 space-y-1 text-xs text-gray-400">
          <p><span className="text-gray-500">Reason:</span> {d.reason}</p>
          {d.alternative && <p><span className="text-gray-500">Alt:</span> {d.alternative}</p>}
          {d.expected_result && <p><span className="text-gray-500">Expected:</span> {d.expected_result}</p>}
          <p className="text-gray-600">{d.created_at ? new Date(d.created_at).toLocaleString() : ""}</p>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

const PLATFORMS = ["tiktok", "youtube_create"];
const PRIORITIES = [
  { value: 0, label: "Critical" },
  { value: 1, label: "High" },
  { value: 2, label: "Normal" },
  { value: 3, label: "Low" },
];

export default function AIControlCenterPage() {
  const [goals, setGoals] = useState<AgentGoal[]>([]);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [decisions, setDecisions] = useState<AgentDecision[]>([]);
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [suggestions, setSuggestions] = useState<OptimizationSuggestion[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [events, setEvents] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"overview"|"decisions"|"memory"|"suggestions"|"timeline">("overview");

  // Goal form
  const [goalText, setGoalText] = useState("");
  const [platform, setPlatform] = useState("tiktok");
  const [product, setProduct] = useState("");
  const [count, setCount] = useState(5);
  const [priority, setPriority] = useState(2);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState("");

  const wsRef = useRef<WebSocket | null>(null);

  const notify = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  const load = async () => {
    try {
      const [g, s, d, m, su] = await Promise.all([
        listGoals(), getAgentStatus(), listDecisions(undefined, 30),
        getMemory(), getSuggestions(),
      ]);
      setGoals(g);
      setStatus(s);
      setDecisions(d);
      setMemory(m);
      setSuggestions(su);
    } catch {}
  };

  const loadTimeline = async () => {
    try { setTimeline(await getTimeline(undefined, 60)); } catch {}
  };

  useEffect(() => {
    load();
    const iv = setInterval(load, 15_000);

    const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/agents`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        const line = `[${new Date().toLocaleTimeString()}] ${msg.event}: ${JSON.stringify(msg.data).slice(0, 80)}`;
        setEvents(prev => [line, ...prev].slice(0, 60));
        if (["goal_submitted", "goal_completed", "goal_failed", "task_assigned", "decision_made"].includes(msg.event)) {
          load();
        }
      } catch {}
    };
    return () => { clearInterval(iv); ws.close(); };
  }, []);

  useEffect(() => {
    if (activeTab === "timeline") loadTimeline();
  }, [activeTab]);

  const handleSubmit = async () => {
    if (!goalText.trim()) { notify("Enter a goal"); return; }
    setSubmitting(true);
    try {
      await submitGoal({ goal_text: goalText, platform, product, target_count: count, priority });
      setGoalText(""); setProduct("");
      notify("Goal submitted — planner will begin shortly");
      load();
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleOptimize = async () => {
    try {
      const res = await runOptimization();
      setSuggestions(res);
      notify(`Optimization complete — ${res.length} suggestions`);
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const activeGoals = goals.filter(g => ["PLANNING","RUNNING","PAUSED"].includes(g.status));
  const pastGoals = goals.filter(g => ["COMPLETED","FAILED","CANCELLED"].includes(g.status));

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "decisions", label: `Decisions (${decisions.length})` },
    { id: "memory", label: `Memory (${memory.length})` },
    { id: "suggestions", label: `Suggestions (${suggestions.length})` },
    { id: "timeline", label: "Timeline" },
  ] as const;

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <div className="border-b border-gray-700 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">AI Control Center</h1>
          <p className="text-xs text-gray-400 mt-0.5">Autonomous content production agent</p>
        </div>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          {status && (
            <>
              <span>Active goals: <span className="text-white">{status.active_goals}</span></span>
              <span>Tick: <span className="text-white">#{status.tick_count}</span></span>
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" title="Agent loop running" />
            </>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {toast && <div className="px-4 py-2 bg-indigo-900 border border-indigo-600 rounded text-sm">{toast}</div>}

        {/* Goal Submission */}
        <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Submit Goal</h2>
          <div className="space-y-3">
            <textarea
              value={goalText}
              onChange={e => setGoalText(e.target.value)}
              placeholder='e.g. "Generate 20 TikTok videos for Product X this week"'
              rows={2}
              className="w-full bg-gray-700 text-white text-sm rounded-lg px-4 py-2.5 resize-none placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Platform</label>
                <select value={platform} onChange={e => setPlatform(e.target.value)}
                  className="bg-gray-700 text-white text-sm rounded px-3 py-1.5">
                  {PLATFORMS.map(p => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Product</label>
                <input value={product} onChange={e => setProduct(e.target.value)}
                  placeholder="Product name"
                  className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-40" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Count</label>
                <input type="number" min={1} max={500} value={count} onChange={e => setCount(Number(e.target.value))}
                  className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-20" />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Priority</label>
                <select value={priority} onChange={e => setPriority(Number(e.target.value))}
                  className="bg-gray-700 text-white text-sm rounded px-3 py-1.5">
                  {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div className="flex items-end">
                <button onClick={handleSubmit} disabled={submitting}
                  className="px-5 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium rounded">
                  {submitting ? "Submitting…" : "Submit Goal"}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-700">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id as typeof activeTab)}
              className={`px-4 py-2 text-sm ${activeTab === t.id ? "text-white border-b-2 border-indigo-500" : "text-gray-400 hover:text-white"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab: Overview */}
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-4">
              <h3 className="text-sm text-gray-300 font-semibold">Active Goals ({activeGoals.length})</h3>
              {activeGoals.length === 0 ? (
                <div className="text-gray-500 text-sm py-4 text-center">No active goals. Submit one above.</div>
              ) : (
                activeGoals.map(g => (
                  <GoalCard key={g.id} goal={g}
                    onPause={id => pauseGoal(id).then(load)}
                    onResume={id => resumeGoal(id).then(load)}
                    onCancel={id => cancelGoal(id).then(load)} />
                ))
              )}

              {pastGoals.length > 0 && (
                <>
                  <h3 className="text-sm text-gray-400 font-semibold mt-6">Past Goals ({pastGoals.length})</h3>
                  {pastGoals.slice(0, 5).map(g => (
                    <GoalCard key={g.id} goal={g}
                      onPause={() => {}} onResume={() => {}} onCancel={() => {}} />
                  ))}
                </>
              )}
            </div>

            <div className="space-y-4">
              {/* Agent Status */}
              {status && (
                <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
                  <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3">Agent Status</h3>
                  <div className="space-y-2 text-sm">
                    {[
                      { icon: "📐", name: "Planner", state: status.active_goals > 0 ? "active" : "idle" },
                      { icon: "✍️", name: "Content", state: status.pending_content_tasks > 0 ? `${status.pending_content_tasks} queued` : "idle" },
                      { icon: "⚙️", name: "Execution", state: status.active_goals > 0 ? "monitoring" : "idle" },
                      { icon: "🔄", name: "Recovery", state: status.active_goals > 0 ? "watching" : "idle" },
                      { icon: "📊", name: "Optimization", state: "periodic" },
                    ].map(a => (
                      <div key={a.name} className="flex items-center justify-between">
                        <span className="text-gray-300">{a.icon} {a.name}</span>
                        <span className={`text-xs ${a.state === "idle" ? "text-gray-500" : "text-green-400"}`}>{a.state}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Live Events */}
              <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
                <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-2">Live Events</h3>
                <div className="h-48 overflow-y-auto font-mono text-xs text-gray-400 space-y-0.5">
                  {events.length === 0 ? (
                    <span className="text-gray-600">Waiting for agent events…</span>
                  ) : events.map((e, i) => <div key={i} className="leading-relaxed">{e}</div>)}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab: Decisions */}
        {activeTab === "decisions" && (
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Reasoning History</h2>
            {decisions.length === 0 ? (
              <div className="text-gray-500 text-sm">No decisions recorded yet.</div>
            ) : (
              decisions.map(d => <DecisionRow key={d.id} d={d} />)
            )}
          </div>
        )}

        {/* Tab: Memory */}
        {activeTab === "memory" && (
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Agent Memory</h2>
            {memory.length === 0 ? (
              <div className="text-gray-500 text-sm">No memory entries yet. Memory accumulates as agents learn.</div>
            ) : (
              <div className="space-y-2">
                {memory.map(m => (
                  <div key={m.id} className="flex items-start justify-between gap-4 py-2 border-b border-gray-700">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs px-1.5 py-0.5 bg-gray-700 rounded text-gray-300">{m.category}</span>
                        <span className="text-xs font-mono text-indigo-400 truncate">{m.key}</span>
                      </div>
                      <p className="text-sm text-gray-300">{m.summary}</p>
                      <p className="text-xs text-gray-500 mt-0.5">Used {m.access_count}× · Score {m.relevance_score.toFixed(1)}</p>
                    </div>
                    <button onClick={() => forgetMemory(m.key).then(load)}
                      className="text-xs text-red-500 hover:text-red-400 shrink-0">Forget</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab: Suggestions */}
        {activeTab === "suggestions" && (
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Optimization Suggestions</h2>
              <button onClick={handleOptimize} className="text-xs px-3 py-1.5 bg-indigo-700 hover:bg-indigo-600 rounded text-white">
                Run Analysis
              </button>
            </div>
            {suggestions.length === 0 ? (
              <div className="text-gray-500 text-sm">No suggestions yet. Run an analysis or wait for the periodic optimizer.</div>
            ) : (
              <div className="space-y-3">
                {suggestions.map((s, i) => (
                  <div key={i} className={`border rounded-lg p-3 ${SEVERITY_COLOR[s.severity] || "border-gray-600 bg-gray-800"}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-gray-400">{s.area}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${s.severity === "warning" ? "bg-yellow-800 text-yellow-200" : "bg-blue-800 text-blue-200"}`}>{s.severity}</span>
                    </div>
                    <p className="text-sm text-white">{s.recommendation}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab: Timeline */}
        {activeTab === "timeline" && (
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-4">Execution Timeline</h2>
            {timeline.length === 0 ? (
              <div className="text-gray-500 text-sm">No timeline events yet.</div>
            ) : (
              <div className="space-y-1">
                {timeline.map((e, i) => (
                  <div key={i} className="flex items-start gap-3 py-2 border-b border-gray-700">
                    <span className="text-sm shrink-0">{AGENT_ICON[e.agent] || "📌"}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-white">{e.summary}</p>
                      <p className="text-xs text-gray-500">{e.ts ? new Date(e.ts).toLocaleString() : ""}</p>
                    </div>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${e.type === "decision" ? "bg-purple-900 text-purple-200" : "bg-gray-700 text-gray-300"}`}>{e.type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
