export type ExecutionStatus =
  | 'WAITING'
  | 'STARTING'
  | 'RUNNING'
  | 'EXPORTING'
  | 'READY_FOR_REVIEW'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export interface StepInfo {
  index: number
  label: string
  type: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'
  screenshot: string | null
  error: string | null
}

export interface LogEntry {
  ts: string
  level: string
  message: string
}

export interface ExecutionStateResponse {
  job_id: number
  device_id: string
  status: ExecutionStatus
  current_index: number
  progress: number
  last_screenshot: string | null
  current_screen: string
  error: string | null
  current_step: { index: number; label: string; type: string; status: string } | null
  next_step: { label: string } | null
  previous_step: { index: number; label: string; type: string; status: string } | null
  steps: StepInfo[]
  logs: LogEntry[]
}

export interface ExecutionJob {
  id: number
  content_job_id: number | null
  device_id: string
  adb_address: string
  platform: string
  post_type: string
  schedule_time: string | null
  video_prompt: string
  image_path: string
  status: ExecutionStatus
  current_step: string | null
  progress: number
  error: string | null
  logs: LogEntry[]
  last_screenshot: string | null
  created_at: string | null
  updated_at: string | null
}

export interface StartExecutionRequest {
  device_id: string
  content_job_id?: number
  video_prompt: string
  image_path: string
  platform?: string
  post_type?: string
  schedule_time?: string | null
}

export const STATUS_LABEL: Record<ExecutionStatus, string> = {
  WAITING: 'Waiting',
  STARTING: 'Starting',
  RUNNING: 'Running',
  EXPORTING: 'Exporting',
  READY_FOR_REVIEW: 'Ready for Review',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
}

export const STATUS_COLOR: Record<ExecutionStatus, string> = {
  WAITING: 'bg-gray-100 text-gray-600',
  STARTING: 'bg-blue-100 text-blue-700',
  RUNNING: 'bg-amber-100 text-amber-700',
  EXPORTING: 'bg-violet-100 text-violet-700',
  READY_FOR_REVIEW: 'bg-yellow-100 text-yellow-800',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-red-100 text-red-600',
  CANCELLED: 'bg-gray-100 text-gray-500',
}

export const STEP_STATUS_COLOR: Record<string, string> = {
  pending: 'bg-gray-200 text-gray-500',
  running: 'bg-amber-400 text-white',
  success: 'bg-emerald-500 text-white',
  failed: 'bg-red-500 text-white',
  skipped: 'bg-gray-300 text-gray-600',
}
