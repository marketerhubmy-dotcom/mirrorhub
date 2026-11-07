import type {
  SavedProduct,
  ProductFetchResult,
  ProductDraft,
  ProductSaveRequest,
  ProductRefreshResult,
  ProductConflict,
} from '../types/product'

interface CheckDuplicateResult {
  exists: boolean
  matched_by: string
  product: SavedProduct | null
}

const BASE = '/api/v1/products'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    const msg =
      typeof detail === 'string' ? detail
      : typeof detail?.message === 'string' ? detail.message
      : res.statusText
    throw new Error(msg)
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

export const productApi = {
  list: (): Promise<SavedProduct[]> =>
    request(''),

  get: (id: number): Promise<SavedProduct> =>
    request(`/${id}`),

  // Scrape a TikTok Shop URL + AI analysis
  fetch: (url: string, manualText = ''): Promise<ProductFetchResult> =>
    request('/fetch', json({ url, manual_text: manualText })),

  // AI analysis from pasted text — returns ProductDraft directly
  analyzeText: (text: string, productUrl = ''): Promise<ProductDraft> =>
    request('/analyze-text', json({ text, product_url: productUrl })),

  // AI vision analysis from screenshots — returns ProductDraft directly
  analyzeImages: (
    files: File[],
    productUrl = '',
    notes = '',
  ): Promise<ProductDraft> => {
    const fd = new FormData()
    files.forEach(f => fd.append('images', f))
    fd.append('product_url', productUrl)
    fd.append('notes', notes)
    return request('/analyze-images', { method: 'POST', body: fd })
  },

  search: (q: string): Promise<SavedProduct[]> =>
    request(`/search?q=${encodeURIComponent(q)}`),

  checkDuplicate: (params: { url?: string; product_id?: string; name?: string; shop_name?: string }): Promise<CheckDuplicateResult> =>
    request('/check-duplicate', json(params)),

  save: (data: ProductSaveRequest): Promise<SavedProduct> =>
    request('', json(data)),

  saveOrConflict: async (
    data: ProductSaveRequest,
  ): Promise<{ ok: true; product: SavedProduct } | { ok: false; conflict: ProductConflict }> => {
    const res = await fetch(BASE, json(data))
    if (res.ok) return { ok: true, product: (await res.json()) as SavedProduct }
    if (res.status === 409) {
      const body = await res.json()
      return { ok: false, conflict: body.detail as ProductConflict }
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    const msg =
      typeof detail === 'string' ? detail
      : typeof detail?.message === 'string' ? detail.message
      : res.statusText
    throw new Error(msg)
  },

  update: (id: number, data: Partial<ProductSaveRequest>): Promise<SavedProduct> =>
    request(`/${id}`, json(data, 'PATCH')),

  delete: (id: number): Promise<void> =>
    fetch(`${BASE}/${id}`, { method: 'DELETE' }).then(() => undefined),

  refresh: (id: number): Promise<ProductRefreshResult> =>
    request(`/${id}/refresh`, { method: 'POST' }),
}
