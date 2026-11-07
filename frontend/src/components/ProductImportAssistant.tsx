/**
 * ProductImportAssistant — MVP 0.4
 *
 * Three tabs:
 *   Saved Product  → dropdown → review card → Apply
 *   Product Link   → fetch → blocked fallback → switch to Text tab
 *   Text / Screenshot → paste text + screenshot upload → analyze → review card → Apply
 *
 * All paths produce a ProductDraft reviewed before applying to the pipeline.
 */
import { useState, useEffect, useRef } from 'react'
import { productApi } from '../services/productApi'
import type { SavedProduct, ProductDraft, ProductConflict } from '../types/product'
import { savedToProductDraft } from '../types/product'

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'saved' | 'link' | 'text'

type State =
  | 'idle'
  | 'fetching_link'
  | 'link_blocked'
  | 'analyzing_text'
  | 'analyzing_images'
  | 'draft_ready'
  | 'editing'
  | 'saving'
  | 'saved'
  | 'error'

export interface PipelineFields {
  product: string
  audience: string
  topic: string
  objective: string
  visual_style: string
  tiktok_product_name: string
}

interface Props {
  onApply: (fields: Partial<PipelineFields>, imageFilename: string | null) => void
}

// ── Small UI helpers ──────────────────────────────────────────────────────────

