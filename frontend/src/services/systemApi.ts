const BASE = '/api/v1/system'

export interface BuildInfo {
  version: string
  release_name: string
  build_date: string
  python_version: string
  platform: string
  architecture: string
  plugins: Record<string, string>
  modules: Record<string, string>
  database: { path: string; exists: boolean; size_bytes: number }
  server_time: string
}

export interface HealthCheck {
  status: string
  checks: Record<string, { ok: boolean; detail: string }>
}

export interface AppSettings {
  app_name: string
  host: string
  port: number
  cors_origins: string
  device_timeout: number
  openai_api_key: string
  openai_model: string
  openai_max_tokens: number
  vision_cache_ttl: number
  vision_poll_interval: number
  vision_default_timeout: number
  campaign_poll_interval: number
  campaign_retry_delay: number
  log_level: string
}

async function req<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(res.statusText)
  return res.json()
}

export const systemApi = {
  about: () => req<BuildInfo>(`${BASE}/about`),
  health: () => req<HealthCheck>(`${BASE}/health`),
  settings: () => req<AppSettings>(`${BASE}/settings`),
}
