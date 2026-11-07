import { useEffect, useRef, useState } from "react";
import { getFleet, setMaintenance, releaseDevice, type DeviceProfile } from "../services/orchestratorApi";

const STATUS_COLOR: Record<string, string> = {
  IDLE: "bg-green-500",
  BUSY: "bg-blue-500",
  MAINTENANCE: "bg-yellow-500",
  OFFLINE: "bg-gray-500",
  DISCONNECTED: "bg-red-500",
  RECOVERING: "bg-orange-500",
  PAUSED: "bg-purple-500",
  ONLINE: "bg-teal-500",
};

function ScoreBar({ score }: { score: number }) {
  const pct = (score / 10) * 100;
  const color = score >= 7 ? "bg-green-400" : score >= 4 ? "bg-yellow-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-1">
      <div className="w-16 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400">{score.toFixed(1)}</span>
    </div>
  );
}

function DeviceCard({
  device,
  onMaintenance,
  onRelease,
}: {
  device: DeviceProfile;
  onMaintenance: (id: string) => void;
  onRelease: (id: string) => void;
}) {
  const dotColor = STATUS_COLOR[device.status] || "bg-gray-500";
  const isMaintenance = device.status === "MAINTENANCE";
  const isOffline = device.status === "OFFLINE" || device.status === "DISCONNECTED";

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${dotColor}`} />
          <span className="font-mono text-sm text-white truncate max-w-[140px]" title={device.device_id}>
            {device.device_id.slice(0, 8)}…
          </span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${dotColor} bg-opacity-20 text-white`}>
          {device.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-y-1 text-xs text-gray-400">
        <span>Score</span>
        <ScoreBar score={device.health.performance_score} />
        <span>Latency</span>
        <span className="text-white">{device.health.latency_ms.toFixed(0)} ms</span>
        <span>Android</span>
        <span className="text-white">{device.capabilities.android_version || "—"}</span>
        <span>RAM</span>
        <span className="text-white">{device.capabilities.ram_mb ? `${device.capabilities.ram_mb} MB` : "—"}</span>
        <span>Jobs done</span>
        <span className="text-white">{device.stats.total_jobs_completed}</span>
        <span>Success rate</span>
        <span className="text-white">{device.stats.success_rate}%</span>
      </div>

      <div className="flex gap-2 mt-auto">
        {!isMaintenance && !isOffline && (
          <button
            onClick={() => onMaintenance(device.device_id)}
            className="flex-1 text-xs py-1 rounded bg-yellow-700 hover:bg-yellow-600 text-white"
          >
            Maintenance
          </button>
        )}
        {isMaintenance && (
          <button
            onClick={() => onRelease(device.device_id)}
            className="flex-1 text-xs py-1 rounded bg-green-700 hover:bg-green-600 text-white"
          >
            Release
          </button>
        )}
      </div>
    </div>
  );
}

export default function DeviceWallPage() {
  const [fleet, setFleet] = useState<DeviceProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState<string[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const load = async () => {
    try {
      const data = await getFleet();
      setFleet(data.devices);
    } catch {
      // keep stale data
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const iv = setInterval(load, 30_000);

    const wsUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/orchestrator/fleet`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        setEvents((prev) => [`[${new Date().toLocaleTimeString()}] ${msg.event}: ${JSON.stringify(msg.data)}`, ...prev].slice(0, 50));
        // Refresh fleet on any device event
        if (["device_connected", "device_lost", "failover"].includes(msg.event)) {
          load();
        }
      } catch {}
    };

    return () => {
      clearInterval(iv);
      ws.close();
    };
  }, []);

  const handleMaintenance = async (id: string) => {
    await setMaintenance(id);
    load();
  };

  const handleRelease = async (id: string) => {
    await releaseDevice(id);
    load();
  };

  const statusCounts = fleet.reduce<Record<string, number>>((acc, d) => {
    acc[d.status] = (acc[d.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-1">Device Wall</h1>
        <p className="text-gray-400 text-sm mb-6">Live fleet status — refreshes every 30s</p>

        {/* Summary badges */}
        <div className="flex flex-wrap gap-3 mb-6">
          {Object.entries(statusCounts).map(([status, count]) => (
            <span
              key={status}
              className={`text-xs px-3 py-1 rounded-full ${STATUS_COLOR[status] || "bg-gray-600"} bg-opacity-30 border border-white/10`}
            >
              {status} · {count}
            </span>
          ))}
          <span className="text-xs px-3 py-1 rounded-full bg-gray-700 border border-white/10">
            Total · {fleet.length}
          </span>
        </div>

        {loading ? (
          <div className="text-gray-400">Loading fleet…</div>
        ) : fleet.length === 0 ? (
          <div className="text-gray-400">No devices registered. Connect a device first.</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 mb-8">
            {fleet.map((d) => (
              <DeviceCard
                key={d.device_id}
                device={d}
                onMaintenance={handleMaintenance}
                onRelease={handleRelease}
              />
            ))}
          </div>
        )}

        {/* Live event log */}
        <div>
          <h2 className="text-sm font-semibold text-gray-300 mb-2">Live Events</h2>
          <div className="bg-gray-800 rounded-lg p-3 h-40 overflow-y-auto font-mono text-xs text-gray-400 space-y-1">
            {events.length === 0 ? (
              <span className="text-gray-600">Waiting for events…</span>
            ) : (
              events.map((e, i) => <div key={i}>{e}</div>)
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
