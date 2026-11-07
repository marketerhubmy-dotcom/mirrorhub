import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'

const BASE = '/api/v1/automation'

// ── Static options ────────────────────────────────────────────────────────────

const GENDERS = ['Wanita', 'Lelaki', 'Semua']
const AGES = ['18-24', '25-34', '35-44', '45+']

const ANGLES = [
  'Close-up produk',
  'Lifestyle / pemakai',
  'Before & After',
  'Unboxing',
  'Demo / cara pakai',
  'Testimoni pelanggan',
  'Price reveal / value',
  'Problem & solution',
  'Comparison / vs lain',
  'CTA / Beli sekarang',
]

// ── Helper ────────────────────────────────────────────────────────────────────

function CheckGroup({
  label, options, selected, onChange, single = false,
}: {
  label: string
  options: string[]
  selected: string[]
  onChange: (v: string[]) => void
  single?: boolean
}) {
  const toggle = (opt: string) => {
    if (single) { onChange([opt]); return }
    onChange(selected.includes(opt) ? selected.filter(x => x !== opt) : [...selected, opt])
  }
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => (
          <button key={opt} onClick={() => toggle(opt)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              selected.includes(opt)
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
            }`}>
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

interface Product {
  title: string
  price: string
  description: string
  image_url: string
  image_filename: string | null
  final_url: string
  avatar_questions?: {
    pain_points: string[]
    desires: string[]
    triggers: string[]
  }
}

interface SavedProduct extends Product {
  id: number
  name: string
  url: string
  pain_points: string[]
  desires: string[]
  triggers: string[]
}

interface GeneratedScript {
  angle: string
  script: string
}

export default function AutomationPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()
  const onlineDevices = devices.filter(d => d.is_online && d.adb_address)

  const [deviceId, setDeviceId] = useState('')
  const [savedProducts, setSavedProducts] = useState<SavedProduct[]>([])
  const [productUrl, setProductUrl] = useState('')
  const [product, setProduct] = useState<Product | null>(null)
  const [fetchLoading, setFetchLoading] = useState(false)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [saveLoading, setSaveLoading] = useState(false)

  // Dynamic avatar options from AI
  const [availablePainPoints, setAvailablePainPoints] = useState<string[]>([])
  const [availableDesires, setAvailableDesires] = useState<string[]>([])
  const [availableTriggers, setAvailableTriggers] = useState<string[]>([])

  // Avatar selections
  const [gender, setGender] = useState<string[]>(['Wanita'])
  const [age, setAge] = useState<string[]>(['25-34'])
  const [painPoints, setPainPoints] = useState<string[]>([])
  const [desires, setDesires] = useState<string[]>([])
  const [triggers, setTriggers] = useState<string[]>([])

  // Angles & scripts
  const [selectedAngles, setSelectedAngles] = useState<string[]>([])
  const [useCustomFormat, setUseCustomFormat] = useState(false)
  const [customFormat, setCustomFormat] = useState('')
  const [generatedScripts, setGeneratedScripts] = useState<GeneratedScript[]>([])
  const [genLoading, setGenLoading] = useState(false)
  const [activeScript, setActiveScript] = useState<GeneratedScript | null>(null)

  // Post type
  const [postType, setPostType] = useState<'post_now' | 'draft' | 'schedule'>('draft')
  const [scheduleTime, setScheduleTime] = useState('')

  // Automation
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<{ message: string; status: string }[]>([])
  const logsRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (onlineDevices.length > 0 && !deviceId) setDeviceId(onlineDevices[0].device_id)
  }, [onlineDevices])

  // Load saved products
  useEffect(() => {
    fetch('/api/v1/products')
      .then(r => r.json())
      .then(setSavedProducts)
      .catch(() => {})
  }, [])

  const applyProduct = (p: Product & Partial<SavedProduct>) => {
    setProduct(p)
    const aq = p.avatar_questions ?? {
      pain_points: (p as SavedProduct).pain_points ?? [],
      desires: (p as SavedProduct).desires ?? [],
      triggers: (p as SavedProduct).triggers ?? [],
    }
    setAvailablePainPoints(aq.pain_points)
    setAvailableDesires(aq.desires)
    setAvailableTriggers(aq.triggers)
    setPainPoints([])
    setDesires([])
    setTriggers([])
  }

  useEffect(() => {
    if (logsRef.current) logsRef.current.scrollTop = logsRef.current.scrollHeight
  }, [logs])

  const fetchProduct = async () => {
    if (!productUrl.trim()) return
    setFetchLoading(true)
    try {
      const res = await fetch(`${BASE}/fetch-product`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: productUrl }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail)
      applyProduct(data)
    } catch (e) {
      alert('Gagal fetch produk: ' + (e as Error).message)
    } finally {
      setFetchLoading(false)
    }
  }

  const saveProduct = async () => {
    if (!product) return
    setSaveLoading(true)
    try {
      const res = await fetch('/api/v1/products', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: product.title || productUrl,
          url: productUrl || product.final_url,
          price: product.price,
          description: product.description,
          image_filename: product.image_filename,
          image_url: product.image_url,
          pain_points: availablePainPoints,
          desires: availableDesires,
          triggers: availableTriggers,
        }),
      })
      const saved = await res.json()
      setSavedProducts(prev => [saved, ...prev])
      alert('Produk disimpan!')
    } catch (e) {
      alert('Gagal simpan: ' + (e as Error).message)
    } finally {
      setSaveLoading(false)
    }
  }

  const deleteSaved = async (id: number) => {
    await fetch(`/api/v1/products/${id}`, { method: 'DELETE' })
    setSavedProducts(prev => prev.filter(p => p.id !== id))
  }

  // Upload manual image
  const uploadImage = async (file: File): Promise<string> => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`${BASE}/upload-image`, { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail)
    return data.filename
  }

  // Generate scripts for all selected angles
  const generateScripts = async () => {
    if (selectedAngles.length === 0) { alert('Pilih sekurang-kurangnya 1 angle'); return }
    if (!product && !imageFile) { alert('Fetch produk atau upload gambar dulu'); return }
    setGenLoading(true)
    try {
      const avatar = {
        gender: gender[0] ?? 'Wanita',
        age: age[0] ?? '25-34',
        pain_points: painPoints,
        desires,
        triggers,
      }
      const productInfo = product ?? { title: '', price: '', description: '' }

      const res = await fetch(`${BASE}/generate-scripts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product: productInfo,
          avatar,
          angles: selectedAngles,
          custom_format: useCustomFormat && customFormat.trim() ? customFormat.trim() : null,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail)

      const scripts: GeneratedScript[] = Object.entries(data.scripts).map(
        ([angle, script]) => ({ angle, script: script as string })
      )
      setGeneratedScripts(scripts)
      if (scripts.length > 0) setActiveScript(scripts[0])
    } catch (e) {
      alert('Gagal generate: ' + (e as Error).message)
    } finally {
      setGenLoading(false)
    }
  }

  // Run automation for active script
  const runAutomation = async () => {
    if (!activeScript) { alert('Pilih script dulu'); return }

    let imageFilename = product?.image_filename ?? null
    if (!imageFilename && imageFile) {
      imageFilename = await uploadImage(imageFile)
    }
    if (!imageFilename) { alert('Gambar produk diperlukan'); return }

    try {
      const res = await fetch(`${BASE}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: deviceId,
          script: activeScript.script,
          image_filename: imageFilename,
          post_type: postType,
          schedule_time: postType === 'schedule' ? scheduleTime : null,
          use_chatgpt_app: false,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail)

      setRunning(true)
      setLogs([{ message: `▶ Jalankan: ${activeScript.angle}`, status: 'info' }])

      pollRef.current = setInterval(async () => {
        const s = await fetch(`${BASE}/status/${deviceId}`)
        const data = await s.json()
        setLogs(data.logs)
        if (!data.running) { clearInterval(pollRef.current!); setRunning(false) }
      }, 1000)
    } catch (e) {
      alert('Gagal: ' + (e as Error).message)
    }
  }

  const stopAutomation = async () => {
    await fetch(`${BASE}/stop/${deviceId}`, { method: 'DELETE' })
    clearInterval(pollRef.current!)
    setRunning(false)
  }

  const logColor = (s: string) =>
    s === 'success' ? 'text-emerald-400' : s === 'error' ? 'text-red-400' :
    s === 'stopped' ? 'text-amber-400' : 'text-gray-300'

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-4 shrink-0">
        <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 text-sm">← Back</button>
        <h1 className="text-lg font-bold text-gray-900">Automation</h1>
        <span className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full font-medium">
          YT Create 8s → TikTok
        </span>
      </header>

      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT: Form ── */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* Phone */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Phone</p>
            {onlineDevices.length === 0
              ? <p className="text-sm text-red-500">Tiada phone online — connect dulu dari Dashboard</p>
              : <select value={deviceId} onChange={e => setDeviceId(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500">
                  {onlineDevices.map(d => <option key={d.device_id} value={d.device_id}>{d.device_name}</option>)}
                </select>
            }
          </div>

          {/* Produk */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Produk</p>

            {/* Saved products */}
            {savedProducts.length > 0 && (
              <div>
                <p className="text-xs text-gray-400 mb-1.5">Produk tersimpan:</p>
                <div className="space-y-1.5">
                  {savedProducts.map(sp => (
                    <div key={sp.id}
                      className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${
                        product?.title === sp.title
                          ? 'border-indigo-500 bg-indigo-50'
                          : 'border-gray-200 hover:border-indigo-300'
                      }`}
                      onClick={() => applyProduct(sp)}>
                      {sp.image_filename && (
                        <img src={`/uploads/${sp.image_filename}`} alt=""
                          className="w-8 h-8 object-cover rounded shrink-0"
                          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-gray-800 truncate">{sp.name}</p>
                        {sp.price && <p className="text-xs text-emerald-600">{sp.price}</p>}
                      </div>
                      <button onClick={e => { e.stopPropagation(); deleteSaved(sp.id) }}
                        className="text-gray-300 hover:text-red-400 text-xs px-1">✕</button>
                    </div>
                  ))}
                </div>
                <div className="border-t border-gray-100 my-2" />
              </div>
            )}

            {/* Fetch new product */}
            <div className="flex gap-2">
              <input value={productUrl} onChange={e => setProductUrl(e.target.value)}
                placeholder="Paste link TikTok Shop / beg kuning..."
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button onClick={fetchProduct} disabled={fetchLoading || !productUrl.trim()}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
                  hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap">
                {fetchLoading ? '⏳' : 'Fetch'}
              </button>
            </div>

            {product && (
              <div className="space-y-2">
                <div className="flex gap-3 bg-gray-50 rounded-xl p-3">
                  {(product.image_filename || product.image_url) && (
                    <img
                      src={product.image_filename ? `/uploads/${product.image_filename}` : product.image_url}
                      alt="Product"
                      className="w-16 h-16 object-cover rounded-lg shrink-0"
                      onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{product.title || 'Produk'}</p>
                    {product.price && <p className="text-sm text-emerald-600 font-semibold">{product.price}</p>}
                    <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{product.description}</p>
                  </div>
                </div>
                <button onClick={saveProduct} disabled={saveLoading}
                  className="w-full py-1.5 border border-indigo-300 text-indigo-600 rounded-lg text-xs
                    font-medium hover:bg-indigo-50 disabled:opacity-50">
                  {saveLoading ? '...' : '💾 Simpan produk ni'}
                </button>
              </div>
            )}

            {!product && (
              <div>
                <p className="text-xs text-gray-400 mb-1.5">Atau upload gambar manual:</p>
                <label className="block border-2 border-dashed border-gray-200 rounded-xl p-3 text-center cursor-pointer hover:border-indigo-300">
                  <input type="file" accept="image/*" className="hidden"
                    onChange={e => setImageFile(e.target.files?.[0] ?? null)} />
                  <p className="text-xs text-gray-400">
                    {imageFile ? `${imageFile.name} ✓` : 'Klik untuk upload gambar'}
                  </p>
                </label>
              </div>
            )}
          </div>

          {/* Avatar */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Target Avatar</p>
            <CheckGroup label="Jantina" options={GENDERS} selected={gender} onChange={setGender} single />
            <CheckGroup label="Umur" options={AGES} selected={age} onChange={setAge} single />

            {availablePainPoints.length > 0 ? (
              <CheckGroup label="Pain Points (masalah avatar)" options={availablePainPoints}
                selected={painPoints} onChange={setPainPoints} />
            ) : (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Pain Points (masalah avatar)
                </p>
                <p className="text-xs text-gray-400 italic">
                  Fetch produk dulu — AI akan jana pain points spesifik untuk produk tersebut
                </p>
              </div>
            )}

            {availableDesires.length > 0 && (
              <CheckGroup label="Keinginan / Goals" options={availableDesires}
                selected={desires} onChange={setDesires} />
            )}

            {availableTriggers.length > 0 && (
              <CheckGroup label="Trigger Beli" options={availableTriggers}
                selected={triggers} onChange={setTriggers} />
            )}
          </div>

          {/* Angles */}
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Angle Video ({selectedAngles.length} dipilih)
              </p>
              <button onClick={() => setSelectedAngles(selectedAngles.length === ANGLES.length ? [] : [...ANGLES])}
                className="text-xs text-indigo-500 hover:text-indigo-700">
                {selectedAngles.length === ANGLES.length ? 'Clear all' : 'Select all'}
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {ANGLES.map(a => (
                <button key={a} onClick={() => setSelectedAngles(
                  selectedAngles.includes(a) ? selectedAngles.filter(x => x !== a) : [...selectedAngles, a]
                )}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    selectedAngles.includes(a)
                      ? 'bg-emerald-600 text-white border-emerald-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-emerald-300'
                  }`}>
                  {a}
                </button>
              ))}
            </div>

            {/* Custom prompt format toggle */}
            <div className="border-t border-gray-100 pt-3 space-y-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={useCustomFormat}
                  onChange={e => setUseCustomFormat(e.target.checked)}
                  className="rounded accent-indigo-600" />
                <span className="text-sm font-medium text-gray-700">
                  Guna custom prompt format (untuk video prompt, bukan VO script)
                </span>
              </label>

              {useCustomFormat && (
                <div className="space-y-1.5">
                  <p className="text-xs text-gray-400">
                    Paste format prompt kau. AI akan <strong>fill in</strong> placeholder seperti{' '}
                    <code className="bg-gray-100 px-1 rounded">[SCENE]</code>,{' '}
                    <code className="bg-gray-100 px-1 rounded">[CAMERA MOVEMENT]</code>,{' '}
                    <code className="bg-gray-100 px-1 rounded">[MODEL]</code> dll
                    berdasarkan angle + avatar yang dipilih.
                  </p>
                  <textarea
                    value={customFormat}
                    onChange={e => setCustomFormat(e.target.value)}
                    placeholder={`Close-up cinematic shot of [SCENE]. Use uploaded image as reference. Product must remain pixel-identical...\n[CAMERA MOVEMENT]. [MODEL]...\nNo text, captions, overlays, watermark.`}
                    rows={6}
                    className="w-full border border-indigo-200 rounded-lg px-3 py-2.5 text-xs font-mono
                      outline-none focus:ring-2 focus:ring-indigo-500 resize-none bg-indigo-50"
                  />
                  <p className="text-xs text-emerald-600">
                    ✓ AI akan generate filled-in version ni untuk setiap angle yang dipilih
                  </p>
                </div>
              )}
            </div>

            <button onClick={generateScripts} disabled={genLoading || selectedAngles.length === 0}
              className="w-full py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium
                hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed">
              {genLoading
                ? `Generating ${selectedAngles.length} prompt...`
                : `✨ Generate ${selectedAngles.length} ${useCustomFormat ? 'Video Prompt' : 'Script'}`
              }
            </button>
          </div>

          {/* Generated scripts */}
          {generatedScripts.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Script Dijana</p>
              <div className="space-y-2">
                {generatedScripts.map((gs, i) => (
                  <div key={i}
                    onClick={() => setActiveScript(gs)}
                    className={`rounded-xl border p-3 cursor-pointer transition-colors ${
                      activeScript?.angle === gs.angle
                        ? 'border-indigo-500 bg-indigo-50'
                        : 'border-gray-200 hover:border-indigo-300'
                    }`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-indigo-600">{gs.angle}</span>
                      {activeScript?.angle === gs.angle && (
                        <span className="text-xs bg-indigo-600 text-white px-2 py-0.5 rounded-full">Selected</span>
                      )}
                    </div>
                    <textarea value={gs.script}
                      onChange={e => {
                        const updated = generatedScripts.map(s =>
                          s.angle === gs.angle ? { ...s, script: e.target.value } : s
                        )
                        setGeneratedScripts(updated)
                        if (activeScript?.angle === gs.angle) setActiveScript({ ...gs, script: e.target.value })
                      }}
                      rows={2}
                      className="w-full text-sm text-gray-700 bg-transparent resize-none outline-none"
                      onClick={e => e.stopPropagation()}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Post type */}
          {activeScript && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Cara Post TikTok</p>
              <div className="grid grid-cols-3 gap-2">
                {([
                  { v: 'post_now', l: '🚀 Post Terus' },
                  { v: 'draft', l: '📋 Draft' },
                  { v: 'schedule', l: '⏰ Schedule' },
                ] as const).map(({ v, l }) => (
                  <button key={v} onClick={() => setPostType(v)}
                    className={`py-2.5 rounded-lg text-sm font-medium border transition-colors ${
                      postType === v ? 'bg-indigo-600 text-white border-indigo-600'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300'
                    }`}>
                    {l}
                  </button>
                ))}
              </div>
              {postType === 'schedule' && (
                <input type="datetime-local" value={scheduleTime}
                  onChange={e => setScheduleTime(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none" />
              )}
            </div>
          )}

          {/* Run / Stop */}
          {activeScript && (
            !running ? (
              <button onClick={runAutomation}
                className="w-full py-3 bg-emerald-600 text-white rounded-xl font-semibold hover:bg-emerald-700">
                ▶ Run: {activeScript.angle}
              </button>
            ) : (
              <button onClick={stopAutomation}
                className="w-full py-3 bg-red-500 text-white rounded-xl font-semibold hover:bg-red-600">
                ⏹ Hentikan
              </button>
            )
          )}

          <div className="pb-4 text-xs text-gray-400 space-y-0.5">
            <p>• YT Create max 8 saat per clip — 1 angle = 1 clip</p>
            <p>• Tengok mirror semasa automation berjalan</p>
          </div>
        </div>

        {/* ── RIGHT: Log sidebar ── */}
        <div className="w-64 shrink-0 border-l border-gray-200 bg-gray-900 flex flex-col">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <p className="text-xs font-mono text-gray-500 uppercase tracking-wider">Log</p>
            {running && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
          </div>
          <div ref={logsRef} className="flex-1 overflow-y-auto p-3 space-y-1 font-mono text-xs">
            {logs.length === 0
              ? <p className="text-gray-600">Log akan muncul bila automation start...</p>
              : logs.map((l, i) => <p key={i} className={logColor(l.status)}>{l.message}</p>)
            }
            {running && <p className="text-gray-500 animate-pulse">⏳ Running...</p>}
          </div>
        </div>

      </div>
    </div>
  )
}
