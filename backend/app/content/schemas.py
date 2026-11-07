from pydantic import BaseModel


class ProductContentContext(BaseModel):
    """Full product context passed to every AI generation call."""
    product_name: str = ""
    product_description: str = ""
    key_benefits: list[str] = []
    target_audience: str = ""
    pain_points: list[str] = []
    buying_motivations: list[str] = []
    video_type: str = ""           # awareness | engagement | conversion | demo | testimonial …
    content_angle: str = ""        # selected angle from product library
    visual_style: str = ""         # realistic | cinematic | ugc | lifestyle …
    avatar: str = ""               # e.g. "Malaysian Mother: modest hijab, home setting"
    reference_image: str = ""      # filename in /uploads/
    custom_instructions: str = ""  # user freeform overrides


class ContentJobCreate(BaseModel):
    title: str
    topic: str = ""
    objective: str = ""
    audience: str = ""
    product: str = ""
    duration: str = "8s"
    visual_style: str = ""
    tiktok_product_name: str = ""
    publish_mode: str = "manual"
    avatar: str = ""
    custom_instructions: str = ""


class ContentJobUpdate(BaseModel):
    title: str | None = None
    topic: str | None = None
    objective: str | None = None
    audience: str | None = None
    product: str | None = None
    duration: str | None = None
    visual_style: str | None = None
    hook: str | None = None
    story: str | None = None
    cta: str | None = None
    video_prompt: str | None = None
    cover_hook: str | None = None
    caption: str | None = None
    hashtags: list[str] | None = None
    reference_images: list[str] | None = None
    tiktok_product_name: str | None = None
    publish_mode: str | None = None
    selected_product_id: int | None = None
    product_snapshot: dict | None = None
    avatar: str | None = None
    custom_instructions: str | None = None
    video_type: str | None = None
    selected_content_angle: str | None = None
    status: str | None = None


class ContentJobResponse(BaseModel):
    id: int
    title: str
    topic: str
    objective: str
    audience: str
    product: str
    duration: str
    visual_style: str
    hook: str
    story: str
    cta: str
    video_prompt: str
    cover_hook: str
    caption: str
    hashtags: list[str]
    reference_images: list[str]
    tiktok_product_name: str
    publish_mode: str
    selected_product_id: int | None = None
    product_snapshot: dict | None = None
    avatar: str
    custom_instructions: str
    video_type: str = ""
    selected_content_angle: str = ""
    status: str
    created_at: str | None
    updated_at: str | None


class GenerateRequest(BaseModel):
    """Which pipeline stages to run plus optional product context override."""
    brief: bool = True
    video_prompt: bool = True
    cover_hook: bool = True
    caption: bool = True
    hashtags: bool = True
    context: ProductContentContext | None = None  # if provided, overrides job fields


class WorkflowRequest(BaseModel):
    device_id: str
    platform: str = "ytcreate"   # ytcreate | tiktok | capcut | instagram
    post_type: str = "draft"      # post_now | draft | schedule
    schedule_time: str | None = None


class PipelineRequest(BaseModel):
    """Request body for POST /jobs/{id}/run_pipeline."""
    device_id: str
    publish_mode: str = "manual"  # manual | auto | draft


class WorkflowResponse(BaseModel):
    steps: list[dict]
    total_steps: int
