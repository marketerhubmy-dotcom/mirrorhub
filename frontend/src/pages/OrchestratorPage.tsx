import { useEffect, useState } from "react";
import {
  getFleet,
  listGroups,
  createGroup,
  deleteGroup,
  rebalanceJobs,
  migrateJobs,
  distributeCampaign,
  type DeviceGroup,
  type DeviceProfile,
} from "../services/orchestratorApi";

const STRATEGIES = ["least_busy", "round_robin", "fastest", "priority_device", "manual"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 mb-5">
      <h2 className="text-sm font-semibold text-gray-300 mb-4 uppercase tracking-wider">{title}</h2>
      {children}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    IDLE: "bg-green-900 text-green-300",
    BUSY: "bg-blue-900 text-blue-300",
    MAINTENANCE: "bg-yellow-900 text-yellow-300",
    OFFLINE: "bg-gray-700 text-gray-400",
    DISCONNECTED: "bg-red-900 text-red-300",
    RECOVERING: "bg-orange-900 text-orange-300",
    ONLINE: "bg-teal-900 text-teal-300",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[status] || "bg-gray-700 text-gray-300"}`}>
      {status}
    </span>
  );
}

export default function OrchestratorPage() {
  const [devices, setDevices] = useState<DeviceProfile[]>([]);
  const [groups, setGroups] = useState<DeviceGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");

  // Rebalance form
  const [rebalStrategy, setRebalStrategy] = useState("least_busy");
  const [rebalCampaignId, setRebalCampaignId] = useState("");

  // Migrate form
  const [migrateFrom, setMigrateFrom] = useState("");
  const [migrateTo, setMigrateTo] = useState("");

  // Distribute form
  const [distCampaignId, setDistCampaignId] = useState("");
  const [distStrategy, setDistStrategy] = useState("least_busy");

  // Group form
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupPlugin, setNewGroupPlugin] = useState("");

  const notify = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const load = async () => {
    try {
      const [f, g] = await Promise.all([getFleet(), listGroups()]);
      setDevices(f.devices);
      setGroups(g);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleRebalance = async () => {
    try {
      const res = await rebalanceJobs(rebalCampaignId ? Number(rebalCampaignId) : undefined, rebalStrategy);
      notify(`Rebalanced ${res.rebalanced} jobs`);
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleMigrate = async () => {
    if (!migrateFrom || !migrateTo) { notify("Fill both device IDs"); return; }
    try {
      const res = await migrateJobs(migrateFrom, migrateTo);
      notify(`Moved ${res.moved} jobs`);
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleDistribute = async () => {
    if (!distCampaignId) { notify("Enter campaign ID"); return; }
    try {
      const res = await distributeCampaign(Number(distCampaignId), distStrategy);
      const summary = Object.entries(res.distribution).map(([d, n]) => `${d.slice(0, 8)}: ${n}`).join(", ");
      notify(`Distributed — ${summary || "no jobs"}`);
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleCreateGroup = async () => {
    if (!newGroupName) { notify("Enter group name"); return; }
    try {
      await createGroup({ name: newGroupName, default_plugin: newGroupPlugin || undefined });
      setNewGroupName("");
      setNewGroupPlugin("");
      load();
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleDeleteGroup = async (id: number) => {
    try {
      await deleteGroup(id);
      load();
    } catch (e: unknown) {
      notify(`Error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold mb-1">Orchestrator</h1>
        <p className="text-gray-400 text-sm mb-6">Fleet management, job distribution & device groups</p>

        {toast && (
          <div className="mb-4 px-4 py-2 bg-indigo-800 border border-indigo-600 rounded text-sm">
            {toast}
          </div>
        )}

        {/* Fleet overview */}
        <Section title="Fleet Overview">
          {loading ? (
            <div className="text-gray-400 text-sm">Loading…</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-400 border-b border-gray-700">
                    <th className="pb-2 pr-4">Device ID</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Score</th>
                    <th className="pb-2 pr-4">Latency</th>
                    <th className="pb-2 pr-4">Completed</th>
                    <th className="pb-2">Success %</th>
                  </tr>
                </thead>
                <tbody>
                  {devices.map((d) => (
                    <tr key={d.device_id} className="border-b border-gray-800 hover:bg-gray-750">
                      <td className="py-2 pr-4 font-mono text-xs">{d.device_id.slice(0, 12)}…</td>
                      <td className="py-2 pr-4"><StatusBadge status={d.status} /></td>
                      <td className="py-2 pr-4">{d.health.performance_score.toFixed(1)}</td>
                      <td className="py-2 pr-4">{d.health.latency_ms.toFixed(0)} ms</td>
                      <td className="py-2 pr-4">{d.stats.total_jobs_completed}</td>
                      <td className="py-2">{d.stats.success_rate}%</td>
                    </tr>
                  ))}
                  {devices.length === 0 && (
                    <tr><td colSpan={6} className="py-4 text-gray-500 text-center">No devices</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        {/* Distribute */}
        <Section title="Distribute Campaign Jobs">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Campaign ID</label>
              <input
                type="number"
                value={distCampaignId}
                onChange={(e) => setDistCampaignId(e.target.value)}
                placeholder="123"
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-28"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Strategy</label>
              <select
                value={distStrategy}
                onChange={(e) => setDistStrategy(e.target.value)}
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5"
              >
                {STRATEGIES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <button
              onClick={handleDistribute}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded"
            >
              Distribute
            </button>
          </div>
        </Section>

        {/* Rebalance */}
        <Section title="Rebalance Queue">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Campaign ID (optional)</label>
              <input
                type="number"
                value={rebalCampaignId}
                onChange={(e) => setRebalCampaignId(e.target.value)}
                placeholder="all"
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-28"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Strategy</label>
              <select
                value={rebalStrategy}
                onChange={(e) => setRebalStrategy(e.target.value)}
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5"
              >
                {STRATEGIES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <button
              onClick={handleRebalance}
              className="px-4 py-1.5 bg-yellow-700 hover:bg-yellow-600 text-white text-sm rounded"
            >
              Rebalance
            </button>
          </div>
        </Section>

        {/* Migrate */}
        <Section title="Migrate Jobs Between Devices">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="text-xs text-gray-400 block mb-1">From Device ID</label>
              <input
                value={migrateFrom}
                onChange={(e) => setMigrateFrom(e.target.value)}
                placeholder="device-uuid"
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-48"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">To Device ID</label>
              <input
                value={migrateTo}
                onChange={(e) => setMigrateTo(e.target.value)}
                placeholder="device-uuid"
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-48"
              />
            </div>
            <button
              onClick={handleMigrate}
              className="px-4 py-1.5 bg-red-700 hover:bg-red-600 text-white text-sm rounded"
            >
              Migrate
            </button>
          </div>
        </Section>

        {/* Device Groups */}
        <Section title="Device Groups">
          <div className="flex flex-wrap gap-3 items-end mb-4">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Group name</label>
              <input
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                placeholder="YouTube Devices"
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5 w-40"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Default plugin</label>
              <select
                value={newGroupPlugin}
                onChange={(e) => setNewGroupPlugin(e.target.value)}
                className="bg-gray-700 text-white text-sm rounded px-3 py-1.5"
              >
                <option value="">—</option>
                <option value="youtube_create">youtube_create</option>
                <option value="tiktok">tiktok</option>
              </select>
            </div>
            <button
              onClick={handleCreateGroup}
              className="px-4 py-1.5 bg-green-700 hover:bg-green-600 text-white text-sm rounded"
            >
              Create Group
            </button>
          </div>

          {groups.length === 0 ? (
            <div className="text-gray-500 text-sm">No groups yet</div>
          ) : (
            <div className="space-y-2">
              {groups.map((g) => (
                <div key={g.id} className="flex items-center justify-between bg-gray-700 rounded px-3 py-2">
                  <div>
                    <span className="font-medium text-white text-sm">{g.name}</span>
                    {g.default_plugin && (
                      <span className="ml-2 text-xs text-gray-400">{g.default_plugin}</span>
                    )}
                  </div>
                  <button
                    onClick={() => handleDeleteGroup(g.id)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
