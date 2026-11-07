import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'
import { executionApi } from '../services/executionApi'
import type { ExecutionStateResponse } from '../types/execution'

const BASE = '/api/v1'

async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

async function apiPostJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

interface ScrapeResult {
  job_id: number
  product_name: string
  tiktok_product_name: string
  image_filename: string
  target_audience: string
  key_benefits: string[]
  content_angles: string[]
  default_angle: string
  pain_points: string[]
  desires: string[]
  triggers: string[]
}

interface Variant {
  angle: string
  hook: string
  video_prompt: string
}

function ChipGroup({ label, options, selected, onChange }: {
  label: string; options: string[]; selected: string[]; onChange: (v: string[]) => void
}) {
  const toggle = (opt: string) =>
    onChange(selected.includes(opt) ? selected.filter(x => x !== opt) : [...selected, opt])
  return (
    <div>
      <p className="text-xs font-semibold text-gray-600 mb-1.5">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {options.map(opt => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
              selected.includes(opt)
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}

interface QuickLaunchResult {
  execution_job_id: number
  content_job_id: number
  product_name: string
  tiktok_product_name: string
  total_steps: number
  status: string
}

type Phase =
  | 'idle'
  | 'scraping'
  | 'scraped'
  | 'generating'
  | 'starting'
  | 'running'
  | 'done'
  | 'error'

const PHASE_LABEL: Record<Phase, string> = {
  idle:       '',
  scraping:   'Scraping produk dari TikTok Shop...',
  scraped:    'Produk dijumpai — pilih angle & avatar',
  generating: 'AI sedang generate content...',
  starting:   'Memulakan pipeline...',
  running:    'Pipeline sedang berjalan...',
  done:       'Selesai!',
  error:      'Ralat',
}

const STEP_COLOR: Record<string, string> = {
  pending:   'bg-gray-200',
  running:   'bg-blue-400 animate-pulse',
  success:   'bg-emerald-400',
  failed:    'bg-red-400',
  skipped:   'bg-gray-300',
  retrying:  'bg-amber-400 animate-pulse',
}

function StepRow({ step, idx }: { step: any; idx: number }) {
  const color = STEP_COLOR[step.status] ?? 'bg-gray-200'
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-xs text-gray-400 w-5 text-right">{idx + 1}</span>
      <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${color}`} />
      <span className="text-sm text-gray-700 flex-1 truncate">{step.label || step.type}</span>
      <span className="text-xs text-gray-400 capitalize">{step.status}</span>
    </div>
  )
}

export default function QuickLaunchPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()
  const onlineDevices = devices.filter(d => d.is_online)

  const [productUrl, setProductUrl] = useState('')
  const [deviceId, setDeviceId] = useState('')
  const [publishMode, setPublishMode] = useState<'manual' | 'auto' | 'draft'>('manual')
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState('')
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null)
  const [selectedAngles, setSelectedAngles] = useState<string[]>([])
  const [selectedPainPoints, setSelectedPainPoints] = useState<string[]>([])
  const [selectedDesires, setSelectedDesires] = useState<string[]>([])
  const [selectedTriggers, setSelectedTriggers] = useState<string[]>([])
  const [variants, setVariants] = useState<Variant[]>([])
  const [activeVariant, setActiveVariant] = useState<Variant | null>(null)
  const [variantsLoading, setVariantsLoading] = useState(false)
  const [result, setResult] = useState<QuickLaunchResult | null>(null)
  const [execState, setExecState] = useState<ExecutionStateResponse | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Avatar / dialogue / own reference image
  const [avatarPresets, setAvatarPresets] = useState<string[]>([])
  const [avatar, setAvatar] = useState('')
  const [customAvatar, setCustomAvatar] = useState('')
  const [dialogue, setDialogue] = useState('')
  const [avatarImageFile, setAvatarImageFile] = useState<File | null>(null)
  const [avatarImagePreview, setAvatarImagePreview] = useState<string>('')

  useEffect(() => {
    fetch(`${BASE}/content/avatars`)
      .then(r => r.json())
      .then(d => setAvatarPresets(d.presets ?? []))
      .catch(() => {})
  }, [])

  const handleAvatarImageChange = (file: File | null) => {
    setAvatarImageFile(file)
    if (avatarImagePreview) URL.revokeObjectURL(avatarImagePreview)
    setAvatarImagePreview(file ? URL.createObjectURL(file) : '')
  }

  // Default: most recently active online device
  useEffect(() => {
    if (!deviceId && onlineDevices.length > 0) {
      const sorted = [...onlineDevices].sort(
        (a, b) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime()
      )
      setDeviceId(sorted[0].device_id)
    }
  }, [onlineDevices, deviceId])

  // Poll execution state while running
  useEffect(() => {
    if (!result || phase !== 'running') return
    const poll = async () => {
      try {
        const state = await executionApi.get(result.execution_job_id) as ExecutionStateResponse
        setExecState(state)
        const status = state.status ?? ''
        if (['COMPLETED', 'READY_FOR_REVIEW', 'FAILED', 'CANCELLED'].includes(status)) {
          setPhase('done')
          if (pollRef.current) clearInterval(pollRef.current)
        }
      } catch { /* ignore */ }
    }
    poll()
    pollRef.current = setInterval(poll, 2500)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [result, phase])

  const handleScrape = async () => {
    if (!productUrl.trim()) { setError('Masukkan URL produk TikTok Shop.'); return }
    setError('')
    setScrapeResult(null)
    setSelectedAngles([])
    setSelectedPainPoints([]); setSelectedDesires([]); setSelectedTriggers([])
    setVariants([]); setActiveVariant(null)

    try {
      setPhase('scraping')
      const res = await apiPostJson<ScrapeResult>('/quicklaunch/scrape', {
        product_url: productUrl.trim(),
      })
      setScrapeResult(res)
      setSelectedAngles(res.default_angle ? [res.default_angle] : [])
      setPhase('scraped')
    } catch (e: any) {
      setError(e.message ?? 'Ralat tidak diketahui.')
      setPhase('error')
    }
  }

  const handleGenerateVariants = async () => {
    if (!scrapeResult || selectedAngles.length === 0) return
    setError('')
    setVariantsLoading(true)
    setActiveVariant(null)
    try {
      const res = await apiPostJson<{ variants: Variant[] }>('/quicklaunch/variants', {
        job_id: scrapeResult.job_id,
        angles: selectedAngles,
        pain_points: selectedPainPoints,
        desires: selectedDesires,
        triggers: selectedTriggers,
        avatar,
        custom_avatar: avatar === 'Custom' ? customAvatar.trim() : '',
        dialogue: dialogue.trim(),
      })
      setVariants(res.variants)
      if (res.variants.length > 0) setActiveVariant(res.variants[0])
    } catch (e: any) {
      setError(e.message ?? 'Ralat generate variasi.')
    } finally {
      setVariantsLoading(false)
    }
  }

  const handleExecute = async () => {
    if (!scrapeResult) return
    if (!deviceId) { setError('Pilih device.'); return }
    setError('')
    setResult(null)
    setExecState(null)

    try {
      setPhase('generating')
      const form = new FormData()
      form.append('job_id', String(scrapeResult.job_id))
      form.append('device_id', deviceId)
      form.append('publish_mode', publishMode)
      form.append('content_angle', activeVariant?.angle || selectedAngles[0] || scrapeResult.default_angle)
      form.append('avatar', avatar)
      form.append('custom_avatar', avatar === 'Custom' ? customAvatar.trim() : '')
      form.append('dialogue', dialogue.trim())
      if (activeVariant) {
        form.append('chosen_hook', activeVariant.hook)
        form.append('chosen_video_prompt', activeVariant.video_prompt)
      }
      if (avatarImageFile) form.append('avatar_image', avatarImageFile)

      const res = await apiPostForm<QuickLaunchResult>('/quicklaunch/start', form)

      setResult(res)
      setPhase('running')
    } catch (e: any) {
      setError(e.message ?? 'Ralat tidak diketahui.')
      setPhase('error')
    }
  }

  const resetAll = () => {
    setPhase('idle')
    setResult(null)
    setExecState(null)
    setScrapeResult(null)
    setSelectedAngles([])
    setSelectedPainPoints([]); setSelectedDesires([]); setSelectedTriggers([])
    setVariants([]); setActiveVariant(null)
    setProductUrl('')
    setAvatar('')
    setCustomAvatar('')
    setDialogue('')
    handleAvatarImageChange(null)
  }

  const jobStatus = execState?.status ?? ''
  const steps: any[] = execState?.steps ?? []
  const currentStep = steps.find(s => s.status === 'running')
  const doneCount = steps.filter(s => s.status === 'success' || s.status === 'skipped').length
  const progress = result ? Math.round((doneCount / result.total_steps) * 100) : 0
  const isRunning = phase === 'scraping' || phase === 'generating' || phase === 'starting' || phase === 'running'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4">
        <button onClick={() => navigate('/')}
          className="text-gray-400 hover:text-gray-700 text-sm">← Back</button>
        <h1 className="text-lg font-bold text-gray-900">Quick Launch</h1>
        <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
          URL → Video → TikTok
        </span>
      </div>

      <div className="flex-1 flex flex-col items-center justify-start px-4 py-8 gap-6 max-w-xl mx-auto w-full">

        {/* Input form */}
        <div className="w-full bg-white rounded-2xl border border-gray-200 shadow-sm p-6 flex flex-col gap-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-sm font-semibold text-gray-700">
                Link Produk TikTok Shop
              </label>
              {scrapeResult && (
                <button
                  onClick={resetAll}
                  disabled={isRunning}
                  className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                >
                  ↺ Scan produk lain
                </button>
              )}
            </div>
            <input
              type="url"
              value={productUrl}
              onChange={e => setProductUrl(e.target.value)}
              placeholder="https://shop.tiktok.com/view/product/..."
              disabled={isRunning || !!scrapeResult}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm
                focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
                disabled:bg-gray-50 disabled:text-gray-400"
            />
            <p className="text-xs text-gray-400 mt-1">
              Hanya TikTok Shop (shop.tiktok.com, vt.tiktok.com)
            </p>
          </div>

          {/* Product preview + angle/trait chips (after scrape) */}
          {scrapeResult && (
            <div className="bg-gray-50 rounded-xl px-4 py-3 space-y-3">
              <div>
                <p className="font-semibold text-gray-800 text-sm truncate">{scrapeResult.product_name}</p>
                <p className="text-gray-500 text-xs mt-0.5">
                  Beg kuning: <span className="font-medium text-gray-700">{scrapeResult.tiktok_product_name}</span>
                </p>
              </div>

              <ChipGroup label="Angle Video (boleh pilih lebih dari 1)"
                options={scrapeResult.content_angles} selected={selectedAngles} onChange={setSelectedAngles} />

              {scrapeResult.pain_points.length > 0 && (
                <ChipGroup label="Pain Points" options={scrapeResult.pain_points}
                  selected={selectedPainPoints} onChange={setSelectedPainPoints} />
              )}
              {scrapeResult.desires.length > 0 && (
                <ChipGroup label="Keinginan" options={scrapeResult.desires}
                  selected={selectedDesires} onChange={setSelectedDesires} />
              )}
              {scrapeResult.triggers.length > 0 && (
                <ChipGroup label="Trigger Beli" options={scrapeResult.triggers}
                  selected={selectedTriggers} onChange={setSelectedTriggers} />
              )}
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1.5">Device</label>
            <select
              value={deviceId}
              onChange={e => setDeviceId(e.target.value)}
              disabled={isRunning}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm
                focus:outline-none focus:ring-2 focus:ring-blue-400
                disabled:bg-gray-50 disabled:text-gray-400"
            >
              {onlineDevices.length === 0 && (
                <option value="">Tiada device online</option>
              )}
              {onlineDevices.map(d => (
                <option key={d.device_id} value={d.device_id}>
                  {d.device_name
                    ? `${d.device_name} (${d.adb_address || d.device_id})`
                    : (d.adb_address || d.device_id)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Mod Post</label>
            <div className="flex gap-3">
              {(['manual', 'auto', 'draft'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => !isRunning && setPublishMode(mode)}
                  className={`flex-1 py-2.5 rounded-xl text-sm font-medium border transition-colors
                    ${publishMode === mode
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                    } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  {mode === 'manual' ? '✋ Manual (semak dulu)' : mode === 'auto' ? '🚀 Auto Post' : '💾 Save Draft (VPN)'}
                </button>
              ))}
            </div>
          </div>

          {/* Avatar (optional) */}
          <div className="pt-1 border-t border-gray-100">
            <label className="block text-sm font-semibold text-gray-700 mb-1.5 mt-3">
              Avatar <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <select
              value={avatar}
              onChange={e => setAvatar(e.target.value)}
              disabled={isRunning}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm
                focus:outline-none focus:ring-2 focus:ring-blue-400
                disabled:bg-gray-50 disabled:text-gray-400"
            >
              <option value="">Tiada avatar — fokus produk sahaja</option>
              {avatarPresets.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>

            {avatar === 'Custom' && (
              <textarea
                value={customAvatar}
                onChange={e => setCustomAvatar(e.target.value)}
                disabled={isRunning}
                placeholder="Describe avatar sendiri (contoh: wanita Malaysia 20-an, hijab warna pastel, suasana rumah)"
                rows={2}
                className="w-full mt-2 border border-gray-300 rounded-xl px-4 py-3 text-sm
                  focus:outline-none focus:ring-2 focus:ring-blue-400
                  disabled:bg-gray-50 disabled:text-gray-400 resize-none"
              />
            )}
          </div>

          {/* Dialogue */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1.5">
              Dialog Avatar <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={dialogue}
              onChange={e => setDialogue(e.target.value)}
              disabled={isRunning}
              placeholder='Contoh: "Korang confirm pernah rasa masalah ni kan..."'
              rows={2}
              className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm
                focus:outline-none focus:ring-2 focus:ring-blue-400
                disabled:bg-gray-50 disabled:text-gray-400 resize-none"
            />
          </div>

          {/* Own reference image */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1.5">
              Gambar Avatar Sendiri <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <p className="text-xs text-gray-400 mb-2">
              Kalau diisi, AI akan guna gambar ni + gambar produk sebagai reference — bukan gambar pertama scrape sahaja.
            </p>
            {avatarImagePreview ? (
              <div className="flex items-center gap-3">
                <img src={avatarImagePreview} alt="Avatar reference"
                  className="w-16 h-16 rounded-xl object-cover border border-gray-200" />
                <button
                  onClick={() => handleAvatarImageChange(null)}
                  disabled={isRunning}
                  className="text-xs text-red-600 hover:underline disabled:opacity-50"
                >
                  Buang gambar
                </button>
              </div>
            ) : (
              <input
                type="file"
                accept="image/*"
                disabled={isRunning}
                onChange={e => handleAvatarImageChange(e.target.files?.[0] ?? null)}
                className="w-full text-sm text-gray-600 file:mr-3 file:py-2 file:px-4
                  file:rounded-xl file:border-0 file:text-sm file:font-medium
                  file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100
                  disabled:opacity-50"
              />
            )}
          </div>

          {/* Generate + pick a variant (optional — Execute falls back to auto if skipped) */}
          {scrapeResult && (
            <div>
              <button
                onClick={handleGenerateVariants}
                disabled={isRunning || variantsLoading || selectedAngles.length === 0}
                className="w-full py-2.5 rounded-xl text-sm font-semibold border border-blue-300 text-blue-700
                  hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {variantsLoading
                  ? `⏳ Generating ${selectedAngles.length} variasi...`
                  : `✨ Generate ${selectedAngles.length || ''} Variasi`}
              </button>

              {variants.length > 0 && (
                <div className="mt-3 space-y-2">
                  {variants.map((v, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setActiveVariant(v)}
                      disabled={isRunning}
                      className={`w-full text-left rounded-xl border p-3 transition-colors ${
                        activeVariant === v
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 bg-white hover:border-blue-300'
                      } disabled:opacity-50`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-semibold text-blue-700">{v.angle}</span>
                        {activeVariant === v && (
                          <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">Dipilih</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-700 font-medium mb-1">{v.hook}</p>
                      <p className="text-xs text-gray-400 line-clamp-2">{v.video_prompt}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {!scrapeResult ? (
            <button
              onClick={handleScrape}
              disabled={isRunning || !productUrl.trim()}
              className="w-full py-3.5 rounded-xl font-bold text-white text-sm
                bg-gradient-to-r from-blue-600 to-indigo-600
                hover:from-blue-700 hover:to-indigo-700
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all shadow-md hover:shadow-lg"
            >
              {phase === 'scraping' ? '⏳ Scraping...' : '🔍 Scan Produk'}
            </button>
          ) : (
            <button
              onClick={handleExecute}
              disabled={isRunning || !deviceId}
              className="w-full py-3.5 rounded-xl font-bold text-white text-sm
                bg-gradient-to-r from-blue-600 to-indigo-600
                hover:from-blue-700 hover:to-indigo-700
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all shadow-md hover:shadow-lg"
            >
              {isRunning ? '⏳ Sedang berjalan...' : '▶ Execute'}
            </button>
          )}
        </div>

        {/* Phase status */}
        {(phase === 'generating' || phase === 'starting' || phase === 'running' || phase === 'done' || (phase === 'error' && result)) && (
          <div className="w-full bg-white rounded-2xl border border-gray-200 shadow-sm p-5">

            {/* Phase label */}
            <div className="flex items-center gap-3 mb-4">
              {isRunning && phase !== 'running' && (
                <span className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
              )}
              <span className="text-sm font-semibold text-gray-800">
                {PHASE_LABEL[phase]}
              </span>
            </div>

            {/* Product info (once scraped) */}
            {result && (
              <div className="bg-gray-50 rounded-xl px-4 py-3 mb-4 text-sm">
                <p className="font-semibold text-gray-800 truncate">{result.product_name}</p>
                <p className="text-gray-500 text-xs mt-0.5">
                  Beg kuning: <span className="font-medium text-gray-700">{result.tiktok_product_name}</span>
                </p>
              </div>
            )}

            {/* Progress bar */}
            {result && (
              <div className="mb-4">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>{doneCount}/{result.total_steps} langkah</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                {currentStep && (
                  <p className="text-xs text-blue-600 mt-1.5 font-medium">
                    ▶ {currentStep.label || currentStep.type}
                  </p>
                )}
              </div>
            )}

            {/* Job status badge */}
            {jobStatus && (
              <div className="mb-3">
                <span className={`text-xs font-bold px-2.5 py-1 rounded-full
                  ${jobStatus === 'COMPLETED' || jobStatus === 'READY_FOR_REVIEW'
                    ? 'bg-emerald-100 text-emerald-700'
                    : jobStatus === 'FAILED'
                    ? 'bg-red-100 text-red-700'
                    : 'bg-blue-100 text-blue-700'
                  }`}>
                  {jobStatus}
                </span>
              </div>
            )}

            {/* Step list */}
            {steps.length > 0 && (
              <div className="border border-gray-100 rounded-xl overflow-hidden">
                {steps.map((s, i) => <StepRow key={i} step={s} idx={i} />)}
              </div>
            )}

            {/* Done actions */}
            {phase === 'done' && (
              <div className="mt-4 flex gap-3">
                <button
                  onClick={() => navigate('/execution')}
                  className="flex-1 py-2.5 rounded-xl border border-gray-300 text-sm text-gray-700
                    hover:bg-gray-50 font-medium"
                >
                  Lihat Execution Log
                </button>
                <button
                  onClick={() => {
                    resetAll()
                  }}
                  className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white text-sm
                    font-medium hover:bg-blue-700"
                >
                  Launch Baru
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
