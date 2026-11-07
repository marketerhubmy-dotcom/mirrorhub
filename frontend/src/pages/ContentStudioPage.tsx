import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'
import { contentApi } from '../services/contentApi'
import type { ContentJob, ContentJobUpdate, WorkflowRequest } from '../types/content'
import {
  STATUS_LABEL,
  STATUS_COLOR,
  STATUS_PIPELINE,
} from '../types/content'

const DURATIONS = ['8s', '15s', '30s', '60s']
const PLATFORMS = [
  { value: 'ytcreate', label: 'YT Create → TikTok' },
  { value: 'tiktok', label: 'TikTok Direct' },
  { value: 'capcut', label: 'CapCut' },
  { value: 'instagram', label: 'Instagram' },
]

// ── Empty form state ──────────────────────────────────────────────────────────

function emptyForm() {
  return {
    title: '',
    topic: '',
    objective: '',
    audience: '',
    product: '',
    duration: '8s',
    visual_style: '',
    hook: '',
    story: '',
    cta: '',
    video_prompt: '',
    caption: '',
    hashtags: [] as string[],
  }
}

type Form = ReturnType<typeof emptyForm>

function jobToForm(job: ContentJob): Form {
  return {
    title: job.title,
    topic: job.topic,
    objective: job.objective,
    audience: job.audience,
    product: job.product,
    duration: job.duration,
    visual_style: job.visual_style,
    hook: job.hook,
    story: job.story,
    cta: job.cta,
    video_prompt: job.video_prompt,
    caption: job.caption,
    hashtags: job.hashtags,
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ContentJob['status'] }) {
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_COLOR[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  )
}

