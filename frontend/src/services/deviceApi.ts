import type { Device } from '../types'

const BASE = '/api/v1'

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch { /* non-JSON error body */ }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  const ct = res.headers.get('content-type') ?? ''
  return (ct.includes('json') ? res.json() : res.blob()) as Promise<T>
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

// ── types ─────────────────────────────────────────────────────────────────────
export interface AdbLiveDevice {
  serial: string
  state: string
  transport: 'usb' | 'wifi' | 'emulator'
  model: string
  registered: boolean
  device_id: string | null
  name: string
}
export interface PairingStatus {
  adb_version: string
  adb_ok: boolean
  adb_error: string
  devices: AdbLiveDevice[]
}
export interface MdnsService { name: string; kind: 'pairing' | 'connect'; address: string }
export interface ActionResult { ok: boolean; message: string }
export interface ApkInfo { name: string; size: number; modified: number }
export interface InstallResult { device_id: string; name?: string; ok: boolean; message: string }
export interface RemoteEntry { name: string; is_dir: boolean; size: number; modified: string; perms: string; link_to: string }
export interface DirListing { path: string; parent: string | null; entries: RemoteEntry[] }
export interface DiagCheck { id: string; title: string; status: 'PASS' | 'WARN' | 'FAIL' | 'INFO'; detail: string; hint: string }
export interface BackupInfo { name: string; size: number; created: string }

// ── pairing ───────────────────────────────────────────────────────────────────
export const pairingApi = {
  status: () => request<PairingStatus>('/pairing/status'),
  refresh: () => post<unknown>('/pairing/refresh'),
  discover: () => request<{ services: MdnsService[] }>('/pairing/wifi/discover'),
  pair: (address: string, code: string) => post<ActionResult>('/pairing/wifi/pair', { address, code }),
  connect: (address: string) => post<ActionResult>('/pairing/wifi/connect', { address }),
  disconnect: (address: string) => post<ActionResult>('/pairing/wifi/disconnect', { address }),
}

// ── device manager ────────────────────────────────────────────────────────────
export const managerApi = {
  list: () => request<Device[]>('/devices'),
  patch: (id: string, body: Partial<Pick<Device, 'device_name' | 'tags' | 'group_name' | 'notes'>>) =>
    request<Device>(`/devices/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }),
  forget: (id: string) => request<{ ok: boolean }>(`/devices/${id}?confirm=true`, { method: 'DELETE' }),
  refresh: (id: string) => post<Device & { wifi_ip?: string; charging?: boolean; battery_temp_c?: number }>(`/devices/${id}/refresh`),
  reconnect: (id: string) => post<ActionResult>(`/devices/${id}/reconnect`),
  disconnect: (id: string) => post<ActionResult>(`/devices/${id}/disconnect`),
  screenshot: (id: string) => post<Blob>(`/devices/${id}/screenshot`),
  recordStart: (id: string, seconds: number) => post<{ ok: boolean }>(`/devices/${id}/record/start?seconds=${seconds}`),
  recordStop: (id: string) => post<{ ok: boolean; name: string; url: string }>(`/devices/${id}/record/stop`),
}

// ── apps ──────────────────────────────────────────────────────────────────────
export const appsApi = {
  apks: () => request<ApkInfo[]>('/apps/apks'),
  uploadApk: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ name: string; size: number }>('/apps/apks', { method: 'POST', body: fd })
  },
  deleteApk: (name: string) => request<{ ok: boolean }>(`/apps/apks/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  packages: (id: string, thirdParty = true) =>
    request<{ packages: string[]; count: number }>(`/apps/${id}/packages?third_party=${thirdParty}`),
  install: (id: string, apk: string, opts: Record<string, boolean> = {}) =>
    post<ActionResult>(`/apps/${id}/install`, { apk, ...opts }),
  installMany: (device_ids: string[], apk: string, opts: Record<string, boolean> = {}) =>
    post<{ results: InstallResult[]; succeeded: number; total: number }>('/apps/install-many', { device_ids, apk, ...opts }),
  uninstall: (id: string, pkg: string, keep_data = false) => post<ActionResult>(`/apps/${id}/uninstall`, { package: pkg, keep_data }),
  launch: (id: string, pkg: string) => post<ActionResult>(`/apps/${id}/launch`, { package: pkg }),
  forceStop: (id: string, pkg: string) => post<ActionResult>(`/apps/${id}/force-stop`, { package: pkg }),
  clearData: (id: string, pkg: string) => post<ActionResult>(`/apps/${id}/clear-data`, { package: pkg }),
}

// ── files ─────────────────────────────────────────────────────────────────────
export const filesApi = {
  list: (id: string, path: string) => request<DirListing>(`/files/${id}/list?path=${encodeURIComponent(path)}`),
  mkdir: (id: string, path: string) => post<{ ok: boolean }>(`/files/${id}/mkdir`, { path }),
  remove: (id: string, path: string) => post<{ ok: boolean }>(`/files/${id}/delete`, { path }),
  rename: (id: string, path: string, new_name: string) => post<{ ok: boolean; path: string }>(`/files/${id}/rename`, { path, new_name }),
  upload: (id: string, dir: string, files: File[]) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    return request<{ results: { name: string; ok: boolean; message?: string }[]; succeeded: number }>(
      `/files/${id}/upload?dir=${encodeURIComponent(dir)}`, { method: 'POST', body: fd })
  },
  downloadUrl: (id: string, path: string) => `${BASE}/files/${id}/download?path=${encodeURIComponent(path)}`,
}

