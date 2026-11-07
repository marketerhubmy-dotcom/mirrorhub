export interface SavedProduct {
  id: number
  name: string
  url: string
  platform: string
  source_type: string
  product_id: string | null
  shop_name: string
  price: string
  description: string
  image_filename: string | null
  image_url: string | null
  reference_image_path: string | null
  key_benefits: string[]
  pain_points: string[]
  desires: string[]
  triggers: string[]
  common_pain_points: string[]
  buying_motivations: string[]
  suggested_content_angles: string[]
  target_audience: string
  target_audience_options: string[]
  default_video_objective: string
  default_video_style: string
  tiktok_product_name: string
  created_at: string | null
  updated_at: string | null
}

export interface ScrapedProduct {
  fetch_failed: boolean
  fetch_error: string
  title: string
  shop_name: string
  description: string
  image_url: string
  price: string
  rating: string
  final_url: string
  product_id: string | null
}

export interface ProductAnalysis {
  target_audience: string
  target_audience_options: string[]
  common_pain_points: string[]
  buying_motivations: string[]
  suggested_content_angles: string[]
  default_video_objective: string
  default_video_style: string
  tiktok_product_name: string
  key_benefits: string[]
  confidence: number
  warnings: string[]
}

// Normalized shape produced by all import paths (URL, text, screenshot, saved)
export interface ProductDraft {
  source_type: 'url' | 'text' | 'screenshot' | 'saved'
  product_url: string
  product_name: string
  shop_name: string
  product_description: string
  price: string
  key_benefits: string[]
  target_audience: string
  target_audience_options: string[]
  common_pain_points: string[]
  buying_motivations: string[]
  suggested_content_angles: string[]
  default_video_objective: string
  default_video_style: string
  tiktok_product_name: string
  source_images: string[]   // filenames in /uploads/ (screenshots or product image)
  confidence: number        // 0.0–1.0
  warnings: string[]
  vision_error?: string     // set if screenshot vision failed
}

export interface ProductFetchResult {
  scraped: ScrapedProduct
  analysis: ProductAnalysis
  image_filename: string | null
  fetch_failed: boolean
  fetch_error: string
  ai_error: string
  canonical_url: string
  existing_id: number | null
  draft: ProductDraft       // normalized draft, always present
}

export interface ProductSaveRequest {
  name: string
  url?: string
  platform?: string
  source_type?: string
  product_id?: string | null
  shop_name?: string
  price?: string
  description?: string
  image_filename?: string | null
  image_url?: string | null
  reference_image_path?: string | null
  key_benefits?: string[]
  pain_points?: string[]
  desires?: string[]
  triggers?: string[]
  common_pain_points?: string[]
  buying_motivations?: string[]
  suggested_content_angles?: string[]
  target_audience?: string
  target_audience_options?: string[]
  default_video_objective?: string
  default_video_style?: string
  tiktok_product_name?: string
}

export interface ProductConflict {
  message: string
  existing_product_id: number
  existing_product_name: string
  matched_by: 'url' | 'product_id' | 'name_shop' | 'name_only_legacy'
  existing_product: SavedProduct
}

export interface ProductRefreshResult extends ProductFetchResult {
  saved: SavedProduct
  diff: Record<string, { old: string; new: string }>
  has_changes: boolean
}

// Helper: normalize a SavedProduct into a ProductDraft
export function savedToProductDraft(p: SavedProduct): ProductDraft {
  return {
    source_type: 'saved',
    product_url: p.url.startsWith('http') ? p.url : '',
    product_name: p.name,
    shop_name: p.shop_name,
    product_description: p.description,
    price: p.price,
    key_benefits: p.key_benefits,
    target_audience: p.target_audience,
    target_audience_options: p.target_audience_options.length
      ? p.target_audience_options
      : p.target_audience ? [p.target_audience] : [],
    common_pain_points: p.common_pain_points,
    buying_motivations: p.buying_motivations,
    suggested_content_angles: p.suggested_content_angles,
    default_video_objective: p.default_video_objective,
    default_video_style: p.default_video_style,
    tiktok_product_name: p.tiktok_product_name,
    source_images: p.image_filename ? [p.image_filename] : [],
    confidence: 1.0,   // saved = fully vetted by user
    warnings: [],
  }
}
