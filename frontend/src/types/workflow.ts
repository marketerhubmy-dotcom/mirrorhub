export interface WorkflowStep {
  id: number
  workflow_id: number
  order: number
  step_type: string
  label: string
  parameters: Record<string, unknown>
  conditions: Record<string, unknown>
  retry_max: number
  timeout: number
  enabled: boolean
  screen_name: string | null
  screenshot_path: string | null
}

export interface Workflow {
  id: number
  name: string
  description: string
  application: string
  current_version: number
  variables: string[]
  step_count?: number
  steps?: WorkflowStep[]
  created_at: string | null
  updated_at: string | null
}

export interface WorkflowVersion {
  id: number
  workflow_id: number
  version: number
  steps: WorkflowStep[]
  variables: string[]
  notes: string | null
  created_at: string | null
}

export interface WorkflowExecution {
  id: number
  workflow_id: number
  workflow_version: number
  device_id: string
  adb_address: string
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  progress: number
  current_step_index: number
  variables: Record<string, string>
  error: string | null
  logs: Array<{ ts: string; level: string; message: string }>
  started_at: string | null
  finished_at: string | null
}

export interface RecordingSession {
  session_id: string
  device_id: string
  name: string
  started_at: string
  step_count: number
  steps: WorkflowStep[]
}

export interface StepTypeInfo {
  type: string
  required_params: string[]
}

export const STEP_TYPE_LABELS: Record<string, string> = {
  tap_button:     '👆 Tap Button',
  tap_relative:   '🎯 Tap Position',
  input_text:     '⌨️ Type Text',
  paste:          '📋 Paste',
  long_press:     '👇 Long Press',
  swipe:          '👉 Swipe',
  scroll_down:    '⬇️ Scroll Down',
  scroll_up:      '⬆️ Scroll Up',
  wait:           '⏳ Wait',
  delay:          '⏳ Delay',
  wait_until:     '🔍 Wait Until',
  launch_app:     '🚀 Launch App',
  open_activity:  '📱 Open Activity',
  take_screenshot:'📸 Screenshot',
  verify_screen:  '✅ Verify Screen',
  verify_button:  '✅ Verify Button',
  back:           '← Back',
  home:           '🏠 Home',
  recent_apps:    '⊡ Recent Apps',
  export:         '📤 Export',
  share:          '↗ Share',
}

export const EXECUTION_STATUS_COLOR: Record<string, string> = {
  RUNNING:   'bg-amber-100 text-amber-700',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  FAILED:    'bg-red-100 text-red-600',
  CANCELLED: 'bg-gray-100 text-gray-500',
}
