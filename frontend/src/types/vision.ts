export type ScreenType =
  | 'Home'
  | 'Loading'
  | 'Permission Dialog'
  | 'Gallery Picker'
  | 'Share Sheet'
  | 'Export Screen'
  | 'Generation Screen'
  | 'Error Dialog'
  | 'Confirmation Dialog'
  | 'Unknown'

export interface ButtonTarget {
  text: string
  x: number
  y: number
  bounds: [number, number, number, number]  // x1, y1, x2, y2
  confidence: number
  clickable: boolean
  source: string
}

export interface ScreenAnalysis {
  device_id: string
  screen_type: ScreenType
  screen_name: string
  confidence: number
  visible_text: string[]
  buttons: ButtonTarget[]
  dialogs: string[]
  loading: boolean
  errors: string[]
  progress: number | null
  detected_icons: string[]
  editable_fields: string[]
  image_placeholders: string[]
  screenshot_path: string | null
  width: number
  height: number
  raw_xml: string
  provider: string
  timestamp: string
  ai_suggestion: string | null
}

export interface WaitRequest {
  screen?: string
  button?: string
  loading?: boolean
  timeout?: number
  poll_interval?: number
  provider?: string
}

export const SCREEN_TYPE_COLOR: Record<ScreenType, string> = {
  'Home': 'bg-blue-100 text-blue-700',
  'Loading': 'bg-amber-100 text-amber-700',
  'Permission Dialog': 'bg-orange-100 text-orange-700',
  'Gallery Picker': 'bg-violet-100 text-violet-700',
  'Share Sheet': 'bg-pink-100 text-pink-700',
  'Export Screen': 'bg-emerald-100 text-emerald-700',
  'Generation Screen': 'bg-indigo-100 text-indigo-700',
  'Error Dialog': 'bg-red-100 text-red-600',
  'Confirmation Dialog': 'bg-yellow-100 text-yellow-700',
  'Unknown': 'bg-gray-100 text-gray-600',
}
