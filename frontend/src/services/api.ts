import type { Device, MirrorStatus } from '../types'

const BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch { /* non-JSON error body */ }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getDevices: () => request<Device[]>('/devices'),
  getDevice: (id: string) => request<Device>(`/devices/${id}`),

  connectAdb: (adb_address: string, device_name?: string) =>
    request<Device>('/mirror/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ adb_address, device_name }),
    }),

  startMirror: (device_id: string) =>
    request<MirrorStatus>(`/mirror/${device_id}/start`, { method: 'POST' }),

  stopMirror: (device_id: string) =>
    request<MirrorStatus>(`/mirror/${device_id}/stop`, { method: 'DELETE' }),

  getMirrorStatus: (device_id: string) =>
    request<MirrorStatus>(`/mirror/${device_id}/status`),
}
