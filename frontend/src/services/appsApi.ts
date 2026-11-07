const BASE = '/api/v1/apps/youtube_create'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

function json(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export interface YTCExecuteRequest {
  device_id: string
  video_prompt: string
  image_path?: string
  image_paths?: string[]
  post_type?: string
  schedule_time?: string | null
  content_job_id?: number | null
  resolution?: string
  generation_timeout?: number
}

export interface YTCSimulateRequest {
  video_prompt: string
  image_path?: string
  image_paths?: string[]
  post_type?: string
  schedule_time?: string | null
  resolution?: string
  generation_timeout?: number
}

export interface YTCValidateRequest {
  video_prompt?: string
  image_path?: string
  image_paths?: string[]
}

export interface YTCSimulateResult {
  status: string
  reason: string
  total_steps: number
  steps: { type: string; label: string }[]
}

export interface YTCPluginConfig {
  timeouts: { launch: number; generation: number; export: number; share: number }
  retry: { max: number; poll_interval: number }
  media: { preferred_resolution: string; preferred_duration: string; preferred_style: string; max_images: number }
}

export interface YTCPhases {
  phases: string[]
  transitions: { from: string; to: string }[]
}

export const ytcPluginApi = {
  execute: (req: YTCExecuteRequest): Promise<{ status: string; reason: string; job_id: number; total_steps: number }> =>
    request('/execute', json(req)),

  simulate: (req: YTCSimulateRequest): Promise<YTCSimulateResult> =>
    request('/simulate', json(req)),

  validate: (req: YTCValidateRequest): Promise<{ success: boolean; code: string; reason: string }> =>
    request('/validate', json(req)),

  config: (): Promise<YTCPluginConfig> =>
    request('/config'),

  phases: (): Promise<YTCPhases> =>
    request('/phases'),
}