function Field({
  label, value, onChange, placeholder, rows = 2, mono = false,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rows?: number
  mono?: boolean
}) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">{label}</p>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className={`w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none
          focus:ring-2 focus:ring-indigo-500 resize-none
          ${mono ? 'font-mono text-xs bg-indigo-50 border-indigo-200' : 'bg-white'}`}
      />
    </div>
  )
}

function PipelineTrack({ status }: { status: ContentJob['status'] }) {
  const currentIndex = STATUS_PIPELINE.indexOf(status)
  return (
    <div className="space-y-1">
      {STATUS_PIPELINE.map((s, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        return (
          <div key={s} className="flex items-center gap-2.5">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0
              ${done ? 'bg-emerald-500 text-white' : active ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-400'}`}>
              {done ? '✓' : i + 1}
            </div>
            <span className={`text-xs ${active ? 'font-semibold text-indigo-700' : done ? 'text-gray-400 line-through' : 'text-gray-500'}`}>
              {STATUS_LABEL[s]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Main Page ───���─────────────────────────────────────────────────────────────

export default function ContentStudioPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()
  const onlineDevices = devices.filter(d => d.is_online && d.adb_address)

  const [jobs, setJobs] = useState<ContentJob[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [form, setForm] = useState<Form>(emptyForm())
  const [imageFiles, setImageFiles] = useState<File[]>([])
  const imageInputRef = useRef<HTMLInputElement>(null)

  // UI states
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')

  // Run panel
  const [deviceId, setDeviceId] = useState('')
  const [platform, setPlatform] = useState('ytcreate')
  const [postType, setPostType] = useState<'post_now' | 'draft' | 'schedule'>('draft')
  const [scheduleTime, setScheduleTime] = useState('')

  const selectedJob = jobs.find(j => j.id === selectedId) ?? null

  useEffect(() => {
    contentApi.list().then(setJobs).catch(() => {})
  }, [])

  useEffect(() => {
    if (onlineDevices.length > 0 && !deviceId) setDeviceId(onlineDevices[0].device_id)
  }, [onlineDevices, deviceId])

  const selectJob = (job: ContentJob) => {
    setSelectedId(job.id)
    setForm(jobToForm(job))
    setImageFiles([])
    setRunError('')
  }

  const createNew = async () => {
    try {
      const job = await contentApi.create({ title: 'Untitled Content' })
      setJobs(prev => [job, ...prev])
      selectJob(job)
    } catch (e) {
      alert('Gagal cipta: ' + (e as Error).message)
    }
  }

  const saveForm = async () => {
    if (!selectedId) return
    setSaving(true)
    try {
      const patch: ContentJobUpdate = {
        title: form.title,
        topic: form.topic,
        objective: form.objective,
        audience: form.audience,
        product: form.product,
        duration: form.duration,
        visual_style: form.visual_style,
        hook: form.hook,
        story: form.story,
        cta: form.cta,
        video_prompt: form.video_prompt,
        caption: form.caption,
        hashtags: form.hashtags,
      }
      const updated = await contentApi.update(selectedId, patch)
      setJobs(prev => prev.map(j => (j.id === selectedId ? updated : j)))
    } catch (e) {
      alert('Gagal simpan: ' + (e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const uploadPendingImages = async (jobId: number) => {
    let updated: ContentJob | null = null
    for (const file of imageFiles) {
      updated = await contentApi.uploadImage(jobId, file)
    }
    if (updated) {
      setJobs(prev => prev.map(j => (j.id === jobId ? updated! : j)))
      setImageFiles([])
    }
  }

  const generate = async () => {
    if (!selectedId) return
    setGenerating(true)
    try {
      // save current form state + upload any pending images first
      await saveForm()
      if (imageFiles.length > 0) await uploadPendingImages(selectedId)

      const updated = await contentApi.generate(selectedId)
      setJobs(prev => prev.map(j => (j.id === selectedId ? updated : j)))
      setForm(jobToForm(updated))
    } catch (e) {
      alert('Gagal generate: ' + (e as Error).message)
    } finally {
      setGenerating(false)
    }
  }

  const removeImage = async (filename: string) => {
    if (!selectedId) return
    try {
      const updated = await contentApi.removeImage(selectedId, filename)
      setJobs(prev => prev.map(j => (j.id === selectedId ? updated : j)))
    } catch (e) {
      alert('Gagal remove: ' + (e as Error).message)
    }
  }

  const runAutomation = async () => {
    if (!selectedId || !deviceId) return
    setRunning(true)
    setRunError('')
    try {
      // save before running
      await saveForm()
      if (imageFiles.length > 0) await uploadPendingImages(selectedId)

      const req: WorkflowRequest = {
        device_id: deviceId,
        platform,
        post_type: postType,
        schedule_time: postType === 'schedule' ? scheduleTime : null,
      }
      await contentApi.run(selectedId, req)
      // Refresh job to see status change
      const updated = await contentApi.get(selectedId)
      setJobs(prev => prev.map(j => (j.id === selectedId ? updated : j)))
    } catch (e) {
      setRunError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const deleteJob = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete content ini?')) return
    await contentApi.delete(id)
    setJobs(prev => prev.filter(j => j.id !== id))
    if (selectedId === id) { setSelectedId(null); setForm(emptyForm()) }
  }

  const setField = (key: keyof Form) => (val: string) =>
    setForm(prev => ({ ...prev, [key]: val }))

  const hasGenerated = selectedJob
    ? !!(selectedJob.hook || selectedJob.video_prompt)
    : false

  const canRun = hasGenerated && (selectedJob?.reference_images.length ?? 0) > 0

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">

      {/* ── Header ── */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4 shrink-0">
        <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 text-sm">
          ← Back
        </button>
        <h1 className="text-lg font-bold text-gray-900">Content Studio</h1>
        <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full font-medium">
          AI Pipeline
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => navigate('/automation')}
            className="px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:border-gray-300"
          >
            ⚡ Automation
          </button>
          <button
            onClick={createNew}
            className="px-4 py-1.5 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700"
          >
            + New Content
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">

        {/* ══ LEFT: Content List ═══════════════════════════════════════════════ */}
        <aside className="w-56 shrink-0 border-r border-gray-200 bg-white flex flex-col overflow-hidden">
          <div className="px-3 py-3 border-b border-gray-100">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Content ({jobs.length})
            </p>
          </div>

          <div className="flex-1 overflow-y-auto py-1">
            {jobs.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-8 px-4">
                Belum ada content. Klik "+ New Content" untuk mula.
              </p>
            )}
            {jobs.map(job => (
              <div
                key={job.id}
                onClick={() => selectJob(job)}
                className={`mx-2 my-0.5 px-3 py-2.5 rounded-lg cursor-pointer transition-colors flex items-start gap-2 ${
                  selectedId === job.id
                    ? 'bg-violet-50 border border-violet-200'
                    : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{job.title}</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${STATUS_COLOR[job.status]}`}>
                      {STATUS_LABEL[job.status]}
                    </span>
                  </div>
                </div>
                <button
                  onClick={e => deleteJob(job.id, e)}
                  className="text-gray-300 hover:text-red-400 text-xs shrink-0 mt-0.5"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </aside>

        {/* ══ CENTER: Editor ═══════════════════════════════════════════════════ */}
        <main className="flex-1 overflow-y-auto">
          {!selectedJob ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <p className="text-4xl mb-3">✨</p>
              <p className="text-gray-700 font-semibold">Pilih atau buat content baru</p>
              <p className="text-gray-400 text-sm mt-1">
                Content Pipeline: Idea → Brief → Prompt → Caption → Hashtag → Automation
              </p>
              <button
                onClick={createNew}
                className="mt-5 px-6 py-2.5 bg-violet-600 text-white rounded-xl font-medium hover:bg-violet-700"
              >
                + New Content
              </button>
            </div>
          ) : (
            <div className="p-4 space-y-4 max-w-2xl">

              {/* Title */}
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Content</p>
                  <StatusBadge status={selectedJob.status} />
                </div>
                <input
                  value={form.title}
                  onChange={e => setField('title')(e.target.value)}
                  placeholder="Tajuk content..."
                  className="w-full text-lg font-semibold text-gray-900 outline-none border-b border-gray-100
                    pb-2 focus:border-indigo-400 bg-transparent"
                />
              </div>

              {/* Input fields */}
              <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Input</p>

                <Field
                  label="Topik / Idea"
                  value={form.topic}
                  onChange={setField('topic')}
                  placeholder="Apa yang video ni pasal? Cth: Produk kulit wajah untuk kulit berminyak"
                  rows={2}
                />
                <Field
                  label="Objektif"
                  value={form.objective}
                  onChange={setField('objective')}
                  placeholder="Apa tujuan video ni? Cth: Drive traffic ke link produk, awareness, viral"
                  rows={2}
                />
                <Field
                  label="Target Audiens"
                  value={form.audience}
                  onChange={setField('audience')}
                  placeholder="Siapa yang tengok? Cth: Wanita 25-34, ada masalah kulit berminyak"
                  rows={2}
                />
                <Field
                  label="Produk / Brand"
                  value={form.product}
                  onChange={setField('product')}
                  placeholder="Nama produk dan info ringkas"
                  rows={1}
                />

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                      Durasi Video
                    </p>
                    <div className="flex gap-1.5 flex-wrap">
                      {DURATIONS.map(d => (
                        <button
                          key={d}
                          onClick={() => setForm(p => ({ ...p, duration: d }))}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                            form.duration === d
                              ? 'bg-indigo-600 text-white border-indigo-600'
                              : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                          }`}
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                  </div>

                  <Field
                    label="Gaya Visual"
                    value={form.visual_style}
                    onChange={setField('visual_style')}
                    placeholder="Cth: cinematic, lifestyle, close-up"
                    rows={1}
                  />
                </div>
              </div>

              {/* Reference Images */}
              <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Reference Images
                  </p>
                  <button
                    onClick={() => imageInputRef.current?.click()}
                    className="text-xs text-indigo-600 hover:text-indigo-800"
                  >
                    + Tambah
                  </button>
                  <input
                    ref={imageInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    onChange={e => {
                      const files = Array.from(e.target.files ?? [])
                      setImageFiles(prev => [...prev, ...files])
                    }}
                  />
                </div>

                {/* Saved images */}
                {selectedJob.reference_images.length === 0 && imageFiles.length === 0 && (
                  <label
                    className="flex flex-col items-center border-2 border-dashed border-gray-200
                      rounded-xl p-4 cursor-pointer hover:border-indigo-300 text-center"
                    onClick={() => imageInputRef.current?.click()}
                  >
                    <span className="text-2xl">����️</span>
                    <p className="text-xs text-gray-400 mt-1">Upload gambar produk / reference</p>
                    <p className="text-xs text-gray-300">Diperlukan untuk automation</p>
                  </label>
                )}

                {selectedJob.reference_images.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {selectedJob.reference_images.map(fn => (
                      <div key={fn} className="relative group">
                        <img
                          src={`/uploads/${fn}`}
                          alt=""
                          className="w-16 h-16 object-cover rounded-lg border border-gray-200"
                        />
                        <button
                          onClick={() => removeImage(fn)}
                          className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white
                            rounded-full text-xs items-center justify-center hidden group-hover:flex"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {imageFiles.length > 0 && (
                  <div className="space-y-1">
                    {imageFiles.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                        <span className="text-amber-500">⏳</span>
                        <span className="truncate">{f.name}</span>
                        <span className="text-gray-300">(akan upload bila Generate / Run)</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Generate button */}
              <button
                onClick={generate}
                disabled={generating || !form.topic.trim()}
                className="w-full py-3 bg-violet-600 text-white rounded-xl font-semibold
                  hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {generating
                  ? '⏳ AI sedang generate...'
                  : '✨ Generate Brief + Prompt + Caption + Hashtag'}
              </button>

              {/* Generated fields — shown once there's AI output */}
              {hasGenerated && (
                <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      Generated — editable
                    </p>
                    <button
                      onClick={saveForm}
                      disabled={saving}
                      className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
                    >
                      {saving ? 'Saving...' : '💾 Save'}
                    </button>
                  </div>

                  <Field label="Hook" value={form.hook} onChange={setField('hook')} rows={2} />
                  <Field label="Story" value={form.story} onChange={setField('story')} rows={3} />
                  <Field label="CTA" value={form.cta} onChange={setField('cta')} rows={1} />
                  <Field
                    label="Video Prompt"
                    value={form.video_prompt}
                    onChange={setField('video_prompt')}
                    placeholder="Video prompt untuk YT Create / AI video generator..."
                    rows={4}
                    mono
                  />
                  <Field
                    label="Caption TikTok"
                    value={form.caption}
                    onChange={setField('caption')}
                    rows={3}
                  />

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                      Hashtags
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {form.hashtags.map((tag, i) => (
                        <span
                          key={i}
                          className="bg-indigo-50 text-indigo-700 text-xs px-2 py-1 rounded-full border border-indigo-100"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                    <textarea
                      value={form.hashtags.join(' ')}
                      onChange={e =>
                        setForm(prev => ({
                          ...prev,
                          hashtags: e.target.value
                            .split(/\s+/)
                            .filter(t => t.startsWith('#')),
                        }))
                      }
                      placeholder="#hashtag1 #hashtag2 ..."
                      rows={2}
                      className="w-full mt-2 border border-gray-200 rounded-lg px-3 py-2 text-xs
                        font-mono outline-none focus:ring-2 focus:ring-indigo-500 resize-none bg-white"
                    />
                  </div>

                  <button
                    onClick={saveForm}
                    disabled={saving}
                    className="w-full py-2 border border-indigo-300 text-indigo-600 rounded-lg
                      text-sm font-medium hover:bg-indigo-50 disabled:opacity-50"
                  >
                    {saving ? '...' : '💾 Simpan semua perubahan'}
                  </button>
                </div>
              )}

              <div className="pb-4" />
            </div>
          )}
        </main>

        {/* ══ RIGHT: Generation Preview + Run ═════════════════════════════════ */}
        <aside className="w-72 shrink-0 border-l border-gray-200 bg-white flex flex-col overflow-hidden">

          {!selectedJob ? (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-xs text-gray-300 text-center px-4">
                Pilih content untuk lihat preview
              </p>
            </div>
          ) : (
            <>
              {/* Status pipeline */}
              <div className="p-4 border-b border-gray-100">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Pipeline Status
                </p>
                <PipelineTrack status={selectedJob.status} />
              </div>

              {/* Preview */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {selectedJob.hook && (
                  <div className="bg-blue-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-blue-600 mb-1">Hook</p>
                    <p className="text-xs text-gray-700">{selectedJob.hook}</p>
                  </div>
                )}
                {selectedJob.story && (
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-gray-500 mb-1">Story</p>
                    <p className="text-xs text-gray-700">{selectedJob.story}</p>
                  </div>
                )}
                {selectedJob.cta && (
                  <div className="bg-emerald-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-emerald-600 mb-1">CTA</p>
                    <p className="text-xs text-gray-700">{selectedJob.cta}</p>
                  </div>
                )}
                {selectedJob.video_prompt && (
                  <div className="bg-indigo-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-indigo-600 mb-1">Video Prompt</p>
                    <p className="text-xs text-gray-700 font-mono leading-relaxed">
                      {selectedJob.video_prompt}
                    </p>
                  </div>
                )}
                {selectedJob.caption && (
                  <div className="bg-violet-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-violet-600 mb-1">Caption</p>
                    <p className="text-xs text-gray-700 whitespace-pre-line">{selectedJob.caption}</p>
                  </div>
                )}
                {selectedJob.hashtags.length > 0 && (
                  <div className="bg-amber-50 rounded-lg p-3">
                    <p className="text-xs font-semibold text-amber-600 mb-1">Hashtags</p>
                    <p className="text-xs text-gray-600 leading-relaxed">
                      {selectedJob.hashtags.join(' ')}
                    </p>
                  </div>
                )}

                {!hasGenerated && (
                  <p className="text-xs text-gray-300 text-center py-6">
                    Klik Generate untuk lihat output AI di sini
                  </p>
                )}
              </div>

              {/* Run automation */}
              <div className="border-t border-gray-100 p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Hantar ke Automation
                </p>

                {!canRun && (
                  <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
                    {!hasGenerated
                      ? '⚠ Generate content dulu'
                      : '⚠ Tambah reference image dulu'}
                  </p>
                )}

                {/* Device */}
                {onlineDevices.length === 0 ? (
                  <p className="text-xs text-red-500">Tiada phone online</p>
                ) : (
                  <select
                    value={deviceId}
                    onChange={e => setDeviceId(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs outline-none
                      focus:ring-2 focus:ring-indigo-500"
                  >
                    {onlineDevices.map(d => (
                      <option key={d.device_id} value={d.device_id}>{d.device_name}</option>
                    ))}
                  </select>
                )}

                {/* Platform */}
                <select
                  value={platform}
                  onChange={e => setPlatform(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs outline-none
                    focus:ring-2 focus:ring-indigo-500"
                >
                  {PLATFORMS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>

                {/* Post type */}
                <div className="grid grid-cols-3 gap-1">
                  {(['post_now', 'draft', 'schedule'] as const).map(pt => (
                    <button
                      key={pt}
                      onClick={() => setPostType(pt)}
                      className={`py-1.5 rounded text-xs font-medium border transition-colors ${
                        postType === pt
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                      }`}
                    >
                      {pt === 'post_now' ? '🚀 Post' : pt === 'draft' ? '📋 Draft' : '⏰ Jadual'}
                    </button>
                  ))}
                </div>

                {postType === 'schedule' && (
                  <input
                    type="datetime-local"
                    value={scheduleTime}
                    onChange={e => setScheduleTime(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs outline-none"
                  />
                )}

                {runError && (
                  <p className="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">{runError}</p>
                )}

                <button
                  onClick={runAutomation}
                  disabled={running || !canRun || !deviceId}
                  className="w-full py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-semibold
                    hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {running ? '⏳ Running...' : '▶ Run Automation'}
                </button>

                <p className="text-xs text-gray-300 text-center">
                  Tengok Automation page untuk log
                </p>
              </div>
            </>
          )}
        </aside>

      </div>
    </div>
  )
}