// ── system ────────────────────────────────────────────────────────────────────
export interface Preferences {
  wall_layout: 'auto' | 1 | 2 | 4 | 9
  wall_show_offline: boolean
  wall_quality: 'auto' | 'thumb' | 'normal' | 'focus'
  auto_reconnect: boolean
  record_seconds: number
}
export const prefsApi = {
  get: () => request<Preferences>('/system/preferences'),
  put: (patch: Partial<Preferences>) =>
    request<Preferences>('/system/preferences', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }),
}

export const systemApi2 = {
  diagnostics: () => request<{ overall: string; checks: DiagCheck[] }>('/system/diagnostics'),
  data: () => request<{ data_dir: string; database: string; backups: BackupInfo[] }>('/system/data'),
  backup: () => post<{ ok: boolean; name: string }>('/system/backup'),
  restore: (name: string) => post<{ ok: boolean; message: string }>(`/system/restore/${encodeURIComponent(name)}`),
}

// ── automation core ───────────────────────────────────────────────────────────
export interface AutoStep { type: string; label?: string; retries?: number; retry_delay?: number; timeout?: number; continue_on_error?: boolean; [k: string]: unknown }
export interface AutoDevice { device_id: string; name: string; state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'; step_index: number; steps_done: number; error: string; logs?: { t: string; level: string; msg: string }[] }
export interface AutoRun { id: string; name: string; state: string; created_at: number; total_steps: number; steps: { type: string; label: string }[]; devices: AutoDevice[] }
export const autoApi = {
  validate: (steps: AutoStep[]) => post<{ ok: boolean }>('/auto/validate', { steps }),
  start: (name: string, device_ids: string[], steps: AutoStep[]) => post<AutoRun>('/auto/runs', { name, device_ids, steps }),
  runs: () => request<AutoRun[]>('/auto/runs'),
  run: (id: string) => request<AutoRun>(`/auto/runs/${id}`),
  cancel: (id: string) => post<{ ok: boolean }>(`/auto/runs/${id}/cancel`),
}

// ── performance dashboard ─────────────────────────────────────────────────────
export type Health = 'healthy' | 'degraded' | 'reconnecting' | 'disconnected' | 'authorization_required'
export interface PerfAlert { key: string; scope: string; title: string; severity: 'warning' | 'critical'; active: boolean; since: number; value: unknown; message: string }
export interface PerfOverview {
  generated_at: number; collector_uptime_s: number
  devices: { connected: number; unauthorized: number; disconnected: number; reconnecting: number }
  devices_total: number; active_streams: number
  pc: { cpu_pct: number | null; ram_pct: number | null; ram_used_mb: number | null; ram_total_mb: number | null; cpu_count: number | null }
  process: { cpu_pct: number | null; rss_mb: number | null; threads: number | null; handles: number | null; note: string }
  fps_avg: number | null; fps_note: string | null
  ws: Record<string, number>; ws_total: number
  reconnects: { '5m': number; '15m': number; '1h': number }
  health: { status: 'healthy' | 'degraded'; reason: string; critical_alerts: number }
  alerts: PerfAlert[]
  thresholds: Record<string, number | boolean>
}
export interface PerfPoint {
  t: number; sys_cpu: number | null; sys_ram_pct: number | null; sys_ram_used_mb: number | null; proc_cpu: number | null
  proc_rss_mb: number | null; proc_threads: number | null; proc_handles: number | null; streams: number | null
  fps_avg: number | null; reconnects: number | null; ws: number | null; devices_connected: number | null
}
export interface PerfStream {
  profile: string; state: string; viewers: number; frames: number; bytes: number; dropped_server: number
  fps: number | null; fps_avg: number | null; bitrate_kbps: number | null; width: number | null; height: number | null
  startup_s: number | null; reconnects: number; last_error: string | null; uptime_s: number | null; activity: string
}
export interface PerfDevice {
  device_id: string; name: string; transport: string | null; state: string; online: boolean; health: Health; health_reason: string
  fps: number | null; fps_avg: number | null; resolution: string | null; bitrate_kbps: number | null
  activity: 'active' | 'idle' | 'none' | 'unknown'; frames_sent: number; frames_dropped_server: number
  client: { profile: string; received: number; decoded: number; dropped: number; fps: number | null; age_s: number } | null
  startup_s: number | null; reconnects: number; reconnects_recent: number; last_error: string | null; uptime_s: number | null
  battery: number | null; storage_free_mb: number | null; storage_total_mb: number | null
  streams: PerfStream[]; na: Record<string, string>
}
export interface PerfEvent { id: number; t: number; kind: string; level: string; device_id: string | null; message: string }
export type PerfRange = '5m' | '15m' | '1h' | 'session'
export const perfApi = {
  overview: () => request<PerfOverview>('/perf/overview'),
  history: (range: PerfRange) => request<{ range: string; interval_s: number; points: PerfPoint[] }>(`/perf/history?range=${range}`),
  devices: () => request<PerfDevice[]>('/perf/devices'),
  events: (limit = 100) => request<PerfEvent[]>(`/perf/events?limit=${limit}`),
  alerts: () => request<{ active: PerfAlert[]; history: { t: number; message: string; event: string; severity: string }[] }>('/perf/alerts'),
  thresholds: () => request<Record<string, number | boolean> & { defaults: Record<string, number | boolean> }>('/perf/thresholds'),
  putThresholds: (patch: Record<string, number | boolean>) =>
    request<Record<string, number | boolean>>('/perf/thresholds', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }),
  reportJson: () => request<Record<string, unknown>>('/perf/diagnostics'),
  reportText: async () => (await fetch(`${BASE}/perf/diagnostics.txt`)).text(),
  csvUrl: (kind: 'history' | 'devices' | 'events', range = '1h') => `${BASE}/perf/export.csv?kind=${kind}&range=${range}`,
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  const u = ['KB', 'MB', 'GB', 'TB']
  let v = n / 1024, i = 0
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${u[i]}`
}
