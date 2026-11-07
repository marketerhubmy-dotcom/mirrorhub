import type { ExecutionJob, ExecutionStateResponse, StartExecutionRequest } from '../types/execution'

const BASE = '/api/v1/execution'

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

export const executionApi = {
  list: (): Promise<ExecutionJob[]> =>
    request('/jobs'),

  get: (id: number): Promise<ExecutionStateResponse | ExecutionJob> =>
    request(`/jobs/${id}`),

  start: (req: StartExecutionRequest): Promise<{ status: string; job_id: number; total_steps: number }> =>
    request('/jobs', json(req)),

  pause: (id: number): Promise<{ status: string; job_id: number }> =>
    request(`/jobs/${id}/pause`, { method: 'POST' }),

  resume: (id: number): Promise<{ status: string; job_id: number }> =>
    request(`/jobs/${id}/resume`, { method: 'POST' }),

  cancel: (id: number): Promise<{ status: string; job_id: number }> =>
    request(`/jobs/${id}/cancel`, { method: 'POST' }),

  active: (): Promise<{ active: Record<string, number> }> =>
    request('/active'),
}
