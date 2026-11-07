const BASE = '/api/v1/campaigns'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Campaign {
  id: number
  name: string
  description: string
  status: 'DRAFT' | 'SCHEDULED' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  platform_default: string
  device_id_default: string
  timezone: string
  total_jobs: number
  completed_jobs: number
  failed_jobs: number
  created_at: string
  updated_at: string
}

export interface CampaignJob {
  id: number
  campaign_id: number
  content_job_id: number | null
  platform: string
  device_id: string
  priority: number
  scheduled_time: string | null
  schedule_expr: string | null
  depends_on_job_id: number | null
  retry_max: number
  retry_count: number
  status: string
  job_config_json: string
  execution_job_id: number | null
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface QueueEntry {
  id: number
  campaign_job_id: number
  queue_order: number
  status: string
  started_at: string | null
  finished_at: string | null
  campaign_job?: CampaignJob | null
}

export interface QueueState {
  queue: QueueEntry[]
  counts: Record<string, number>
  paused: boolean
}

export interface CampaignStats {
  total: number
  completed: number
  failed: number
  running: number
  waiting: number
  success_rate: number
  avg_duration_s: number
  retry_count: number
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
}

export interface CampaignCreate {
  name: string
  description?: string
  platform_default?: string
  device_id_default?: string
  timezone?: string
}

export interface CampaignJobCreate {
  campaign_id: number
  platform: string
  device_id: string
  priority?: number
  scheduled_time?: string | null
  schedule_expr?: string | null
  depends_on_job_id?: number | null
  retry_max?: number
  content_job_id?: number | null
  job_config_json?: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText)
    throw new Error(body || res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// ── Campaign CRUD ─────────────────────────────────────────────────────────────

export const campaignApi = {
  list: () => req<Campaign[]>(BASE),

  create: (data: CampaignCreate) =>
    req<Campaign>(BASE, { method: 'POST', body: JSON.stringify(data) }),

  get: (id: number) => req<Campaign>(`${BASE}/${id}`),

  update: (id: number, data: Partial<CampaignCreate>) =>
    req<Campaign>(`${BASE}/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  delete: (id: number) => req<void>(`${BASE}/${id}`, { method: 'DELETE' }),

  start: (id: number, simulate = false) =>
    req<{ status: string; enqueued: number; simulate: boolean }>(
      `${BASE}/${id}/start`,
      { method: 'POST', body: JSON.stringify({ simulate }) },
    ),

  pause: (id: number) =>
    req<{ status: string }>(`${BASE}/${id}/pause`, { method: 'POST', body: '{}' }),

  resume: (id: number) =>
    req<{ status: string }>(`${BASE}/${id}/resume`, { method: 'POST', body: '{}' }),

  cancel: (id: number) =>
    req<{ status: string }>(`${BASE}/${id}/cancel`, { method: 'POST', body: '{}' }),

  listJobs: (id: number) => req<CampaignJob[]>(`${BASE}/${id}/jobs`),

  validate: (id: number) => req<ValidationResult>(`${BASE}/${id}/validate`),

  estimate: (id: number) =>
    req<{ estimated_seconds: number; estimated_finish: string; remaining_jobs: number }>(
      `${BASE}/${id}/estimate`,
    ),

  schedule: (id: number) => req<object[]>(`${BASE}/${id}/schedule`),

  history: (id: number) => req<object[]>(`${BASE}/${id}/history`),

  stats: (id: number) => req<CampaignStats>(`${BASE}/${id}/stats`),

  // ── Campaign Jobs ────────────────────────────────────────────────────────────

  createJob: (data: CampaignJobCreate) =>
    req<CampaignJob>(`${BASE}/jobs`, { method: 'POST', body: JSON.stringify(data) }),

  getJob: (id: number) => req<CampaignJob>(`${BASE}/jobs/${id}`),

  deleteJob: (id: number) => req<void>(`${BASE}/jobs/${id}`, { method: 'DELETE' }),

  pauseJob: (id: number) =>
    req<{ status: string }>(`${BASE}/jobs/${id}/pause`, { method: 'POST', body: '{}' }),

  resumeJob: (id: number) =>
    req<{ status: string }>(`${BASE}/jobs/${id}/resume`, { method: 'POST', body: '{}' }),

  cancelJob: (id: number) =>
    req<{ status: string }>(`${BASE}/jobs/${id}/cancel`, { method: 'POST', body: '{}' }),

  retryJob: (id: number) =>
    req<{ status: string; entry_id: number }>(`${BASE}/jobs/${id}/retry`, {
      method: 'POST',
      body: '{}',
    }),

  simulateJob: (id: number) => req<object>(`${BASE}/jobs/${id}/simulate`, { method: 'POST', body: '{}' }),

  // ── Queue ────────────────────────────────────────────────────────────────────

  queue: () => req<QueueState>(`${BASE}/queue`),

  pauseQueue: () => req<{ status: string }>(`${BASE}/queue/pause`, { method: 'POST', body: '{}' }),

  resumeQueue: () =>
    req<{ status: string }>(`${BASE}/queue/resume`, { method: 'POST', body: '{}' }),

  reorderQueue: (campaign_job_id: number, new_order: number) =>
    req<{ status: string }>(`${BASE}/queue/reorder`, {
      method: 'POST',
      body: JSON.stringify({ campaign_job_id, new_order }),
    }),

  removeFromQueue: (entry_id: number) =>
    req<{ status: string }>(`${BASE}/queue/${entry_id}`, { method: 'DELETE' }),

  // ── Global ───────────────────────────────────────────────────────────────────

  globalHistory: () => req<object[]>(`${BASE}/history`),

  globalStats: () => req<CampaignStats>(`${BASE}/stats`),
}
