const BASE = "/api/v1/orchestrator";

export interface DeviceCapabilities {
  resolution: string;
  android_version: string;
  ram_mb: number;
  storage_gb: number;
  installed_apps: string[];
  supported_plugins: string[];
}

export interface DeviceHealth {
  performance_score: number;
  latency_ms: number;
  last_health_check: string | null;
}

export interface DeviceStats {
  total_jobs_completed: number;
  total_jobs_failed: number;
  success_rate: number;
  last_job_completed_at: string | null;
}

export interface DeviceProfile {
  device_id: string;
  status: string;
  priority: number;
  group_id: number | null;
  notes: string;
  capabilities: DeviceCapabilities;
  health: DeviceHealth;
  stats: DeviceStats;
  created_at: string | null;
  updated_at: string | null;
}

export interface FleetStatus {
  total: number;
  online: number;
  idle: number;
  busy: number;
  maintenance: number;
  offline: number;
  devices: DeviceProfile[];
}

export interface DeviceGroup {
  id: number;
  name: string;
  description: string;
  default_plugin: string | null;
  default_strategy: string;
  created_at: string | null;
}

export interface GroupMember {
  id: number;
  group_id: number;
  device_id: string;
  added_at: string | null;
}

export interface Assignment {
  id: number;
  campaign_job_id: number;
  device_id: string;
  strategy: string;
  reason: string;
  status: string;
  migrated_to: string | null;
  assigned_at: string | null;
  completed_at: string | null;
}

export interface DistributeResult {
  campaign_id: number;
  distribution: Record<string, number>;
}

export interface MigrateResult {
  moved: number;
  from: string;
  to: string;
}

export interface RebalanceResult {
  rebalanced: number;
  distribution: Record<string, number>;
}

async function req<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Fleet ────────────────────────────────────────────────────────────────────

export const getFleet = () => req<FleetStatus>("/fleet");
export const getFleetStats = () => req<Record<string, unknown>>("/fleet/stats");

// ── Devices ───────────────────────────────────────────────────────────────────

export const listDevices = () => req<DeviceProfile[]>("/devices");
export const getDevice = (id: string) => req<DeviceProfile>(`/devices/${id}`);
export const patchDevice = (id: string, data: Partial<DeviceProfile>) =>
  req<DeviceProfile>(`/devices/${id}`, { method: "PATCH", body: JSON.stringify(data) });
export const getDeviceStats = (id: string) =>
  req<Record<string, unknown>>(`/devices/${id}/stats`);
export const getDeviceAssignments = (id: string, limit = 50) =>
  req<Assignment[]>(`/devices/${id}/assignments?limit=${limit}`);

// ── Maintenance / reservation ─────────────────────────────────────────────────

export const setMaintenance = (id: string, reason = "") =>
  req<DeviceProfile>(`/devices/${id}/maintenance`, {
    method: "POST",
    body: JSON.stringify({ device_id: id, reason }),
  });
export const releaseDevice = (id: string) =>
  req<DeviceProfile>(`/devices/${id}/release`, { method: "POST" });
export const reserveDevice = (id: string, reason = "") =>
  req<DeviceProfile>(`/devices/${id}/reserve`, {
    method: "POST",
    body: JSON.stringify({ device_id: id, reason }),
  });

// ── Groups ────────────────────────────────────────────────────────────────────

export const listGroups = () => req<DeviceGroup[]>("/groups");
export const createGroup = (data: {
  name: string;
  description?: string;
  default_plugin?: string;
  default_strategy?: string;
}) => req<DeviceGroup>("/groups", { method: "POST", body: JSON.stringify(data) });
export const getGroup = (id: number) => req<DeviceGroup>(`/groups/${id}`);
export const updateGroup = (id: number, data: Partial<DeviceGroup>) =>
  req<DeviceGroup>(`/groups/${id}`, { method: "PATCH", body: JSON.stringify(data) });
export const deleteGroup = (id: number) =>
  req<void>(`/groups/${id}`, { method: "DELETE" });
export const getGroupMembers = (id: number) =>
  req<GroupMember[]>(`/groups/${id}/members`);
export const addGroupMember = (groupId: number, deviceId: string) =>
  req<GroupMember>(`/groups/${groupId}/members`, {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId }),
  });
export const removeGroupMember = (groupId: number, deviceId: string) =>
  req<void>(`/groups/${groupId}/members/${deviceId}`, { method: "DELETE" });

// ── Distribution ──────────────────────────────────────────────────────────────

export const distributeCampaign = (
  campaignId: number,
  strategy = "least_busy",
  groupId?: number,
  pluginFilter?: string
) =>
  req<DistributeResult>(`/campaigns/${campaignId}/distribute`, {
    method: "POST",
    body: JSON.stringify({ strategy, group_id: groupId, plugin_filter: pluginFilter }),
  });

export const rebalanceJobs = (campaignId?: number, strategy = "least_busy") =>
  req<RebalanceResult>("/rebalance", {
    method: "POST",
    body: JSON.stringify({ campaign_id: campaignId, strategy }),
  });

export const migrateJobs = (
  fromDeviceId: string,
  toDeviceId: string,
  jobStatuses?: string[]
) =>
  req<MigrateResult>("/migrate", {
    method: "POST",
    body: JSON.stringify({
      from_device_id: fromDeviceId,
      to_device_id: toDeviceId,
      job_statuses: jobStatuses,
    }),
  });