function TabBtn({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
        active
          ? 'bg-violet-600 text-white'
          : 'text-gray-500 hover:text-gray-800 hover:bg-gray-100'
      }`}
    >
      {label}
    </button>
  )
}

function Pill({ label, color = 'gray' }: { label: string; color?: 'gray' | 'violet' | 'amber' | 'emerald' }) {
  const cls = {
    gray: 'bg-gray-100 text-gray-600',
    violet: 'bg-violet-100 text-violet-700',
    amber: 'bg-amber-100 text-amber-700',
    emerald: 'bg-emerald-100 text-emerald-700',
  }[color]
  return <span className={`text-xs px-2 py-0.5 rounded-full ${cls}`}>{label}</span>
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.7 ? 'bg-emerald-500' : value >= 0.4 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

// ── Draft editor — allows editing all fields before Apply ─────────────────────

function DraftEditor({
  draft,
  onChange,
}: {
  draft: ProductDraft
  onChange: (d: ProductDraft) => void
}) {
  function field(key: keyof ProductDraft) {
    return {
      value: (draft[key] as string) ?? '',
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        onChange({ ...draft, [key]: e.target.value }),
    }
  }

  function listField(key: keyof ProductDraft) {
    const arr = (draft[key] as string[]) ?? []
    return {
      value: arr.join('\n'),
      onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) =>
        onChange({ ...draft, [key]: e.target.value.split('\n').filter(Boolean) }),
    }
  }

  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-gray-500 mb-1">Nama Produk</p>
          <input {...field('product_name')}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
              focus:ring-2 focus:ring-violet-500" />
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Kedai</p>
          <input {...field('shop_name')}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
              focus:ring-2 focus:ring-violet-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-gray-500 mb-1">Harga</p>
          <input {...field('price')}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
              focus:ring-2 focus:ring-violet-500" />
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Nama TikTok Shop</p>
          <input {...field('tiktok_product_name')}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
              focus:ring-2 focus:ring-violet-500" />
        </div>
      </div>

      <div>
        <p className="text-xs text-gray-500 mb-1">Deskripsi Produk</p>
        <textarea {...field('product_description')} rows={3}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
            focus:ring-2 focus:ring-violet-500 resize-none" />
      </div>

      <div>
        <p className="text-xs text-gray-500 mb-1">Target Audience (pilihan pertama)</p>
        <input {...field('target_audience')}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
            focus:ring-2 focus:ring-violet-500" />
      </div>

      <div>
        <p className="text-xs text-gray-500 mb-1">Manfaat Utama (satu per baris)</p>
        <textarea {...listField('key_benefits')} rows={4}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm font-mono
            outline-none focus:ring-2 focus:ring-violet-500 resize-none" />
      </div>

      <div>
        <p className="text-xs text-gray-500 mb-1">Content Angles (satu per baris)</p>
        <textarea {...listField('suggested_content_angles')} rows={4}
          className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm font-mono
            outline-none focus:ring-2 focus:ring-violet-500 resize-none" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-gray-500 mb-1">Video Objective</p>
          <input {...field('default_video_objective')}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
              focus:ring-2 focus:ring-violet-500" />
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Video Style</p>
          <input {...field('default_video_style')}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm outline-none
              focus:ring-2 focus:ring-violet-500" />
        </div>
      </div>
    </div>
  )
}

// ── Review card ───────────────────────────────────────────────────────────────

function ReviewCard({
  draft,
  onApply,
  onSave,
  onCancel,
  saving,
  savedMsg,
  existingId,
}: {
  draft: ProductDraft
  onApply: (d: ProductDraft, refImage: string | null) => void
  onSave: (d: ProductDraft) => void
  onCancel: () => void
  saving: boolean
  savedMsg: string
  existingId?: number | null
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [editedDraft, setEditedDraft] = useState<ProductDraft>(draft)
  const [selectedAudience, setSelectedAudience] = useState(draft.target_audience)
  const [selectedAngle, setSelectedAngle] = useState(draft.suggested_content_angles[0] ?? '')
  const [selectedRefImage, setSelectedRefImage] = useState<string | null>(
    draft.source_images[0] ?? null
  )

  // Keep local state in sync if draft changes (e.g. after re-fetch)
  useEffect(() => {
    setEditedDraft(draft)
    setSelectedAudience(draft.target_audience)
    setSelectedAngle(draft.suggested_content_angles[0] ?? '')
    setSelectedRefImage(draft.source_images[0] ?? null)
  }, [draft])

  const activeDraft = isEditing ? editedDraft : draft

  function handleApply() {
    const d: ProductDraft = {
      ...activeDraft,
      target_audience: selectedAudience || activeDraft.target_audience,
      suggested_content_angles: selectedAngle
        ? [selectedAngle, ...activeDraft.suggested_content_angles.filter(a => a !== selectedAngle)]
        : activeDraft.suggested_content_angles,
    }
    onApply(d, selectedRefImage)
  }

  return (
    <div className="border border-violet-200 rounded-xl bg-white overflow-hidden">
      {/* Header */}
      <div className="bg-violet-50 px-4 py-2.5 flex items-center justify-between border-b border-violet-200">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-violet-700 uppercase tracking-wide">
            Product Analysis
          </span>
          {activeDraft.source_type !== 'saved' && (
            <Pill
              label={
                activeDraft.source_type === 'url' ? 'Link'
                : activeDraft.source_type === 'text' ? 'Text'
                : 'Screenshot'
              }
              color="violet"
            />
          )}
        </div>
        <button onClick={onCancel} className="text-gray-400 hover:text-gray-700 text-lg leading-none">×</button>
      </div>

      <div className="p-4 space-y-4">

        {/* Editing mode */}
        {isEditing ? (
          <>
            <DraftEditor draft={editedDraft} onChange={setEditedDraft} />
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => setIsEditing(false)}
                className="px-4 py-2 bg-violet-600 text-white text-sm font-semibold rounded-lg
                  hover:bg-violet-700"
              >
                Done Editing
              </button>
              <button
                onClick={() => { setEditedDraft(draft); setIsEditing(false) }}
                className="px-3 py-2 text-sm border border-gray-200 text-gray-500 rounded-lg
                  hover:bg-gray-50"
              >
                Reset
              </button>
            </div>
          </>
        ) : (
          <>
            {/* Product summary */}
            <div className="flex items-start gap-3">
              {activeDraft.source_images.length > 0 && (
                <img
                  src={`/uploads/${activeDraft.source_images[0]}`}
                  alt=""
                  className="w-14 h-14 object-cover rounded-lg border border-gray-200 shrink-0"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              )}
              <div className="min-w-0">
                <p className="font-semibold text-gray-900 text-sm leading-tight">
                  {activeDraft.product_name || '—'}
                </p>
                {activeDraft.shop_name && (
                  <p className="text-xs text-gray-500 mt-0.5">{activeDraft.shop_name}</p>
                )}
                {activeDraft.price && (
                  <p className="text-xs font-medium text-emerald-700 mt-0.5">{activeDraft.price}</p>
                )}
              </div>
            </div>

            {/* Confidence */}
            <div>
              <p className="text-xs text-gray-500 mb-1">Confidence</p>
              <ConfidenceBar value={activeDraft.confidence} />
            </div>

            {/* Warnings */}
            {activeDraft.warnings.length > 0 && (
              <div className="bg-amber-50 rounded-lg px-3 py-2 space-y-1">
                {activeDraft.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-amber-700">⚠ {w}</p>
                ))}
              </div>
            )}

            {activeDraft.vision_error && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                <p className="text-xs text-amber-700">
                  Vision gagal: {activeDraft.vision_error}<br />
                  <span className="text-gray-500">
                    Gambar disimpan — boleh pilih sebagai reference image di bawah.
                    Salin teks produk dan gunakan tab "Text" untuk analisis.
                  </span>
                </p>
              </div>
            )}

            {/* Target audience dropdown */}
            {(activeDraft.target_audience_options.length > 0 || activeDraft.target_audience) && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Target Audience</p>
                <select
                  value={selectedAudience}
                  onChange={e => setSelectedAudience(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white
                    outline-none focus:ring-2 focus:ring-violet-500"
                >
                  {(activeDraft.target_audience_options.length
                    ? activeDraft.target_audience_options
                    : [activeDraft.target_audience]
                  ).map((a, i) => (
                    <option key={i} value={a}>{a}</option>
                  ))}
                  <option value="">— custom (edit di form) —</option>
                </select>
              </div>
            )}

            {/* Content angle dropdown */}
            {activeDraft.suggested_content_angles.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Content Angle</p>
                <select
                  value={selectedAngle}
                  onChange={e => setSelectedAngle(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white
                    outline-none focus:ring-2 focus:ring-violet-500"
                >
                  {activeDraft.suggested_content_angles.map((a, i) => (
                    <option key={i} value={a}>{a}</option>
                  ))}
                  <option value="">— custom (taip dalam Topic) —</option>
                </select>
              </div>
            )}

            {/* Key benefits */}
            {activeDraft.key_benefits.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Key Benefits</p>
                <div className="flex flex-wrap gap-1">
                  {activeDraft.key_benefits.map((b, i) => (
                    <Pill key={i} label={b} color="emerald" />
                  ))}
                </div>
              </div>
            )}

            {/* TikTok product name */}
            {activeDraft.tiktok_product_name && (
              <div className="flex items-center gap-2 text-xs text-gray-600 bg-gray-50
                rounded-lg px-3 py-2">
                <span className="text-gray-400">TikTok search:</span>
                <span className="font-medium">{activeDraft.tiktok_product_name}</span>
              </div>
            )}

            {/* Screenshot reference image picker */}
            {activeDraft.source_images.length > 1 && (
              <div>
                <p className="text-xs text-gray-500 mb-2">
                  Select Reference Image (for pipeline)
                </p>
                <div className="flex gap-2 flex-wrap">
                  {activeDraft.source_images.map((fn, i) => (
                    <button
                      key={i}
                      onClick={() => setSelectedRefImage(fn)}
                      className={`relative rounded-lg overflow-hidden border-2 transition-colors ${
                        selectedRefImage === fn ? 'border-violet-500' : 'border-transparent'
                      }`}
                    >
                      <img
                        src={`/uploads/${fn}`}
                        alt={`screenshot ${i + 1}`}
                        className="w-16 h-16 object-cover"
                        onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                      {selectedRefImage === fn && (
                        <div className="absolute inset-0 bg-violet-500/20 flex items-center
                          justify-center text-violet-700 text-lg">✓</div>
                      )}
                    </button>
                  ))}
                  <button
                    onClick={() => setSelectedRefImage(null)}
                    className={`w-16 h-16 rounded-lg border-2 text-xs text-gray-400
                      flex items-center justify-center hover:bg-gray-50 transition-colors ${
                      selectedRefImage === null ? 'border-violet-500 text-violet-500' : 'border-gray-200'
                    }`}
                  >
                    Tiada
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Existing duplicate notice */}
        {existingId != null && (
          <p className="text-xs text-blue-600 bg-blue-50 rounded px-2 py-1.5">
            Produk ini sudah disimpan — "Save" akan kemaskini preset sedia ada.
          </p>
        )}

        {/* Action buttons */}
        {!isEditing && (
          <div className="flex flex-wrap gap-2 pt-1 border-t border-gray-100">
            <button
              onClick={handleApply}
              className="px-4 py-2 bg-emerald-600 text-white text-sm font-semibold rounded-lg
                hover:bg-emerald-700"
            >
              Apply to Pipeline
            </button>
            <button
              onClick={() => setIsEditing(true)}
              className="px-3 py-2 text-sm border border-gray-200 text-gray-600 rounded-lg
                hover:bg-gray-50"
            >
              Edit Analysis
            </button>
            <button
              onClick={() => onSave(isEditing ? editedDraft : activeDraft)}
              disabled={saving}
              className="px-3 py-2 text-sm border border-violet-200 text-violet-700 rounded-lg
                hover:bg-violet-50 disabled:opacity-50"
            >
              {saving ? 'Saving...' : existingId != null ? '↻ Update Preset' : '💾 Save Preset'}
            </button>
            <button
              onClick={onCancel}
              className="px-3 py-2 text-sm text-gray-400 hover:text-gray-600"
            >
              Cancel
            </button>
          </div>
        )}

        {savedMsg && (
          <p className={`text-xs ${savedMsg.startsWith('✓') ? 'text-emerald-600' : 'text-red-500'}`}>
            {savedMsg}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ProductImportAssistant({ onApply }: Props) {
  const [tab, setTab] = useState<Tab>('saved')
  const [state, setState] = useState<State>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  // Shared draft state
  const [draft, setDraft] = useState<ProductDraft | null>(null)
  const [existingId, setExistingId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [conflict, setConflict] = useState<ProductConflict | null>(null)

  // ── Tab: Saved ──────────────────────────────────────────────────────────────
  const [savedProducts, setSavedProducts] = useState<SavedProduct[]>([])
  const [selectedPresetId, setSelectedPresetId] = useState<number | ''>('')
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  // ── Tab: Link ───────────────────────────────────────────────────────────────
  const [productUrl, setProductUrl] = useState('')
  const [linkBlockedMsg, setLinkBlockedMsg] = useState('')

  // ── Tab: Text / Screenshot ──────────────────────────────────────────────────
  const [pastedText, setPastedText] = useState('')
  const [screenshots, setScreenshots] = useState<File[]>([])
  const [screenshotPreviews, setScreenshotPreviews] = useState<string[]>([])
  const [textProductUrl, setTextProductUrl] = useState('') // carried from link tab
  const [notes, setNotes] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    productApi.list().then(setSavedProducts).catch(() => {})
  }, [])

  // Clean up object URLs on unmount
  useEffect(() => {
    return () => { screenshotPreviews.forEach(URL.revokeObjectURL) }
  }, [screenshotPreviews])

  function resetDraft() {
    setDraft(null)
    setExistingId(null)
    setSavedMsg('')
    setState('idle')
    setErrorMsg('')
  }

  // ── Tab: Saved — select preset ─────────────────────────────────────────────
  function handlePresetSelect(id: number | '') {
    setSelectedPresetId(id)
    setDeleteConfirm(false)
    if (id === '') { resetDraft(); return }
    const p = savedProducts.find(x => x.id === id)
    if (!p) return
    setDraft(savedToProductDraft(p))
    setExistingId(p.id)
    setState('draft_ready')
    setSavedMsg('')
  }

  async function handleDeletePreset(id: number) {
    setDeletingId(id)
    try {
      await productApi.delete(id)
      setSavedProducts(prev => prev.filter(p => p.id !== id))
      setSelectedPresetId('')
      resetDraft()
    } catch (e) {
      setErrorMsg((e as Error).message)
    } finally {
      setDeletingId(null)
      setDeleteConfirm(false)
    }
  }

  async function handleRefreshPreset(id: number) {
    setState('fetching_link')
    try {
      const result = await productApi.refresh(id)
      if (result.draft) {
        setDraft(result.draft)
        setState('draft_ready')
        if (result.has_changes) {
          setSavedMsg('↻ Data terbaru dimuat — semak dan Apply semula jika perlu.')
        } else {
          setSavedMsg('Data sudah terkini.')
        }
      }
    } catch (e) {
      setErrorMsg((e as Error).message)
      setState('error')
    }
  }

  // ── Tab: Link — fetch ──────────────────────────────────────────────────────
  async function handleFetchLink() {
    if (!productUrl.trim()) return
    setState('fetching_link')
    setLinkBlockedMsg('')
    setErrorMsg('')
    setSavedMsg('')
    try {
      const result = await productApi.fetch(productUrl.trim())

      if (result.fetch_failed) {
        setState('link_blocked')
        setLinkBlockedMsg(result.fetch_error)
        return
      }

      setDraft(result.draft)
      setExistingId(result.existing_id ?? null)
      setState('draft_ready')
    } catch (e) {
      setErrorMsg((e as Error).message)
      setState('error')
    }
  }

  function switchToTextFromLink() {
    setTab('text')
    setTextProductUrl(productUrl)
    setState('idle')
    setLinkBlockedMsg('')
  }

  // ── Tab: Text / Screenshot — analyze ───────────────────────────────────────
  function handleScreenshotSelect(files: FileList | null) {
    if (!files) return
    const newFiles = Array.from(files).slice(0, 5 - screenshots.length)
    const newPreviews = newFiles.map(f => URL.createObjectURL(f))
    setScreenshots(prev => [...prev, ...newFiles].slice(0, 5))
    setScreenshotPreviews(prev => [...prev, ...newPreviews].slice(0, 5))
  }

  function removeScreenshot(i: number) {
    URL.revokeObjectURL(screenshotPreviews[i])
    setScreenshots(prev => prev.filter((_, j) => j !== i))
    setScreenshotPreviews(prev => prev.filter((_, j) => j !== i))
  }

  async function handleAnalyzeText() {
    const text = pastedText.trim()
    if (text.length < 20) {
      setErrorMsg('Teks terlalu pendek. Salin lebih banyak maklumat produk.')
      return
    }
    setState('analyzing_text')
    setErrorMsg('')
    setSavedMsg('')
    try {
      const d = await productApi.analyzeText(text, textProductUrl)
      setDraft(d)
      setExistingId(null)
      setState('draft_ready')
    } catch (e) {
      setErrorMsg((e as Error).message)
      setState('error')
    }
  }

  async function handleAnalyzeImages() {
    if (screenshots.length === 0) {
      setErrorMsg('Upload sekurang-kurangnya satu screenshot.')
      return
    }
    setState('analyzing_images')
    setErrorMsg('')
    setSavedMsg('')
    try {
      const d = await productApi.analyzeImages(screenshots, textProductUrl, notes)
      setDraft(d)
      setExistingId(null)
      setState('draft_ready')
    } catch (e) {
      setErrorMsg((e as Error).message)
      setState('error')
    }
  }

  async function handleAnalyze() {
    if (screenshots.length > 0) {
      await handleAnalyzeImages()
    } else {
      await handleAnalyzeText()
    }
  }

  // ── Apply draft to pipeline ────────────────────────────────────────────────
  function handleApply(d: ProductDraft, refImage: string | null) {
    const fields: Partial<PipelineFields> = {
      product: d.product_name,
      audience: d.target_audience,
      topic: d.suggested_content_angles[0] ?? '',
      objective: d.default_video_objective,
      visual_style: d.default_video_style,
      tiktok_product_name: d.tiktok_product_name,
    }
    onApply(fields, refImage)
    setSavedMsg('')
  }

  // ── Save preset ────────────────────────────────────────────────────────────
  async function handleSave(d: ProductDraft) {
    setSaving(true)
    setSavedMsg('')
    setConflict(null)
    try {
      if (existingId != null) {
        const updated = await productApi.update(existingId, {
          name: d.product_name,
          shop_name: d.shop_name,
          price: d.price,
          description: d.product_description,
          image_filename: d.source_images[0] ?? undefined,
          common_pain_points: d.common_pain_points,
          buying_motivations: d.buying_motivations,
          suggested_content_angles: d.suggested_content_angles,
          target_audience: d.target_audience,
          target_audience_options: d.target_audience_options,
          default_video_objective: d.default_video_objective,
          default_video_style: d.default_video_style,
          tiktok_product_name: d.tiktok_product_name,
          key_benefits: d.key_benefits,
        })
        setSavedProducts(prev => prev.map(p => p.id === updated.id ? updated : p))
        setSavedMsg('✓ Preset dikemaskini.')
      } else {
        const result = await productApi.saveOrConflict({
          name: d.product_name || 'Produk Baru',
          url: d.product_url || '',
          source_type: d.source_type,
          shop_name: d.shop_name,
          price: d.price,
          description: d.product_description,
          image_filename: d.source_images[0] ?? undefined,
          common_pain_points: d.common_pain_points,
          buying_motivations: d.buying_motivations,
          suggested_content_angles: d.suggested_content_angles,
          target_audience: d.target_audience,
          target_audience_options: d.target_audience_options,
          default_video_objective: d.default_video_objective,
          default_video_style: d.default_video_style,
          tiktok_product_name: d.tiktok_product_name,
          key_benefits: d.key_benefits,
        })
        if (!result.ok) {
          setConflict(result.conflict)
          return
        }
        const saved = result.product
        setSavedProducts(prev => [saved, ...prev])
        setExistingId(saved.id)
        setSelectedPresetId(saved.id)
        setSavedMsg('✓ Preset disimpan.')
      }
    } catch (e) {
      setSavedMsg((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleUseExisting() {
    if (!conflict) return
    try {
      const existing = await productApi.get(conflict.existing_product_id)
      const d = savedToProductDraft(existing)
      handleApply(d, existing.reference_image_path ?? existing.image_filename ?? null)
      setConflict(null)
    } catch {
      setSavedMsg('Gagal memuatkan produk sedia ada.')
    }
  }

  async function handleEditExisting() {
    if (!conflict) return
    try {
      const existing = await productApi.get(conflict.existing_product_id)
      setExistingId(existing.id)
      setDraft(savedToProductDraft(existing))
      setState('draft_ready')
      setConflict(null)
    } catch {
      setSavedMsg('Gagal memuatkan produk sedia ada.')
    }
  }

  // ── Busy flag ──────────────────────────────────────────────────────────────
  const isBusy = state === 'fetching_link' || state === 'analyzing_text' || state === 'analyzing_images'

  return (
    <div className="rounded-xl border border-violet-200 bg-violet-50 p-4 space-y-3">
      {/* Header + tabs */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-xs font-bold text-violet-600 uppercase tracking-widest">
          Product Import Assistant
        </p>
        <div className="flex gap-1 bg-white border border-violet-100 rounded-lg p-0.5">
          <TabBtn label="Saved" active={tab === 'saved'} onClick={() => { setTab('saved'); resetDraft() }} />
          <TabBtn label="Link" active={tab === 'link'}  onClick={() => { setTab('link');  resetDraft() }} />
          <TabBtn label="Text / Screenshot" active={tab === 'text'}  onClick={() => { setTab('text');  resetDraft() }} />
        </div>
      </div>

      {/* ── Tab: Saved ─────────────────────────────────────────────────────── */}
      {tab === 'saved' && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <select
              value={selectedPresetId}
              onChange={e => handlePresetSelect(e.target.value === '' ? '' : Number(e.target.value))}
              className="flex-1 border border-violet-200 rounded-lg px-3 py-2 text-sm bg-white
                outline-none focus:ring-2 focus:ring-violet-500"
            >
              <option value="">— pilih produk —</option>
              {savedProducts.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.shop_name ? ` · ${p.shop_name}` : ''}
                </option>
              ))}
            </select>

            {selectedPresetId !== '' && (
              <div className="flex gap-1">
                <button
                  onClick={() => handleRefreshPreset(Number(selectedPresetId))}
                  disabled={isBusy}
                  title="Refresh analysis"
                  className="px-3 py-2 text-xs border border-violet-300 text-violet-700 rounded-lg
                    hover:bg-violet-100 disabled:opacity-50"
                >
                  ↻
                </button>
                {!deleteConfirm ? (
                  <button
                    onClick={() => setDeleteConfirm(true)}
                    title="Delete preset"
                    className="px-3 py-2 text-xs border border-red-200 text-red-500 rounded-lg
                      hover:bg-red-50"
                  >
                    🗑
                  </button>
                ) : (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-red-600">Delete?</span>
                    <button
                      onClick={() => handleDeletePreset(Number(selectedPresetId))}
                      disabled={deletingId !== null}
                      className="px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600
                        disabled:opacity-50"
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => setDeleteConfirm(false)}
                      className="px-2 py-1 text-xs border border-gray-200 text-gray-500 rounded
                        hover:bg-gray-50"
                    >
                      No
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {savedProducts.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-2">
              Tiada preset disimpan lagi — gunakan tab Link atau Text untuk tambah produk baru.
            </p>
          )}
        </div>
      )}

      {/* ── Tab: Link ─────────────────────────────────────────────────────── */}
      {tab === 'link' && (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              value={productUrl}
              onChange={e => setProductUrl(e.target.value)}
              placeholder="https://shop.tiktok.com/view/product/..."
              disabled={isBusy}
              className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white
                outline-none focus:ring-2 focus:ring-violet-500 disabled:bg-gray-50"
            />
            <button
              onClick={handleFetchLink}
              disabled={!productUrl.trim() || isBusy}
              className="px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg
                hover:bg-violet-700 disabled:opacity-40 shrink-0"
            >
              {state === 'fetching_link' ? '⏳' : 'Fetch'}
            </button>
          </div>

          {/* Bot blocked fallback */}
          {state === 'link_blocked' && (
            <div className="bg-white border border-amber-200 rounded-lg p-3 space-y-2">
              <p className="text-sm text-amber-800 font-medium">
                TikTok blocks automatic reading for this link.
              </p>
              <p className="text-xs text-gray-600">
                Copy the product title, description, and benefits from TikTok Shop, then use one of these options:
              </p>
              <div className="flex gap-2">
                <button
                  onClick={switchToTextFromLink}
                  className="px-3 py-2 text-xs bg-violet-600 text-white rounded-lg
                    hover:bg-violet-700 font-medium"
                >
                  Switch to Text Input
                </button>
                <button
                  onClick={() => { setTab('text'); setTextProductUrl(productUrl); setState('idle') }}
                  className="px-3 py-2 text-xs border border-violet-300 text-violet-700 rounded-lg
                    hover:bg-violet-50"
                >
                  Upload Screenshot
                </button>
              </div>
              {linkBlockedMsg && (
                <p className="text-xs text-gray-400">{linkBlockedMsg}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Text / Screenshot ────────────────────────────────────────── */}
      {tab === 'text' && (
        <div className="space-y-3">
          {/* Optional URL carry-over notice */}
          {textProductUrl && (
            <div className="flex items-center gap-2 bg-white border border-violet-100 rounded-lg
              px-3 py-2">
              <span className="text-xs text-gray-500">URL disimpan:</span>
              <span className="text-xs text-violet-700 truncate flex-1">{textProductUrl}</span>
              <button
                onClick={() => setTextProductUrl('')}
                className="text-gray-400 hover:text-gray-600 text-sm shrink-0"
              >×</button>
            </div>
          )}

          {/* Text area */}
          <div>
            <p className="text-xs text-gray-500 mb-1">
              Paste product title, description, benefits, price…
            </p>
            <textarea
              value={pastedText}
              onChange={e => setPastedText(e.target.value)}
              rows={5}
              placeholder="Salin mana-mana teks dari halaman produk TikTok Shop…"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white
                outline-none focus:ring-2 focus:ring-violet-500 resize-none"
            />
            {pastedText.length > 0 && (
              <p className="text-xs text-gray-400 text-right">{pastedText.length} aksara</p>
            )}
          </div>

          {/* Screenshot upload */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs text-gray-500">Screenshots (opsional, maks 5)</p>
              {screenshots.length > 0 && (
                <button
                  onClick={() => {
                    screenshotPreviews.forEach(URL.revokeObjectURL)
                    setScreenshots([]); setScreenshotPreviews([])
                  }}
                  className="text-xs text-red-400 hover:text-red-600"
                >
                  Clear all
                </button>
              )}
            </div>

            {/* Thumbnail row */}
            {screenshotPreviews.length > 0 && (
              <div className="flex gap-2 mb-2 flex-wrap">
                {screenshotPreviews.map((src, i) => (
                  <div key={i} className="relative">
                    <img
                      src={src}
                      alt={`screenshot ${i + 1}`}
                      className="w-16 h-16 object-cover rounded-lg border border-gray-200"
                    />
                    <button
                      onClick={() => removeScreenshot(i)}
                      className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white
                        rounded-full text-xs flex items-center justify-center leading-none"
                    >×</button>
                  </div>
                ))}
              </div>
            )}

            {screenshots.length < 5 && (
              <button
                onClick={() => fileInputRef.current?.click()}
                className="text-xs border border-dashed border-violet-300 text-violet-600 px-3
                  py-2 rounded-lg hover:bg-violet-50 w-full text-center"
              >
                + Upload screenshot (JPG, PNG, WEBP)
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".jpg,.jpeg,.png,.webp"
              multiple
              className="hidden"
              onChange={e => handleScreenshotSelect(e.target.files)}
            />
          </div>

          {/* Notes (visible when screenshots selected) */}
          {screenshots.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Nota tambahan (opsional)</p>
              <input
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Contoh: produk ni untuk kanak-kanak 4-12 tahun"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white
                  outline-none focus:ring-2 focus:ring-violet-500"
              />
            </div>
          )}

          {/* Analyze button */}
          <div className="flex gap-2">
            <button
              onClick={handleAnalyze}
              disabled={
                isBusy ||
                (pastedText.trim().length < 20 && screenshots.length === 0)
              }
              className="flex-1 py-2.5 bg-violet-600 text-white text-sm font-semibold rounded-lg
                hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {state === 'analyzing_text'   ? '⏳ Analyzing text...'
               : state === 'analyzing_images' ? '⏳ Analyzing screenshots...'
               : screenshots.length > 0 ? '🔍 Analyze Screenshots'
               : '🔍 Analyze Product'}
            </button>
            {(pastedText || screenshots.length > 0) && (
              <button
                onClick={() => {
                  setPastedText('')
                  screenshotPreviews.forEach(URL.revokeObjectURL)
                  setScreenshots([]); setScreenshotPreviews([])
                  setNotes('')
                  resetDraft()
                }}
                className="px-3 py-2 text-xs border border-gray-200 text-gray-500 rounded-lg
                  hover:bg-gray-50"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Error banner ──────────────────────────────────────────────────── */}
      {state === 'error' && errorMsg && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <p className="text-xs text-red-600">{errorMsg}</p>
          <button
            onClick={resetDraft}
            className="text-xs text-red-500 underline mt-1"
          >
            Cuba semula
          </button>
        </div>
      )}
      {state !== 'error' && errorMsg && (
        <p className="text-xs text-red-500">{errorMsg}</p>
      )}

      {/* ── Review card ───────────────────────────────────────────────────── */}
      {draft && state === 'draft_ready' && (
        <ReviewCard
          draft={draft}
          onApply={handleApply}
          onSave={handleSave}
          onCancel={resetDraft}
          saving={saving}
          savedMsg={savedMsg}
          existingId={existingId}
        />
      )}

      {/* ── Conflict card ─────────────────────────────────────────────────── */}
      {conflict && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 space-y-2">
          <p className="text-sm font-semibold text-amber-800">⚠ Produk Sudah Ada</p>
          <p className="text-xs text-amber-700">
            <strong>{conflict.existing_product_name}</strong>
            {conflict.matched_by === 'url' ? ' — URL yang sama'
              : conflict.matched_by === 'product_id' ? ' — ID produk yang sama'
              : conflict.matched_by === 'name_shop' ? ' — nama & kedai yang sama'
              : ' — nama yang serupa'}
            {' '}sudah ada dalam library.
          </p>
          <div className="flex flex-wrap gap-2 pt-0.5">
            <button
              onClick={handleUseExisting}
              className="px-3 py-1.5 text-xs bg-violet-600 text-white rounded-lg
                hover:bg-violet-700 font-medium"
            >
              Guna Produk Sedia Ada
            </button>
            <button
              onClick={handleEditExisting}
              className="px-3 py-1.5 text-xs border border-amber-400 text-amber-700
                rounded-lg hover:bg-amber-100"
            >
              Edit Produk Sedia Ada
            </button>
            <button
              onClick={() => setConflict(null)}
              className="px-3 py-1.5 text-xs border border-gray-200 text-gray-500
                rounded-lg hover:bg-gray-50"
            >
              Batal
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
