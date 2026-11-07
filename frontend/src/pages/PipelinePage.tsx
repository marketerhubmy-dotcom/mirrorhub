/**
 * AI Video Studio — MVP 0.6
 * Wizard: Product → Type → Angle → Style+Avatar → Generate → Review
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'
import { contentApi } from '../services/contentApi'
import { productApi } from '../services/productApi'
import type { ContentJob, ContentJobUpdate } from '../types/content'
import type { ExecutionStateResponse } from '../types/execution'
import type { SavedProduct } from '../types/product'
import ProductImportAssistant from '../components/ProductImportAssistant'
import type { PipelineFields } from '../components/ProductImportAssistant'
import ProductLibraryPanel from '../components/ProductLibraryPanel'

// ── Avatar presets ─────────────────────────────────────────────────────────────

const AVATAR_PRESETS = [
  { id: 'Malaysian Mother',     label: 'Ibu Malaysia',         icon: '👩‍👧' },
  { id: 'Malaysian Father',     label: 'Bapa Malaysia',        icon: '👨‍👦' },
  { id: 'Young Adult Woman',    label: 'Wanita Muda',          icon: '👩' },
  { id: 'Young Adult Man',      label: 'Lelaki Muda',          icon: '👨' },
  { id: 'Female Student',       label: 'Pelajar Perempuan',    icon: '👩‍🎓' },
  { id: 'Male Student',         label: 'Pelajar Lelaki',       icon: '👨‍🎓' },
  { id: 'Primary School Child', label: 'Kanak-kanak',          icon: '🧒' },
  { id: 'Product Only',         label: 'Produk Sahaja',        icon: '📦' },
  { id: 'Hands Only',           label: 'Tangan Sahaja',        icon: '🤲' },
  { id: 'Custom',               label: 'Avatar Sendiri',       icon: '✏️' },
]

// ── Video types & styles ───────────────────────────────────────────────────────

const VIDEO_TYPES = [
  { id: 'awareness',    label: 'Awareness',         icon: '👋', desc: 'Perkenalkan produk ke audiens baru' },
  { id: 'engagement',  label: 'Engagement',         icon: '💬', desc: 'Dapatkan komen, share, save maksimum' },
  { id: 'conversion',  label: 'Conversion',         icon: '💰', desc: 'Drive klik ke link dan beli sekarang' },
  { id: 'storytelling',label: 'Storytelling',       icon: '📖', desc: 'Cerita emosional yang menyentuh hati' },
  { id: 'demo',        label: 'Product Demo',       icon: '🎬', desc: 'Tunjukkan cara guna produk step-by-step' },
  { id: 'problem',     label: 'Problem & Solution', icon: '💡', desc: 'Highlight masalah + tunjukkan penyelesaian' },
  { id: 'testimonial', label: 'Testimonial Style',  icon: '⭐', desc: 'UGC-style review yang autentik' },
  { id: 'faq',         label: 'FAQ',                icon: '❓', desc: 'Jawab soalan biasa pelanggan' },
]

const VISUAL_STYLES = [
  { id: 'realistic',  label: 'Realistic',     icon: '📸', desc: 'Natural, kehidupan harian sebenar' },
  { id: 'cinematic',  label: 'Cinematic',     icon: '🎞️', desc: 'Dramatic lighting, colour grade profesional' },
  { id: 'ugc',        label: 'UGC',           icon: '📱', desc: 'User-generated, candid, tidak formal' },
  { id: 'lifestyle',  label: 'Lifestyle',     icon: '✨', desc: 'Gaya hidup aspirasi, bright & clean' },
  { id: 'product',    label: 'Product Focus', icon: '🔍', desc: 'Macro shots, product hero' },
  { id: 'family',     label: 'Family',        icon: '👨‍👩‍👧', desc: 'Suasana keluarga, warm tones' },
  { id: 'talking',    label: 'Talking Style', icon: '🎤', desc: 'Talking head, direct to camera' },
]

// ── Helpers ────────────────────────────────────────────────────────────────────

function isTerminal(status: string) {
  return ['COMPLETED', 'FAILED', 'CANCELLED', 'READY_FOR_REVIEW'].includes(status)
}

function statusColor(status: string) {
  if (status === 'COMPLETED') return 'bg-emerald-100 text-emerald-700'
  if (status === 'READY_FOR_REVIEW') return 'bg-yellow-100 text-yellow-800'
  if (status === 'FAILED' || status === 'CANCELLED') return 'bg-red-100 text-red-600'
  if (status === 'RUNNING' || status === 'STARTING') return 'bg-amber-100 text-amber-700'
  return 'bg-gray-100 text-gray-600'
}

function emptyForm() {
  return {
    product: '',
    topic: '',
    objective: '',
    audience: '',
    visual_style: '',
    hook: '',
    video_prompt: '',
    cover_hook: '',
    caption: '',
    hashtags: [] as string[],
    tiktok_product_name: '',
    publish_mode: 'manual',
    avatar: '',
    custom_instructions: '',
    video_type: '',
    selected_content_angle: '',
  }
}

type Form = ReturnType<typeof emptyForm>

function jobToForm(j: ContentJob): Form {
  return {
    product: j.product,
    topic: j.topic,
    objective: j.objective,
    audience: j.audience,
    visual_style: j.visual_style,
    hook: j.hook,
    video_prompt: j.video_prompt,
    cover_hook: j.cover_hook || '',
    caption: j.caption,
    hashtags: j.hashtags,
    tiktok_product_name: j.tiktok_product_name || '',
    publish_mode: j.publish_mode || 'manual',
    avatar: j.avatar || '',
    custom_instructions: j.custom_instructions || '',
    video_type: j.video_type || '',
    selected_content_angle: j.selected_content_angle || '',
  }
}

// ── Shared UI ──────────────────────────────────────────────────────────────────

function Card({ title, children, accent = false, className = '' }: {
  title?: string; children: React.ReactNode; accent?: boolean; className?: string
}) {
  return (
    <div className={`rounded-xl border p-4 space-y-3 ${accent ? 'bg-violet-50 border-violet-200' : 'bg-white border-gray-200'} ${className}`}>
      {title && (
        <p className={`text-xs font-bold uppercase tracking-widest ${accent ? 'text-violet-500' : 'text-gray-400'}`}>
          {title}
        </p>
      )}
      {children}
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">{children}</p>
}

function Input({ value, onChange, placeholder, rows = 1, mono = false, disabled = false }: {
  value: string; onChange: (v: string) => void; placeholder?: string
  rows?: number; mono?: boolean; disabled?: boolean
}) {
  if (rows === 1) {
    return (
      <input
        value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder} disabled={disabled}
        className={`w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none
          focus:ring-2 focus:ring-violet-500 ${mono ? 'font-mono text-xs bg-violet-50' : 'bg-white'}
          disabled:bg-gray-50 disabled:text-gray-400`}
      />
    )
  }
  return (
    <textarea
      value={value} onChange={e => onChange(e.target.value)}
      placeholder={placeholder} rows={rows} disabled={disabled}
      className={`w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none
        focus:ring-2 focus:ring-violet-500 resize-none
        ${mono ? 'font-mono text-xs bg-violet-50 border-violet-200' : 'bg-white'}
        disabled:bg-gray-50 disabled:text-gray-400`}
    />
  )
}

function RegenerateBtn({ onClick, loading, label }: {
  onClick: () => void; loading: boolean; label: string
}) {
  return (
    <button
      onClick={onClick} disabled={loading}
      className="text-xs text-violet-600 border border-violet-200 px-2.5 py-1 rounded-lg
        hover:bg-violet-50 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
    >
      {loading ? '⏳' : '↻'} {label}
    </button>
  )
}

function StepBadge({ status }: { status: string }) {
  const color =
    status === 'success'  ? 'bg-emerald-500' :
    status === 'running'  ? 'bg-amber-400 animate-pulse' :
    status === 'failed'   ? 'bg-red-500' :
    status === 'skipped'  ? 'bg-gray-300' : 'bg-gray-100'
  return <span className={`w-2 h-2 rounded-full inline-block shrink-0 ${color}`} />
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <p className="text-xs text-gray-400 font-medium">{label}</p>
      <p className="text-xs text-gray-800 font-semibold truncate mt-0.5">{value || '—'}</p>
    </div>
  )
}

// ── Wizard Step Indicator ──────────────────────────────────────────────────────

const STEP_LABELS = ['Produk', 'Jenis', 'Angle', 'Gaya & Avatar', 'Jana', 'Semak']

function WizardStepIndicator({ step, onStepClick, maxReached }: {
  step: number; onStepClick: (s: number) => void; maxReached: number
}) {
  return (
    <div className="flex items-center gap-0 flex-wrap">
      {STEP_LABELS.map((label, i) => {
        const n = i + 1
        const active = n === step
        const done = n < step
        const clickable = n <= maxReached
        return (
          <div key={n} className="flex items-center">
            <button
              onClick={() => clickable && onStepClick(n)}
              disabled={!clickable}
              className={`flex flex-col items-center gap-1 ${clickable ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold
                transition-all border-2 ${active ? 'bg-violet-600 border-violet-600 text-white'
                : done ? 'bg-violet-100 border-violet-400 text-violet-700'
                : 'bg-white border-gray-200 text-gray-400'}`}>
                {done ? '✓' : n}
              </div>
              <span className={`text-xs ${active ? 'text-violet-700 font-semibold' : done ? 'text-violet-500' : 'text-gray-400'}`}>
                {label}
              </span>
            </button>
            {i < STEP_LABELS.length - 1 && (
              <div className={`h-0.5 w-5 mx-1 mb-4 ${n < step ? 'bg-violet-400' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}

function WizardNav({ step, canNext, nextLabel = 'Seterusnya →', onBack, onNext, loading = false }: {
  step: number; canNext: boolean; nextLabel?: string
  onBack: () => void; onNext: () => void; loading?: boolean
}) {
  return (
    <div className="flex gap-3 pt-2">
      {step > 1 && (
        <button onClick={onBack}
          className="px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 font-medium">
          ← Kembali
        </button>
      )}
      <button onClick={onNext} disabled={!canNext || loading}
        className="flex-1 py-2.5 bg-violet-600 text-white rounded-xl text-sm font-semibold
          hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed">
        {loading ? '⏳ Sedang jana...' : nextLabel}
      </button>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function PipelinePage() {
  const navigate = useNavigate()
  const { devices } = useDevices()
  const onlineDevices = devices.filter(d => d.is_online && d.adb_address)

  // Job state
  const [jobs, setJobs]               = useState<ContentJob[]>([])
  const [job, setJob]                 = useState<ContentJob | null>(null)
  const [form, setForm]               = useState<Form>(emptyForm())
  const [imageFile, setImageFile]     = useState<File | null>(null)
  const [presetImageFilename, setPresetImageFilename] = useState<string | null>(null)
  const imageRef = useRef<HTMLInputElement>(null)

  // Execution
  const [execId, setExecId]           = useState<number | null>(null)
  const [execState, setExecState]     = useState<ExecutionStateResponse | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [deviceId, setDeviceId]       = useState('')

  // UI flags
  const [generating, setGenerating]   = useState(false)
  const [regenLoading, setRegenLoading] = useState<Record<string, boolean>>({})
  const [starting, setStarting]       = useState(false)
  const [saving, setSaving]           = useState(false)
  const [genError, setGenError]       = useState('')
  const [runError, setRunError]       = useState('')

  // Wizard
  const [wizardStep, setWizardStep]         = useState<1|2|3|4|5|6>(1)
  const [maxReached, setMaxReached]         = useState(1)
  const [selectedProduct, setSelectedProduct] = useState<SavedProduct | null>(null)
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null)
  const [videoType, setVideoType]           = useState('')
  const [selectedAngle, setSelectedAngle]   = useState('')
  const [customAngle, setCustomAngle]       = useState('')
  const [selectedStyle, setSelectedStyle]   = useState('')
  const [selectedAvatar, setSelectedAvatar] = useState('')
  const [customAvatarText, setCustomAvatarText] = useState('')
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [libraryKey, setLibraryKey]         = useState(0)
  const [advancedOpen, setAdvancedOpen]     = useState(false)

  const setField = (key: keyof Form) => (val: string) =>
    setForm(prev => ({ ...prev, [key]: val }))

  const goToStep = (s: 1|2|3|4|5|6) => {
    setWizardStep(s)
    setMaxReached(prev => Math.max(prev, s))
  }

  // Load jobs on mount
  useEffect(() => {
    contentApi.list().then(list => {
      setJobs(list)
      if (list.length > 0) {
        const first = list[0]
        setJob(first)
        setForm(jobToForm(first))
        if (first.selected_product_id) {
          setSelectedProductId(first.selected_product_id)
          productApi.get(first.selected_product_id).then(setSelectedProduct).catch(() => {})
        }
        if (first.avatar) setSelectedAvatar(first.avatar)
      }
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (onlineDevices.length > 0 && !deviceId) setDeviceId(onlineDevices[0].device_id)
  }, [onlineDevices, deviceId])

  const startPolling = useCallback((id: number) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      const state = await contentApi.latestExecution(id) as ExecutionStateResponse | null
      if (state) {
        setExecState(state)
        if (isTerminal((state as any).status)) {
          clearInterval(pollRef.current!)
          pollRef.current = null
          setStarting(false)
        }
      }
    }, 2000)
  }, [])

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])
  useEffect(() => { if (execId) startPolling(execId) }, [execId, startPolling])

  const loadLatestExec = useCallback(async (j: ContentJob) => {
    const state = await contentApi.latestExecution(j.id) as ExecutionStateResponse | null
    if (state) {
      setExecState(state)
      const execJobId = (state as any).job_id
      if (execJobId) setExecId(execJobId)
      if (!isTerminal((state as any).status)) startPolling(execJobId)
    } else {
      setExecState(null); setExecId(null)
    }
  }, [startPolling])

  const selectJob = (j: ContentJob) => {
    setJob(j); setForm(jobToForm(j))
    setImageFile(null); setPresetImageFilename(null)
    setRunError(''); setGenError('')
    const pid = j.selected_product_id ?? null
    setSelectedProductId(pid); setSelectedProduct(null)
    if (pid) productApi.get(pid).then(setSelectedProduct).catch(() => {})
    if (j.avatar) setSelectedAvatar(j.avatar)
    if (j.video_type) setVideoType(j.video_type)
    if (j.selected_content_angle) setSelectedAngle(j.selected_content_angle)
    loadLatestExec(j)
  }

  const createNew = async () => {
    try {
      const newJob = await contentApi.create({ title: 'AI Video Studio Job' })
      setJobs(prev => [newJob, ...prev])
      selectJob(newJob)
      setWizardStep(1); setMaxReached(1)
      setSelectedProduct(null); setSelectedProductId(null)
      setVideoType(''); setSelectedAngle(''); setCustomAngle('')
      setSelectedStyle(''); setSelectedAvatar(''); setCustomAvatarText('')
    } catch (e) { alert('Gagal buat job: ' + (e as Error).message) }
  }

  // Build product snapshot including avatar
  const buildSnapshot = () => {
    if (!selectedProduct) return null
    const avatarValue = selectedAvatar === 'Custom' ? customAvatarText : selectedAvatar
    return {
      product_id: selectedProduct.id,
      product_name: selectedProduct.name,
      description: selectedProduct.description,
      key_benefits: selectedProduct.key_benefits,
      pain_points: selectedProduct.common_pain_points,
      buying_motivations: selectedProduct.buying_motivations,
      target_audience: selectedProduct.target_audience,
      selected_content_angle: selectedAngle || customAngle,
      tiktok_product_name: selectedProduct.tiktok_product_name,
      reference_image: presetImageFilename || selectedProduct.reference_image_path,
      video_type: videoType,
      visual_style: selectedStyle,
      avatar: avatarValue,
      custom_avatar: selectedAvatar === 'Custom' ? customAvatarText : '',
    }
  }

  const saveForm = async () => {
    if (!job) return job
    setSaving(true)
    try {
      const avatarValue = selectedAvatar === 'Custom' ? customAvatarText : selectedAvatar
      const effectiveAngleSave = selectedAngle || customAngle
      const patch: ContentJobUpdate = {
        product: form.product,
        topic: effectiveAngleSave || form.topic,
        objective: form.objective,
        audience: form.audience,
        visual_style: selectedStyle || form.visual_style,
        hook: form.hook,
        video_prompt: form.video_prompt,
        cover_hook: form.cover_hook,
        caption: form.caption,
        hashtags: form.hashtags,
        tiktok_product_name: form.tiktok_product_name,
        publish_mode: form.publish_mode,
        avatar: avatarValue,
        custom_instructions: form.custom_instructions,
        video_type: videoType,
        selected_content_angle: effectiveAngleSave,
        selected_product_id: selectedProductId ?? undefined,
        product_snapshot: buildSnapshot() ?? undefined,
      }
      const updated = await contentApi.update(job.id, patch)
      setJob(updated)
      setJobs(prev => prev.map(j => (j.id === updated.id ? updated : j)))
      return updated
    } finally { setSaving(false) }
  }

  const uploadImageIfPending = async (jobId: number) => {
    if (!imageFile) return
    const updated = await contentApi.uploadImage(jobId, imageFile)
    setJob(updated)
    setJobs(prev => prev.map(j => (j.id === updated.id ? updated : j)))
    setImageFile(null)
  }

  // Build the ProductContentContext that's sent to every AI call
  const buildGenerateContext = () => {
    const avatarValue = selectedAvatar === 'Custom' ? customAvatarText : selectedAvatar
    return {
      product_name:         form.product || selectedProduct?.name || '',
      product_description:  selectedProduct?.description || '',
      key_benefits:         selectedProduct?.key_benefits || [],
      target_audience:      form.audience || selectedProduct?.target_audience || '',
      pain_points:          selectedProduct?.common_pain_points || [],
      buying_motivations:   selectedProduct?.buying_motivations || [],
      video_type:           videoType,
      content_angle:        selectedAngle || customAngle || form.topic,
      visual_style:         selectedStyle || form.visual_style,
      avatar:               avatarValue,
      custom_instructions:  form.custom_instructions,
      reference_image:      presetImageFilename || selectedProduct?.reference_image_path || '',
    }
  }

  // Full regenerate — saves first, then generates with full context
  const generate = async () => {
    if (!job) return
    setGenerating(true); setGenError('')
    try {
      const saved = await saveForm()
      if (!saved) return
      if (imageFile) await uploadImageIfPending(saved.id)
      const updated = await contentApi.generate(saved.id, { context: buildGenerateContext() })
      setJob(updated); setJobs(prev => prev.map(j => (j.id === updated.id ? updated : j)))
      setForm(jobToForm(updated))
    } catch (e) { setGenError((e as Error).message) }
    finally { setGenerating(false) }
  }

  // Per-field regenerate — always sends the same full context
  const regenerate = async (field: 'video_prompt' | 'cover_hook' | 'caption' | 'hashtags') => {
    if (!job) return
    setRegenLoading(prev => ({ ...prev, [field]: true }))
    try {
      const saved = await saveForm()
      if (!saved) return
      const updated = await contentApi.regenerateField(saved.id, field, {
        context: buildGenerateContext(),
      })
      setJob(updated); setJobs(prev => prev.map(j => (j.id === updated.id ? updated : j)))
      setForm(jobToForm(updated))
    } catch (e) { setGenError((e as Error).message) }
    finally { setRegenLoading(prev => ({ ...prev, [field]: false })) }
  }

  const startPipeline = async () => {
    if (!job || !deviceId) return
    setStarting(true); setRunError(''); setExecState(null)
    try {
      const saved = await saveForm()
      if (!saved) return
      if (imageFile) await uploadImageIfPending(saved.id)
      const resp = await contentApi.runPipeline(saved.id, {
        device_id: deviceId, publish_mode: form.publish_mode,
      })
      setExecId(resp.execution_job_id)
      startPolling(resp.execution_job_id)
    } catch (e) { setRunError((e as Error).message); setStarting(false) }
  }

  const retry = async () => { setExecState(null); setExecId(null); await startPipeline() }

  const applyProductFields = async (fields: Partial<PipelineFields>, imageFilename: string | null) => {
    setForm(prev => ({ ...prev, ...fields }))
    if (imageFilename) setPresetImageFilename(imageFilename)
    setShowAddProduct(false)
    if (fields.product) {
      try {
        const all = await productApi.list()
        const match = all.find(p => p.name.toLowerCase() === (fields.product || '').toLowerCase())
        if (match) {
          setSelectedProduct(match); setSelectedProductId(match.id)
          if (match.suggested_content_angles.length > 0) setSelectedAngle(match.suggested_content_angles[0])
        }
        setLibraryKey(k => k + 1)
      } catch {}
    }
    goToStep(2)
  }

  const handleLibrarySelect = (p: SavedProduct) => {
    setSelectedProduct(p); setSelectedProductId(p.id)
    setForm(prev => ({
      ...prev, product: p.name,
      audience: p.target_audience || prev.audience,
      tiktok_product_name: p.tiktok_product_name || prev.tiktok_product_name,
    }))
    const img = p.reference_image_path || p.image_filename
    if (img) setPresetImageFilename(img)
    if (p.default_video_objective) setForm(prev => ({ ...prev, objective: p.default_video_objective }))
  }

  // Derived state
  const hasGenerated   = !!(job && (job.hook || job.video_prompt))
  const hasCoverHook   = !!(job?.cover_hook?.trim())
  const hasImage       = !!(job && (job.reference_images.length > 0 || imageFile || presetImageFilename))
  const hasValidHashtags = (job?.hashtags?.length ?? 0) >= 3
  const hasTikTokProduct = !!(form.tiktok_product_name?.trim())
  const isPipelineRunning        = execState && !isTerminal((execState as any).status)
  const isPipelineFailed         = execState && (execState as any).status === 'FAILED'
  const isPipelineDone           = execState && (execState as any).status === 'COMPLETED'
  const isPipelineReadyForReview = execState && (execState as any).status === 'READY_FOR_REVIEW'
  const currentStep  = (execState as any)?.current_step
  const execStatus   = (execState as any)?.status as string | undefined

  const displayImageFilename =
    (job && job.reference_images.length > 0 ? job.reference_images[0] : null) || presetImageFilename

  const effectiveAngle = selectedAngle || customAngle

  // 9-condition Start Button Validation (Part 18)
  const startConditions = [
    { ok: !!selectedProduct,                    label: 'Produk dipilih' },
    { ok: hasImage,                             label: 'Gambar rujukan diupload' },
    { ok: !!(job?.video_prompt?.trim()),        label: 'Video Prompt dijana' },
    { ok: hasCoverHook,                         label: 'Cover Hook dijana' },
    { ok: !!(job?.caption?.trim()),             label: 'Caption dijana' },
    { ok: hasValidHashtags,                     label: '3–5 Hashtag dijana' },
    { ok: hasTikTokProduct,                     label: 'Nama produk TikTok Shop diisi' },
    { ok: !!deviceId,                           label: 'Device dipilih' },
    { ok: ['manual', 'auto', 'draft'].includes(form.publish_mode), label: 'Publish mode dipilih' },
  ]
  const missingConditions = startConditions.filter(c => !c.ok)
  const canStart = missingConditions.length === 0 && !starting && !isPipelineRunning

  const step1Valid = !!selectedProduct
  const step2Valid = !!videoType
  const step3Valid = !!effectiveAngle
  const step4Valid = !!selectedStyle && !!selectedAvatar
  const step5Valid = hasGenerated

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-5 py-3 flex items-center gap-3 sticky top-0 z-10">
        <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-700 text-sm">
          ← Back
        </button>
        <span className="font-bold text-gray-900">AI Video Studio</span>
        <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full">MVP 0.6.1</span>

        {jobs.length > 0 && (
          <select
            value={job?.id ?? ''}
            onChange={e => { const f = jobs.find(j => j.id === Number(e.target.value)); if (f) selectJob(f) }}
            className="ml-3 border border-gray-200 rounded-lg px-2 py-1 text-xs outline-none
              focus:ring-2 focus:ring-violet-500 max-w-xs truncate"
          >
            {jobs.map(j => (
              <option key={j.id} value={j.id}>
                {j.product ? `${j.product} — ` : ''}{j.topic || '(no topic)'} #{j.id}
              </option>
            ))}
          </select>
        )}
        <div className="ml-auto">
          <button onClick={createNew}
            className="px-3 py-1.5 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700">
            + New Job
          </button>
        </div>
      </header>

      {/* Main */}
      <div className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* ══ LEFT: Wizard ══════════════════════════════════════════════════════ */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white border border-gray-200 rounded-xl px-5 py-4">
            <WizardStepIndicator step={wizardStep} onStepClick={s => goToStep(s as 1|2|3|4|5|6)} maxReached={maxReached} />
          </div>

          {/* ── Step 1: Product Library ───────────────────────────────────────── */}
          {wizardStep === 1 && (
            <Card title="Langkah 1 — Pilih Produk">
              {showAddProduct ? (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-semibold text-gray-700">Tambah Produk Baru</p>
                    <button onClick={() => setShowAddProduct(false)}
                      className="text-xs text-gray-400 hover:text-gray-700">← Kembali ke Library</button>
                  </div>
                  <ProductImportAssistant onApply={applyProductFields} />
                </div>
              ) : (
                <ProductLibraryPanel
                  selectedId={selectedProductId}
                  onSelect={handleLibrarySelect}
                  onAddNew={() => setShowAddProduct(true)}
                  refreshKey={libraryKey}
                />
              )}
              {!showAddProduct && (
                <WizardNav step={1} canNext={step1Valid} nextLabel="Pilih Jenis Video →"
                  onBack={() => {}} onNext={() => goToStep(2)} />
              )}
            </Card>
          )}

          {/* ── Step 2: Video Type ────────────────────────────────────────────── */}
          {wizardStep === 2 && (
            <Card title="Langkah 2 — Jenis Video">
              <p className="text-sm text-gray-500">Pilih objektif utama untuk video TikTok ini.</p>
              <div className="grid grid-cols-2 gap-2">
                {VIDEO_TYPES.map(t => (
                  <button key={t.id} onClick={() => { setVideoType(t.id); setForm(prev => ({ ...prev, objective: t.desc })) }}
                    className={`p-3 rounded-xl border text-left transition-all ${
                      videoType === t.id ? 'bg-violet-50 border-violet-400' : 'bg-white border-gray-200 hover:border-gray-300'}`}>
                    <div className="text-xl mb-1">{t.icon}</div>
                    <p className={`text-sm font-semibold ${videoType === t.id ? 'text-violet-800' : 'text-gray-800'}`}>{t.label}</p>
                    <p className="text-xs text-gray-400 mt-0.5 leading-snug">{t.desc}</p>
                  </button>
                ))}
              </div>
              <WizardNav step={2} canNext={step2Valid} nextLabel="Pilih Content Angle →"
                onBack={() => goToStep(1)} onNext={() => goToStep(3)} />
            </Card>
          )}

          {/* ── Step 3: Content Angle ─────────────────────────────────────────── */}
          {wizardStep === 3 && (
            <Card title="Langkah 3 — Content Angle">
              {selectedProduct && selectedProduct.suggested_content_angles.length > 0 ? (
                <div className="space-y-2">
                  {selectedProduct.suggested_content_angles.map((angle, i) => (
                    <button key={i} onClick={() => { setSelectedAngle(angle); setCustomAngle(''); setForm(prev => ({ ...prev, topic: angle })) }}
                      className={`w-full text-left p-3 rounded-xl border text-sm transition-all ${
                        selectedAngle === angle ? 'bg-violet-50 border-violet-400 text-violet-800 font-medium'
                        : 'bg-white border-gray-200 hover:border-gray-300 text-gray-700'}`}>
                      <span className="mr-2 text-violet-400">→</span>{angle}
                    </button>
                  ))}
                  <div className={`p-3 rounded-xl border transition-all ${
                    customAngle && !selectedAngle ? 'border-violet-400 bg-violet-50' : 'border-dashed border-gray-300 bg-gray-50'}`}>
                    <p className="text-xs font-semibold text-gray-500 mb-2">Atau tulis angle sendiri:</p>
                    <textarea value={customAngle} onChange={e => { setCustomAngle(e.target.value); if (e.target.value) { setSelectedAngle(''); setForm(prev => ({ ...prev, topic: e.target.value })) } }}
                      rows={2} placeholder="Tulis content angle anda..."
                      className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-violet-500 bg-white resize-none" />
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">Produk ini belum ada content angles. Tulis idea anda:</p>
                  <textarea value={customAngle} onChange={e => { setCustomAngle(e.target.value); setForm(prev => ({ ...prev, topic: e.target.value })) }}
                    rows={3} placeholder="Cth: Cara produk ini selesaikan masalah kulit berminyak dalam 7 hari"
                    className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-violet-500 bg-white resize-none" />
                </div>
              )}
              <WizardNav step={3} canNext={step3Valid} nextLabel="Pilih Gaya & Avatar →"
                onBack={() => goToStep(2)} onNext={() => goToStep(4)} />
            </Card>
          )}

          {/* ── Step 4: Visual Style + Avatar ────────────────────────────────── */}
          {wizardStep === 4 && (
            <div className="space-y-4">
              <Card title="Langkah 4a — Gaya Visual">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {VISUAL_STYLES.map(s => (
                    <button key={s.id} onClick={() => { setSelectedStyle(s.id); setForm(prev => ({ ...prev, visual_style: s.desc })) }}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedStyle === s.id ? 'bg-violet-50 border-violet-400' : 'bg-white border-gray-200 hover:border-gray-300'}`}>
                      <div className="text-2xl mb-1">{s.icon}</div>
                      <p className={`text-sm font-semibold ${selectedStyle === s.id ? 'text-violet-800' : 'text-gray-800'}`}>{s.label}</p>
                      <p className="text-xs text-gray-400 mt-0.5 leading-snug">{s.desc}</p>
                    </button>
                  ))}
                </div>
              </Card>

              <Card title="Langkah 4b — Avatar / Watak Video">
                <p className="text-sm text-gray-500">Pilih watak yang akan muncul dalam video. Avatar ini digunakan dalam video prompt.</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {AVATAR_PRESETS.map(a => (
                    <button key={a.id} onClick={() => { setSelectedAvatar(a.id); setForm(prev => ({ ...prev, avatar: a.id })) }}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedAvatar === a.id ? 'bg-violet-50 border-violet-400' : 'bg-white border-gray-200 hover:border-gray-300'}`}>
                      <div className="text-2xl mb-1">{a.icon}</div>
                      <p className={`text-sm font-semibold ${selectedAvatar === a.id ? 'text-violet-800' : 'text-gray-800'}`}>{a.label}</p>
                    </button>
                  ))}
                </div>
                {selectedAvatar === 'Custom' && (
                  <div>
                    <Label>Huraikan avatar anda</Label>
                    <textarea
                      value={customAvatarText}
                      onChange={e => { setCustomAvatarText(e.target.value); setForm(prev => ({ ...prev, avatar: e.target.value })) }}
                      rows={3}
                      placeholder="Cth: Seorang wanita berbaju kurung merah jambu, berambut pendek, berada di kedai runcit..."
                      className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-violet-500 bg-white resize-none"
                    />
                  </div>
                )}
                {selectedAvatar && selectedAvatar !== 'Custom' && (
                  <div className="bg-violet-50 rounded-lg px-3 py-2">
                    <p className="text-xs text-violet-600 font-semibold mb-0.5">Preview avatar</p>
                    <p className="text-xs text-violet-800">
                      {AVATAR_PRESETS.find(a => a.id === selectedAvatar)?.label} — deskripsi lengkap akan digunakan dalam video prompt.
                    </p>
                  </div>
                )}
              </Card>

              <WizardNav step={4} canNext={step4Valid} nextLabel="Jana Content AI →"
                onBack={() => goToStep(3)} onNext={() => goToStep(5)} />
            </div>
          )}

          {/* ── Step 5: Generate ──────────────────────────────────────────────── */}
          {wizardStep === 5 && (
            <div className="space-y-4">
              {/* Context summary */}
              <Card title="Ringkasan Input">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <SummaryRow label="Produk"  value={form.product || selectedProduct?.name || '—'} />
                  <SummaryRow label="Jenis"   value={VIDEO_TYPES.find(t => t.id === videoType)?.label || '—'} />
                  <SummaryRow label="Angle"   value={effectiveAngle} />
                  <SummaryRow label="Gaya"    value={VISUAL_STYLES.find(s => s.id === selectedStyle)?.label || '—'} />
                  <SummaryRow label="Avatar"  value={selectedAvatar === 'Custom' ? (customAvatarText || '—') : AVATAR_PRESETS.find(a => a.id === selectedAvatar)?.label || '—'} />
                  {selectedProduct && (
                    <SummaryRow label="Pain Points" value={`${selectedProduct.common_pain_points.length} titik kesakitan`} />
                  )}
                </div>
              </Card>

              {/* Reference Image */}
              <Card title="Gambar Rujukan">
                <div className="flex items-center gap-3">
                  {displayImageFilename ? (
                    <img src={`/uploads/${displayImageFilename}`} alt=""
                      className="w-16 h-16 object-cover rounded-lg border border-gray-200 shrink-0" />
                  ) : (
                    <div className="w-16 h-16 rounded-lg border-2 border-dashed border-gray-200
                      flex items-center justify-center text-gray-300 text-xl shrink-0">🖼️</div>
                  )}
                  <div className="flex-1">
                    {presetImageFilename && !imageFile && (
                      <p className="text-xs text-emerald-600 mb-1">Dari product preset</p>
                    )}
                    {imageFile && <p className="text-xs text-violet-600 truncate mb-1">{imageFile.name}</p>}
                    <button onClick={() => imageRef.current?.click()}
                      className="text-xs text-violet-600 hover:text-violet-800 border border-violet-200 px-3 py-1.5 rounded-lg hover:bg-violet-50">
                      {hasImage ? 'Tukar gambar' : 'Pilih gambar'}
                    </button>
                    <input ref={imageRef} type="file" accept="image/*" className="hidden"
                      onChange={e => { const f = e.target.files?.[0]; if (f) { setImageFile(f); setPresetImageFilename(null) } }} />
                    <p className="text-xs text-gray-400 mt-1">Wajib — dihantar ke phone sebelum jana video</p>
                  </div>
                </div>
              </Card>

              {/* TikTok Shop + Advanced */}
              <Card>
                <div>
                  <Label>Nama Produk TikTok Shop</Label>
                  <Input value={form.tiktok_product_name} onChange={setField('tiktok_product_name')}
                    placeholder="Nama tepat untuk carian dalam TikTok Shop..." />
                  <p className="text-xs text-gray-400 mt-1">Kosongkan jika tiada produk TikTok Shop</p>
                </div>
                <button onClick={() => setAdvancedOpen(o => !o)}
                  className="flex items-center justify-between w-full text-sm font-semibold text-gray-500 hover:text-gray-800 pt-1">
                  <span>⚙ Arahan Khas (optional)</span>
                  <span className="text-gray-400 text-xs">{advancedOpen ? '▲' : '▼'}</span>
                </button>
                {advancedOpen && (
                  <div className="pt-2 space-y-2 border-t border-gray-100">
                    <Label>Arahan Tambahan untuk AI</Label>
                    <Input value={form.custom_instructions} onChange={setField('custom_instructions')}
                      rows={3} placeholder="Cth: Tolong sebut manfaat utama dalam 3 saat pertama. Jangan guna kata-kata berlebihan." />
                    <Label>Publish Mode</Label>
                    <div className="grid grid-cols-3 gap-2">
                      {(['manual', 'auto', 'draft'] as const).map(mode => (
                        <button key={mode} onClick={() => setForm(p => ({ ...p, publish_mode: mode }))}
                          className={`py-2 rounded-lg text-xs font-medium border transition-colors ${
                            form.publish_mode === mode
                              ? mode === 'auto' ? 'bg-emerald-600 text-white border-emerald-600' : mode === 'draft' ? 'bg-amber-600 text-white border-amber-600' : 'bg-indigo-600 text-white border-indigo-600'
                              : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'}`}>
                          {mode === 'manual' ? '⏸ Stop before post' : mode === 'auto' ? '🚀 Auto publish' : '💾 Save draft (VPN)'}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </Card>

              {/* Generate All button */}
              <button onClick={async () => { await generate(); if (!genError) goToStep(6) }}
                disabled={generating || !form.topic.trim()}
                className="w-full py-3 bg-violet-600 text-white rounded-xl font-semibold
                  hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed">
                {generating ? '⏳ AI sedang jana...' : '✨ Jana Semua Content (Hook + Prompt + Cover + Caption)'}
              </button>
              {genError && <p className="text-sm text-red-500 bg-red-50 rounded-lg px-4 py-2">{genError}</p>}

              {/* Generated output */}
              {hasGenerated && (
                <Card title="Content Dijana — boleh edit">
                  {/* Hook */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label>Hook Video</Label>
                    </div>
                    <Input value={form.hook} onChange={setField('hook')} rows={2} placeholder="Hook..." />
                  </div>

                  {/* Video Prompt */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label>Video Prompt (untuk YouTube Create)</Label>
                      <RegenerateBtn onClick={() => regenerate('video_prompt')}
                        loading={!!regenLoading.video_prompt} label="Prompt" />
                    </div>
                    <Input value={form.video_prompt} onChange={setField('video_prompt')} rows={6} mono placeholder="Video prompt..." />
                    <p className="text-xs text-gray-400 mt-1">{form.video_prompt.length} huruf</p>
                  </div>

                  {/* Cover Hook */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label>Cover Hook (teks pada cover TikTok)</Label>
                      <RegenerateBtn onClick={() => regenerate('cover_hook')}
                        loading={!!regenLoading.cover_hook} label="Cover" />
                    </div>
                    <Input value={form.cover_hook} onChange={setField('cover_hook')} rows={3}
                      mono placeholder={'KULIT KUSAM HARI-HARI?\nRUPANYA ADA\nSEBAB TERSEMBUNYI...'} />
                    <p className="text-xs text-gray-400 mt-1">Max 3 baris. HURUF BESAR. Tanpa hashtag.</p>
                  </div>

                  {/* Caption */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label>TikTok Caption</Label>
                      <RegenerateBtn onClick={() => regenerate('caption')}
                        loading={!!regenLoading.caption} label="Caption" />
                    </div>
                    <Input value={form.caption} onChange={setField('caption')} rows={3} placeholder="Caption..." />
                  </div>

                  {/* Hashtags */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label>Hashtags</Label>
                      <RegenerateBtn onClick={() => regenerate('hashtags')}
                        loading={!!regenLoading.hashtags} label="Hashtags" />
                    </div>
                    <textarea
                      value={form.hashtags.join(' ')}
                      onChange={e => setForm(prev => ({
                        ...prev,
                        hashtags: e.target.value.split(/\s+/).filter(t => t.startsWith('#')),
                      }))}
                      rows={2}
                      placeholder="#hashtag1 #hashtag2 ..."
                      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono
                        outline-none focus:ring-2 focus:ring-violet-500 resize-none bg-white"
                    />
                    {form.hashtags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {form.hashtags.map((t, i) => (
                          <span key={i} className="bg-violet-50 text-violet-700 text-xs px-2 py-0.5 rounded-full border border-violet-100">{t}</span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex gap-2 flex-wrap">
                    <button onClick={saveForm} disabled={saving}
                      className="text-xs text-violet-600 border border-violet-200 px-3 py-1.5 rounded-lg hover:bg-violet-50 disabled:opacity-50">
                      {saving ? 'Saving...' : '💾 Simpan perubahan'}
                    </button>
                    <button onClick={() => goToStep(6)}
                      className="text-xs text-emerald-600 border border-emerald-200 px-3 py-1.5 rounded-lg hover:bg-emerald-50">
                      Teruskan ke Semak →
                    </button>
                  </div>
                </Card>
              )}

              <WizardNav step={5} canNext={step5Valid} nextLabel="Semak & Mula Pipeline →"
                onBack={() => goToStep(4)} onNext={() => goToStep(6)} loading={generating} />
            </div>
          )}

          {/* ── Step 6: Review & Start ────────────────────────────────────────── */}
          {wizardStep === 6 && (
            <div className="space-y-4">
              <Card title="Semak Sebelum Pipeline">
                <div className="space-y-3">
                  {/* Product image + info */}
                  <div className="flex gap-3 items-start">
                    {displayImageFilename ? (
                      <img src={`/uploads/${displayImageFilename}`} alt=""
                        className="w-14 h-14 rounded-lg object-cover border border-gray-100 shrink-0" />
                    ) : (
                      <div className="w-14 h-14 rounded-lg bg-violet-100 flex items-center justify-center text-violet-500 text-xl shrink-0">🛍️</div>
                    )}
                    <div>
                      <p className="font-semibold text-gray-900">{form.product || '—'}</p>
                      <p className="text-xs text-gray-500">{form.audience || '—'}</p>
                      {form.tiktok_product_name && (
                        <p className="text-xs text-indigo-600">🛍 {form.tiktok_product_name}</p>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <SummaryRow label="Jenis"  value={VIDEO_TYPES.find(t => t.id === videoType)?.label || '—'} />
                    <SummaryRow label="Angle"  value={effectiveAngle} />
                    <SummaryRow label="Gaya"   value={VISUAL_STYLES.find(s => s.id === selectedStyle)?.label || '—'} />
                    <SummaryRow label="Avatar" value={selectedAvatar === 'Custom' ? (customAvatarText.slice(0, 30) || '—') : AVATAR_PRESETS.find(a => a.id === selectedAvatar)?.label || '—'} />
                    <SummaryRow label="Device" value={onlineDevices.find(d => d.device_id === deviceId)?.device_name || deviceId || '—'} />
                    <SummaryRow label="Mode"   value={form.publish_mode === 'auto' ? '🚀 Auto' : form.publish_mode === 'draft' ? '💾 Save draft' : '⏸ Stop before post'} />
                  </div>

                  <div className="border border-gray-100 rounded-lg p-3 space-y-1">
                    <p className="text-xs font-semibold text-gray-500">Video Prompt</p>
                    <p className="text-xs text-gray-600 line-clamp-3 font-mono">{form.video_prompt || '—'}</p>
                  </div>

                  {form.cover_hook && (
                    <div className="border border-violet-100 bg-violet-50 rounded-lg p-3 space-y-1">
                      <p className="text-xs font-semibold text-violet-500">Cover Hook</p>
                      <p className="text-xs text-violet-800 font-mono whitespace-pre-line">{form.cover_hook}</p>
                    </div>
                  )}

                  <div className="border border-gray-100 rounded-lg p-3 space-y-1">
                    <p className="text-xs font-semibold text-gray-500">Caption</p>
                    <p className="text-xs text-gray-600 line-clamp-2">{form.caption || '—'}</p>
                    {form.hashtags.length > 0 && (
                      <p className="text-xs text-violet-600">{form.hashtags.slice(0, 5).join(' ')}</p>
                    )}
                  </div>
                </div>
              </Card>

              {/* 9-Condition Validation Checklist */}
              {missingConditions.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 space-y-1">
                  <p className="text-xs font-bold text-amber-700">Pipeline tidak boleh dimulakan. Lengkapkan dulu:</p>
                  {missingConditions.map((c, i) => (
                    <p key={i} className="text-xs text-amber-800">✗ {c.label}</p>
                  ))}
                </div>
              )}
              {missingConditions.length === 0 && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-2">
                  <p className="text-xs text-emerald-700 font-semibold">✓ Semua syarat dipenuhi — sedia untuk pipeline</p>
                </div>
              )}
              {runError && <p className="text-sm text-red-500 bg-red-50 rounded-lg px-4 py-3">{runError}</p>}

              <button onClick={startPipeline} disabled={!canStart || !!isPipelineRunning}
                className="w-full py-4 bg-emerald-600 text-white rounded-xl font-bold text-base
                  hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed shadow-lg">
                {isPipelineRunning ? '⏳ Pipeline sedang berjalan...'
                  : starting ? '⏳ Memulakan...'
                  : '▶ Mula Video Pipeline'}
              </button>

              {isPipelineFailed && (
                <button onClick={retry}
                  className="w-full py-2.5 border border-amber-400 text-amber-700 rounded-xl text-sm font-semibold hover:bg-amber-50">
                  ↩ Cuba Semula
                </button>
              )}

              <div className="flex gap-3">
                <button onClick={() => goToStep(5)}
                  className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">
                  ← Kembali
                </button>
                <button onClick={async () => { goToStep(5); setTimeout(() => generate(), 100) }}
                  className="flex-1 py-2.5 border border-violet-200 rounded-xl text-sm text-violet-700 hover:bg-violet-50 font-medium">
                  ✨ Jana Semula
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ══ RIGHT: Controls + Status ══════════════════════════════════════════ */}
        <div className="space-y-4">
          <Card title="Pipeline Controls">
            <div>
              <Label>Android Device</Label>
              {onlineDevices.length === 0 ? (
                <p className="text-xs text-red-500">No device online — connect a phone first</p>
              ) : (
                <select value={deviceId} onChange={e => setDeviceId(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-2 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-500">
                  {onlineDevices.map(d => (
                    <option key={d.device_id} value={d.device_id}>{d.device_name || d.device_id}</option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <Label>Publish Mode</Label>
              <div className="grid grid-cols-3 gap-2">
                {(['manual', 'auto', 'draft'] as const).map(mode => (
                  <button key={mode} onClick={() => setForm(p => ({ ...p, publish_mode: mode }))}
                    className={`py-2 rounded-lg text-xs font-medium border transition-colors ${
                      form.publish_mode === mode
                        ? mode === 'auto' ? 'bg-emerald-600 text-white border-emerald-600' : mode === 'draft' ? 'bg-amber-600 text-white border-amber-600' : 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'}`}>
                    {mode === 'manual' ? '⏸ Stop before post' : mode === 'auto' ? '🚀 Auto publish' : '💾 Save draft (VPN)'}
                  </button>
                ))}
              </div>
            </div>

            {runError && <p className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">{runError}</p>}

            <button onClick={startPipeline} disabled={!canStart || !!isPipelineRunning}
              className="w-full py-3 bg-emerald-600 text-white rounded-xl font-bold text-sm
                hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed">
              {isPipelineRunning ? '⏳ Pipeline running...' : starting ? '⏳ Starting...' : '▶ Start Full Pipeline'}
            </button>

            {isPipelineFailed && (
              <button onClick={retry}
                className="w-full py-2.5 border border-amber-400 text-amber-700 rounded-xl text-sm font-semibold hover:bg-amber-50">
                ↩ Retry
              </button>
            )}
          </Card>

          {/* Pipeline Status */}
          {execState && (
            <Card title="Pipeline Status">
              <div className="flex items-center justify-between">
                <span className={`text-xs font-bold px-2 py-1 rounded-full ${statusColor(execStatus ?? '')}`}>
                  {execStatus}
                </span>
                <span className="text-xs text-gray-400">{Math.round((execState as any).progress ?? 0)}%</span>
              </div>

              <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full transition-all duration-500 ${
                  isPipelineDone || isPipelineReadyForReview ? 'bg-emerald-500'
                  : isPipelineFailed ? 'bg-red-400' : 'bg-violet-500'}`}
                  style={{ width: `${(execState as any).progress ?? 0}%` }} />
              </div>

              {isPipelineReadyForReview && (
                <div className="bg-yellow-50 border border-yellow-300 rounded-lg px-3 py-3">
                  <p className="text-sm font-bold text-yellow-800">⏸ Ready for Review</p>
                  <p className="text-xs text-yellow-700 mt-1 leading-relaxed">
                    Pipeline selesai. Semak kandungan pada phone, kemudian tap <strong>Post</strong>.
                  </p>
                </div>
              )}

              {currentStep && (
                <div className="bg-gray-50 rounded-lg px-3 py-2">
                  <p className="text-xs font-semibold text-gray-500 mb-0.5">Current step</p>
                  <div className="flex items-center gap-2">
                    <StepBadge status={currentStep.status} />
                    <p className="text-sm font-medium text-gray-800 truncate">{currentStep.label}</p>
                  </div>
                </div>
              )}

              {(execState as any).error && (
                <div className="bg-red-50 rounded-lg px-3 py-2">
                  <p className="text-xs font-semibold text-red-500 mb-0.5">Error</p>
                  <p className="text-xs text-red-600">{(execState as any).error}</p>
                </div>
              )}

              {(execState as any).last_screenshot && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 mb-1">Latest screenshot</p>
                  <img src={`/uploads/${(execState as any).last_screenshot}`} alt="screenshot"
                    className="w-full rounded-lg border border-gray-200 object-contain max-h-48"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                </div>
              )}

              {(execState as any).steps?.length > 0 && (
                <details className="cursor-pointer">
                  <summary className="text-xs font-semibold text-gray-400 select-none">
                    Steps ({(execState as any).steps.length})
                  </summary>
                  <div className="mt-2 space-y-1 max-h-60 overflow-y-auto">
                    {((execState as any).steps as Array<{ status: string; label: string; index: number }>)
                      .map((s, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <StepBadge status={s.status} />
                          <span className={
                            s.status === 'success' ? 'text-gray-400 line-through' :
                            s.status === 'running' ? 'font-semibold text-gray-800' :
                            s.status === 'failed'  ? 'text-red-500 font-semibold' : 'text-gray-400'}>
                            {s.label}
                          </span>
                        </div>
                      ))}
                  </div>
                </details>
              )}
            </Card>
          )}

          {/* Pipeline Flow */}
          <Card title="Pipeline Flow">
            {[
              { icon: '📤', label: 'Upload reference image' },
              { icon: '🎬', label: 'YouTube Create — paste prompt' },
              { icon: '🖼️', label: 'Tambah reference image' },
              { icon: '⚡', label: 'Generate video (AI)' },
              { icon: '📤', label: 'Export + Share ke TikTok' },
              { icon: '🎨', label: 'Edit cover' + (form.cover_hook ? ` + "${form.cover_hook.split('\n')[0]}"` : '') },
              { icon: '✏️', label: 'Insert caption + hashtags' },
              ...(form.tiktok_product_name && form.publish_mode !== 'draft' ? [
                { icon: '🔗', label: 'Buka Add Link' },
                { icon: '⏳', label: 'Tunggu TikTok Shop' },
                { icon: '🔍', label: `Cari: ${form.tiktok_product_name}` },
                { icon: '✅', label: 'Lampirkan produk' },
              ] : []),
              ...(form.tiktok_product_name && form.publish_mode === 'draft' ? [
                { icon: '⏭️', label: 'Skip beg kuning (VPN) — add manual lepas ni' },
              ] : []),
              { icon: form.publish_mode === 'auto' ? '🚀' : form.publish_mode === 'draft' ? '💾' : '⏸',
                label: form.publish_mode === 'auto' ? 'Publish automatically' : form.publish_mode === 'draft' ? 'Save as TikTok draft' : 'Stop at Post button' },
            ].map((step, i) => (
              <div key={i} className="flex items-center gap-2 text-xs text-gray-600">
                <span>{step.icon}</span><span>{step.label}</span>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  )
}
