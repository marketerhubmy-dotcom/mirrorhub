import type {
  ContentJob,
  ContentJobCreate,
  ContentJobUpdate,
  GenerateRequest,
  WorkflowRequest,
  PipelineRequest,
  PipelineStartResponse,
} from '../types/content'

const BASE = '/api/v1/content'

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

export const contentApi = {
  list: (): Promise<ContentJob[]> =>
    request('/jobs'),

  get: (id: number): Promise<ContentJob> =>
    request(`/jobs/${id}`),

  create: (data: ContentJobCreate): Promise<ContentJob> =>
    request('/jobs', json(data)),

  update: (id: number, data: ContentJobUpdate): Promise<ContentJob> =>
    request(`/jobs/${id}`, { ...json(data), method: 'PATCH' }),

  delete: (id: number): Promise<void> =>
    fetch(`${BASE}/jobs/${id}`, { method: 'DELETE' }).then(() => undefined),

  generate: (id: number, req?: GenerateRequest): Promise<ContentJob> =>
    request(`/jobs/${id}/generate`, json(req ?? {})),

  regenerateField: (
    id: number,
    field: 'brief' | 'video_prompt' | 'cover_hook' | 'caption' | 'hashtags',
    req?: GenerateRequest,
  ): Promise<ContentJob> =>
    request(`/jobs/${id}/regenerate/${field}`, json(req ?? {})),

  uploadImage: (id: number, file: File): Promise<ContentJob> => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/jobs/${id}/images`, { method: 'POST', body: fd })
  },

  removeImage: (id: number, filename: string): Promise<ContentJob> =>
    request(`/jobs/${id}/images/${filename}`, { method: 'DELETE' }),

  run: (id: number, req: WorkflowRequest): Promise<{ status: string; total_steps: number }> =>
    request(`/jobs/${id}/run`, json(req)),

  runPipeline: (id: number, req: PipelineRequest): Promise<PipelineStartResponse> =>
    request(`/jobs/${id}/run_pipeline`, json(req)),

  latestExecution: (id: number): Promise<unknown | null> =>
    fetch(`${BASE}/jobs/${id}/latest_execution`)
      .then(r => (r.ok ? r.json() : null))
      .catch(() => null),
}
