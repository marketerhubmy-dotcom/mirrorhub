const BASE = '/api/v1/apps/tiktok'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

function json(body: unknown, method = 'POST'): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export interface TikTokProduct {
  id: string
  name: string
  search_term: string
  sku: string
  notes: string
}

export interface TikTokExecuteRequest {
  device_id: string
  video_path: string
  caption?: string
  hashtags?: string[]
  first_comment?: string
  product_id?: string
  post_type?: 'post_now' | 'draft'
  variables?: Record<string, string>
  content_job_id?: number
  workflow_id?: number
}

export interface TikTokSimulateRequest {
  video_path: string
  caption?: string
  hashtags?: string[]
  first_comment?: string
  product_id?: string
  post_type?: 'post_now' | 'draft'
  variables?: Record<string, string>
  workflow_id?: number
}

export interface TikTokSimulateResult {
  status: string
  reason: string
  total_steps: number
  steps: Array<{ type: string; label: string }>
}

export interface TikTokConfig {
  timeouts: Record<string, number>
  retry: Record<string, number>
  publish: Record<string, unknown>
  caption: Record<string, unknown>
}

export interface TikTokPhases {
  phases: string[]
  transitions: Array<{ from: string; to: string }>
}

export const tiktokApi = {
  // ── Plugin actions ──────────────────────────────────────────────────────────
  execute: (req: TikTokExecuteRequest): Promise<{
    status: string; reason: string; job_id: number; total_steps: number
  }> => request('', json(req)),

  simulate: (req: TikTokSimulateRequest): Promise<TikTokSimulateResult> =>
    request('/simulate', json(req)),

  validate: (req: { video_path: string; caption?: string; hashtags?: string[]; product_id?: string }): Promise<{
    success: boolean; code: string; reason: string
  }> => request('/validate', json(req)),

  config: (): Promise<TikTokConfig> =>
    request('/config'),

  phases: (): Promise<TikTokPhases> =>
    request('/phases'),

  // ── Product Manager ─────────────────────────────────────────────────────────
  listProducts: (): Promise<{ products: TikTokProduct[] }> =>
    request('/products'),

  addProduct: (p: Omit<TikTokProduct, 'notes'> & { notes?: string }): Promise<TikTokProduct> =>
    request('/products', json(p)),

  updateProduct: (id: string, fields: Partial<TikTokProduct>): Promise<TikTokProduct> =>
    request(`/products/${id}`, json(fields, 'PUT')),

  deleteProduct: (id: string): Promise<{ deleted: string }> =>
    request(`/products/${id}`, { method: 'DELETE' }),
}
