export type ContentStatus =
  | 'IDEA'
  | 'BRIEF'
  | 'PROMPT_READY'
  | 'WAITING_GENERATION'
  | 'VIDEO_CREATED'
  | 'READY_TO_POST'
  | 'POSTED'
  | 'FAILED'

export interface ProductContentContext {
  product_name?: string
  product_description?: string
  key_benefits?: string[]
  target_audience?: string
  pain_points?: string[]
  buying_motivations?: string[]
  video_type?: string
  content_angle?: string
  visual_style?: string
  avatar?: string
  reference_image?: string
  custom_instructions?: string
}

export interface ContentJob {
  id: number
  title: string
  topic: string
  objective: string
  audience: string
  product: string
  duration: string
  visual_style: string
  hook: string
  story: string
  cta: string
  video_prompt: string
  cover_hook: string
  caption: string
  hashtags: string[]
  reference_images: string[]
  tiktok_product_name: string
  publish_mode: string   // "manual" | "auto" | "draft"
  selected_product_id: number | null
  product_snapshot: Record<string, unknown> | null
  avatar: string
  custom_instructions: string
  video_type: string
  selected_content_angle: string
  status: ContentStatus
  created_at: string | null
  updated_at: string | null
}

export interface ContentJobCreate {
  title: string
  topic?: string
  objective?: string
  audience?: string
  product?: string
  duration?: string
  visual_style?: string
  tiktok_product_name?: string
  publish_mode?: string
  avatar?: string
  custom_instructions?: string
}

export interface ContentJobUpdate {
  title?: string
  topic?: string
  objective?: string
  audience?: string
  product?: string
  duration?: string
  visual_style?: string
  hook?: string
  story?: string
  cta?: string
  video_prompt?: string
  cover_hook?: string
  caption?: string
  hashtags?: string[]
  reference_images?: string[]
  tiktok_product_name?: string
  publish_mode?: string
  selected_product_id?: number | null
  product_snapshot?: Record<string, unknown> | null
  avatar?: string
  custom_instructions?: string
  video_type?: string
  selected_content_angle?: string
  status?: ContentStatus
}

export interface PipelineRequest {
  device_id: string
  publish_mode?: string  // "manual" | "auto" | "draft"
}

export interface PipelineStartResponse {
  status: string
  execution_job_id: number
  total_steps: number
}

export interface GenerateRequest {
  brief?: boolean
  video_prompt?: boolean
  cover_hook?: boolean
  caption?: boolean
  hashtags?: boolean
  context?: ProductContentContext
}

export interface WorkflowRequest {
  device_id: string
  platform?: string
  post_type?: string
  schedule_time?: string | null
}

export const STATUS_PIPELINE: ContentStatus[] = [
  'IDEA',
  'BRIEF',
  'PROMPT_READY',
  'WAITING_GENERATION',
  'VIDEO_CREATED',
  'READY_TO_POST',
  'POSTED',
]

export const STATUS_LABEL: Record<ContentStatus, string> = {
  IDEA: 'Idea',
  BRIEF: 'Brief',
  PROMPT_READY: 'Prompt Ready',
  WAITING_GENERATION: 'Waiting Generation',
  VIDEO_CREATED: 'Video Created',
  READY_TO_POST: 'Ready to Post',
  POSTED: 'Posted',
  FAILED: 'Failed',
}

export const STATUS_COLOR: Record<ContentStatus, string> = {
  IDEA: 'bg-gray-100 text-gray-600',
  BRIEF: 'bg-blue-100 text-blue-700',
  PROMPT_READY: 'bg-indigo-100 text-indigo-700',
  WAITING_GENERATION: 'bg-amber-100 text-amber-700',
  VIDEO_CREATED: 'bg-violet-100 text-violet-700',
  READY_TO_POST: 'bg-emerald-100 text-emerald-700',
  POSTED: 'bg-green-100 text-green-700',
  FAILED: 'bg-red-100 text-red-600',
}
