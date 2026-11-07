import type {
  Workflow, WorkflowStep, WorkflowVersion, WorkflowExecution,
  RecordingSession, StepTypeInfo,
} from '../types/workflow'

const BASE = '/api/v1/workflows'

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

export const workflowApi = {
  // ── Workflows ──────────────────────────────────────────────────────────────
  list: (): Promise<Workflow[]> =>
    request(''),

  get: (id: number): Promise<Workflow & { steps: WorkflowStep[] }> =>
    request(`/${id}`),

  create: (data: { name: string; description?: string; application?: string; variables?: string[] }): Promise<Workflow> =>
    request('', json(data)),

  update: (id: number, data: Partial<Workflow>): Promise<Workflow> =>
    request(`/${id}`, json(data, 'PUT')),

  remove: (id: number): Promise<{ deleted: number }> =>
    request(`/${id}`, { method: 'DELETE' }),

  // ── Steps ──────────────────────────────────────────────────────────────────
  getSteps: (workflowId: number): Promise<WorkflowStep[]> =>
    request(`/${workflowId}/steps`),

  addStep: (workflowId: number, step: {
    step_type: string; label?: string; parameters?: Record<string, unknown>
    conditions?: Record<string, unknown>; retry_max?: number; timeout?: number
    enabled?: boolean; screen_name?: string; order?: number
  }): Promise<WorkflowStep> =>
    request(`/${workflowId}/steps`, json(step)),

  updateStep: (workflowId: number, stepId: number, data: Partial<WorkflowStep>): Promise<WorkflowStep> =>
    request(`/${workflowId}/steps/${stepId}`, json(data, 'PUT')),

  deleteStep: (workflowId: number, stepId: number): Promise<{ deleted: number }> =>
    request(`/${workflowId}/steps/${stepId}`, { method: 'DELETE' }),

  duplicateStep: (workflowId: number, stepId: number): Promise<WorkflowStep> =>
    request(`/${workflowId}/steps/${stepId}/duplicate`, { method: 'POST' }),

  moveStepUp: (workflowId: number, stepId: number): Promise<WorkflowStep[]> =>
    request(`/${workflowId}/steps/${stepId}/move_up`, { method: 'POST' }),

  moveStepDown: (workflowId: number, stepId: number): Promise<WorkflowStep[]> =>
    request(`/${workflowId}/steps/${stepId}/move_down`, { method: 'POST' }),

  reorderSteps: (workflowId: number, stepIds: number[]): Promise<WorkflowStep[]> =>
    request(`/${workflowId}/steps/reorder`, json({ step_ids: stepIds })),

  // ── Versions ───────────────────────────────────────────────────────────────
  listVersions: (workflowId: number): Promise<WorkflowVersion[]> =>
    request(`/${workflowId}/versions`),

  saveVersion: (workflowId: number, notes?: string): Promise<WorkflowVersion> =>
    request(`/${workflowId}/versions`, json({ notes })),

  rollback: (workflowId: number, version: number): Promise<{ rolled_back_to: number }> =>
    request(`/${workflowId}/versions/${version}/rollback`, { method: 'POST' }),

  validate: (workflowId: number): Promise<{ valid: boolean; errors: string[]; warnings: string[] }> =>
    request(`/${workflowId}/validate`, { method: 'POST' }),

  // ── Import / Export ────────────────────────────────────────────────────────
  exportUrl: (workflowId: number): string =>
    `${BASE}/${workflowId}/export`,

  importWorkflow: (workflowJson: Record<string, unknown>): Promise<Workflow> =>
    request('/import', json({ workflow_json: workflowJson })),

  // ── Player ─────────────────────────────────────────────────────────────────
  play: (workflowId: number, deviceId: string, variables?: Record<string, string>, simulate?: boolean): Promise<{
    execution_id: number; workflow_id: number; status: string; simulate: boolean; total_steps: number
  }> =>
    request(`/${workflowId}/play`, json({ device_id: deviceId, variables: variables ?? {}, simulate: simulate ?? false })),

  listExecutions: (): Promise<WorkflowExecution[]> =>
    request('/executions/list'),

  getExecution: (id: number): Promise<WorkflowExecution> =>
    request(`/executions/${id}`),

  cancelExecution: (id: number): Promise<{ cancelled: number }> =>
    request(`/executions/${id}/cancel`, { method: 'POST' }),

  // ── Recorder ───────────────────────────────────────────────────────────────
  recorderStart: (deviceId: string, name?: string): Promise<RecordingSession> =>
    request('/recorder/start', json({ device_id: deviceId, name: name ?? 'New Recording' })),

  recorderSessions: (): Promise<RecordingSession[]> =>
    request('/recorder/sessions'),

  recorderGet: (sessionId: string): Promise<RecordingSession> =>
    request(`/recorder/${sessionId}`),

  recorderAddStep: (sessionId: string, step: {
    step_type: string; label?: string; parameters?: Record<string, unknown>
    conditions?: Record<string, unknown>; capture_screen?: boolean
  }): Promise<{ step: WorkflowStep; total_steps: number }> =>
    request(`/recorder/${sessionId}/step`, json(step)),

  recorderRemoveStep: (sessionId: string, index: number): Promise<{ removed: number }> =>
    request(`/recorder/${sessionId}/steps/${index}`, { method: 'DELETE' }),

  recorderStop: (sessionId: string, opts?: {
    name?: string; description?: string; application?: string; save?: boolean
  }): Promise<{ session_id: string; saved: boolean; workflow?: Workflow }> =>
    request(`/recorder/${sessionId}/stop`, json({
      name: opts?.name, description: opts?.description ?? '',
      application: opts?.application ?? 'generic', save: opts?.save ?? true,
    })),

  // ── Meta ───────────────────────────────────────────────────────────────────
  stepTypes: (): Promise<{ step_types: StepTypeInfo[] }> =>
    request('/meta/step_types'),
}
