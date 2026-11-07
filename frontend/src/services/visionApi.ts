import type { ScreenAnalysis, WaitRequest } from '../types/vision'

const BASE = '/api/v1/vision'

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

export const visionApi = {
  analyze: (deviceId: string, provider = 'uiautomator'): Promise<ScreenAnalysis> =>
    request(`/${deviceId}/analyze?provider=${provider}`, { method: 'POST' }),

  screenshot: (deviceId: string): Promise<{ web_path: string; width: number; height: number; timestamp: string }> =>
    request(`/${deviceId}/screenshot`),

  state: (deviceId: string): Promise<ScreenAnalysis> =>
    request(`/${deviceId}/state`),

  history: (deviceId: string, n = 20): Promise<ScreenAnalysis[]> =>
    request(`/${deviceId}/history?n=${n}`),

  wait: (deviceId: string, req: WaitRequest): Promise<ScreenAnalysis> =>
    request(`/${deviceId}/wait`, json(req)),

  ocr: (deviceId: string): Promise<{ visible_text: string[]; buttons: unknown[]; editable_fields: string[]; dialogs: string[] }> =>
    request(`/${deviceId}/ocr`, { method: 'POST' }),

  clearCache: (deviceId: string): Promise<{ cleared: string }> =>
    request(`/${deviceId}/cache`, { method: 'DELETE' }),

  providers: (): Promise<{ providers: string[] }> =>
    request('/providers'),
}
