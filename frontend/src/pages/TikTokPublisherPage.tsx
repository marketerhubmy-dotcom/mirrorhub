import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { tiktokApi, TikTokProduct, TikTokSimulateResult } from '../services/tiktokApi'
import { useDevices } from '../hooks/useDevices'

const STATUS_COLOR: Record<string, string> = {
  SIMULATED: 'bg-indigo-100 text-indigo-700',
  STARTED:   'bg-emerald-100 text-emerald-700',
  OK:        'bg-emerald-100 text-emerald-700',
  ERROR:     'bg-red-100 text-red-700',
}

function Tag({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 bg-indigo-50 border border-indigo-200
      text-indigo-700 text-xs px-2 py-0.5 rounded-full">
      #{label}
      <button onClick={onRemove} className="text-indigo-400 hover:text-indigo-700 ml-0.5">✕</button>
    </span>
  )
}

function ProductCard({ product, selected, onSelect }: {
  product: TikTokProduct
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button onClick={onSelect}
      className={`w-full text-left p-3 rounded-xl border transition-colors
        ${selected
          ? 'border-indigo-300 bg-indigo-50 ring-2 ring-indigo-200'
          : 'border-gray-200 hover:bg-gray-50'}`}>
      <p className="text-sm font-semibold text-gray-900 truncate">{product.name}</p>
      <p className="text-xs text-gray-500 mt-0.5">ID: {product.id}</p>
      {product.sku && <p className="text-xs text-gray-400">SKU: {product.sku}</p>}
    </button>
  )
}

export default function TikTokPublisherPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()

  // ── Form state ────────────────────────────────────────────────────────────
  const [deviceId, setDeviceId] = useState('')
  const [videoPath, setVideoPath] = useState('')
  const [caption, setCaption] = useState('')
  const [hashtagInput, setHashtagInput] = useState('')
  const [hashtags, setHashtags] = useState<string[]>([])
  const [firstComment, setFirstComment] = useState('')
  const [postType, setPostType] = useState<'post_now' | 'draft'>('post_now')
  const [selectedProductId, setSelectedProductId] = useState('')

  // ── Product panel ─────────────────────────────────────────────────────────
  const [products, setProducts] = useState<TikTokProduct[]>([])
  const [showAddProduct, setShowAddProduct] = useState(false)
  const [newProduct, setNewProduct] = useState({ id: '', name: '', search_term: '', sku: '', notes: '' })

  // ── Execution state ───────────────────────────────────────────────────────
  const [simResult, setSimResult] = useState<TikTokSimulateResult | null>(null)
  const [execStatus, setExecStatus] = useState<{ status: string; reason: string; job_id?: number } | null>(null)
  const [validationResult, setValidationResult] = useState<{ success: boolean; code: string; reason: string } | null>(null)
  const [loading, setLoading] = useState<'validate' | 'simulate' | 'publish' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [logs, setLogs] = useState<string[]>([])

  const logsRef = useRef<HTMLDivElement>(null)

  // ── Load products on mount ─────────────────────────────────────────────────
  useEffect(() => {
    tiktokApi.listProducts().then(r => setProducts(r.products)).catch(() => {})
  }, [])

  useEffect(() => {
    logsRef.current?.scrollTo({ top: logsRef.current.scrollHeight, behavior: 'smooth' })
  }, [logs])

  function addLog(msg: string) {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])
  }

  // ── Hashtag helpers ───────────────────────────────────────────────────────
  function commitHashtag() {
    const tag = hashtagInput.trim().replace(/^#/, '')
    if (tag && !hashtags.includes(tag)) {
      setHashtags(prev => [...prev, tag])
    }
    setHashtagInput('')
  }

  function handleHashtagKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === ',') {
      e.preventDefault()
      commitHashtag()
    }
  }

  // ── Actions ───────────────────────────────────────────────────────────────
  async function handleValidate() {
    setLoading('validate')
    setError(null)
    setValidationResult(null)
    try {
      const result = await tiktokApi.validate({
        video_path: videoPath,
        caption,
        hashtags,
        product_id: selectedProductId,
      })
      setValidationResult(result)
      addLog(`Validate: ${result.code} — ${result.reason}`)
    } catch (e) {
      const msg = (e as Error).message
      setError(msg)
      addLog(`Validate error: ${msg}`)
    } finally { setLoading(null) }
  }

  async function handleSimulate() {
    setLoading('simulate')
    setError(null)
    setSimResult(null)
    try {
      addLog('Running simulation...')
      const result = await tiktokApi.simulate({
        video_path: videoPath,
        caption,
        hashtags,
        first_comment: firstComment,
        product_id: selectedProductId,
        post_type: postType,
      })
      setSimResult(result)
      addLog(`Simulation: ${result.total_steps} steps planned`)
    } catch (e) {
      const msg = (e as Error).message
      setError(msg)
      addLog(`Simulation error: ${msg}`)
    } finally { setLoading(null) }
  }

  async function handlePublish() {
    if (!deviceId) { setError('Select a device first'); return }
    if (!videoPath) { setError('Video path is required'); return }
    setLoading('publish')
    setError(null)
    setExecStatus(null)
    try {
      addLog(`Starting publish on ${deviceId}...`)
      const result = await tiktokApi.execute({
        device_id: deviceId,
        video_path: videoPath,
        caption,
        hashtags,
        first_comment: firstComment,
        product_id: selectedProductId,
        post_type: postType,
      })
      setExecStatus(result)
      addLog(`Execution started — job #${result.job_id} (${result.total_steps} steps)`)
    } catch (e) {
      const msg = (e as Error).message
      setError(msg)
      addLog(`Publish error: ${msg}`)
    } finally { setLoading(null) }
  }

  // ── Product CRUD ──────────────────────────────────────────────────────────
  async function handleAddProduct() {
    if (!newProduct.id || !newProduct.name) return
    try {
      const p = await tiktokApi.addProduct({
        ...newProduct,
        search_term: newProduct.search_term || newProduct.name,
      })
      setProducts(prev => [...prev, p])
      setShowAddProduct(false)
      setNewProduct({ id: '', name: '', search_term: '', sku: '', notes: '' })
    } catch (e) { setError((e as Error).message) }
  }

  async function handleDeleteProduct(id: string) {
    if (!confirm(`Delete product "${id}"?`)) return
    try {
      await tiktokApi.deleteProduct(id)
      setProducts(prev => prev.filter(p => p.id !== id))
      if (selectedProductId === id) setSelectedProductId('')
    } catch (e) { setError((e as Error).message) }
  }

  const selectedProduct = products.find(p => p.id === selectedProductId)

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ── Header ── */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 text-sm">← Dashboard</button>
          <span className="text-gray-300">/</span>
          <h1 className="text-lg font-bold text-gray-900">TikTok Publisher</h1>
          <span className="text-xs bg-pink-100 text-pink-700 border border-pink-200 px-2 py-0.5 rounded-full font-medium">
            Plugin v0.7
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleValidate} disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200 disabled:opacity-50">
            ✓ Validate
          </button>
          <button onClick={handleSimulate} disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-lg hover:bg-indigo-200 disabled:opacity-50">
            {loading === 'simulate' ? 'Simulating...' : '▷ Simulate'}
          </button>
          <button onClick={handlePublish} disabled={loading !== null || !deviceId}
            className="px-3 py-1.5 text-xs font-semibold bg-pink-600 text-white rounded-lg hover:bg-pink-700 disabled:opacity-50">
            {loading === 'publish' ? 'Publishing...' : '🚀 Publish'}
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 flex justify-between items-start">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-red-400 hover:text-red-600">✕</button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left: form ── */}
        <main className="flex-1 overflow-y-auto p-6 space-y-4 max-w-2xl">

          {/* Device + post type */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-900 mb-4">Target</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Device</label>
                <select value={deviceId} onChange={e => setDeviceId(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-pink-300">
                  <option value="">— Select device —</option>
                  {devices.map(d => (
                    <option key={d.device_id} value={d.device_id}>{d.device_name || d.device_id}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Post Type</label>
                <select value={postType} onChange={e => setPostType(e.target.value as 'post_now' | 'draft')}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-pink-300">
                  <option value="post_now">Post Now</option>
                  <option value="draft">Save as Draft</option>
                </select>
              </div>
            </div>
          </div>

          {/* Video */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-900 mb-4">Video</h2>
            <label className="block text-xs font-medium text-gray-600 mb-1">Local Video Path</label>
            <input value={videoPath} onChange={e => setVideoPath(e.target.value)}
              placeholder="C:\Users\...\exported_video.mp4"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-pink-300" />
            <p className="text-xs text-gray-400 mt-1">Accepted: .mp4, .mov, .webm — the plugin pushes this file to the device</p>

            {validationResult && (
              <div className={`mt-3 rounded-lg px-3 py-2 text-xs font-medium
                ${validationResult.success ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
                {validationResult.success ? '✓' : '✕'} {validationResult.reason}
              </div>
            )}
          </div>

          {/* Caption + hashtags */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-900 mb-4">Caption & Hashtags</h2>
            <label className="block text-xs font-medium text-gray-600 mb-1">Caption</label>
            <textarea value={caption} onChange={e => setCaption(e.target.value)}
              rows={4}
              placeholder="Caption produk... supports emoji 🔥 and {{variables}}"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-pink-300 resize-none" />
            <p className="text-xs text-gray-400 mt-1">{caption.length} chars</p>

            <label className="block text-xs font-medium text-gray-600 mb-1 mt-3">Hashtags</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {hashtags.map(tag => (
                <Tag key={tag} label={tag} onRemove={() => setHashtags(prev => prev.filter(t => t !== tag))} />
              ))}
            </div>
            <div className="flex gap-2">
              <input value={hashtagInput} onChange={e => setHashtagInput(e.target.value)}
                onKeyDown={handleHashtagKey} onBlur={commitHashtag}
                placeholder="fyp (press Enter or Space)"
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-pink-300" />
              <button onClick={commitHashtag} className="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200">
                Add
              </button>
            </div>

            <label className="block text-xs font-medium text-gray-600 mb-1 mt-3">First Comment (optional)</label>
            <input value={firstComment} onChange={e => setFirstComment(e.target.value)}
              placeholder="First comment to post after publishing..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-pink-300" />
          </div>

          {/* Execution result */}
          {execStatus && (
            <div className={`rounded-xl border p-4 text-sm ${
              execStatus.status === 'STARTED'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-red-50 border-red-200 text-red-700'}`}>
              <p className="font-semibold mb-1">
                {execStatus.status === 'STARTED' ? '✓ Execution started' : `⚠ ${execStatus.status}`}
              </p>
              <p className="text-xs">{execStatus.reason}</p>
              {execStatus.job_id && (
                <button onClick={() => navigate('/execution')}
                  className="mt-2 text-xs underline text-emerald-700 hover:text-emerald-900">
                  View in Execution Monitor → job #{execStatus.job_id}
                </button>
              )}
            </div>
          )}

          {/* Sim result */}
          {simResult && (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold text-gray-900">Simulation Result</h2>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[simResult.status] ?? 'bg-gray-100 text-gray-600'}`}>
                  {simResult.status}
                </span>
              </div>
              <p className="text-xs text-gray-500 mb-3">{simResult.total_steps} steps planned</p>
              <div className="space-y-1">
                {simResult.steps.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs">
                    <span className="w-5 text-right text-gray-400 shrink-0">{i + 1}</span>
                    <span className="text-gray-600 font-mono shrink-0">{s.type}</span>
                    <span className="text-gray-500 truncate">{s.label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>

        {/* ── Right: product panel + execution log ── */}
        <aside className="w-72 bg-white border-l border-gray-200 flex flex-col shrink-0">
          {/* Product panel */}
          <div className="border-b border-gray-100 p-4 flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">TikTok Shop Product</p>
              <button onClick={() => setShowAddProduct(v => !v)}
                className="text-xs text-indigo-600 hover:text-indigo-800">+ Add</button>
            </div>

            {showAddProduct && (
              <div className="mb-3 space-y-2 p-3 bg-gray-50 rounded-xl border border-gray-200">
                {[
                  { key: 'id', placeholder: 'Product ID' },
                  { key: 'name', placeholder: 'Product Name' },
                  { key: 'search_term', placeholder: 'Search term (TikTok Shop)' },
                  { key: 'sku', placeholder: 'SKU (optional)' },
                ].map(({ key, placeholder }) => (
                  <input key={key} value={(newProduct as Record<string, string>)[key]}
                    onChange={e => setNewProduct(p => ({ ...p, [key]: e.target.value }))}
                    placeholder={placeholder}
                    className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-pink-300" />
                ))}
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setShowAddProduct(false)} className="flex-1 py-1.5 border border-gray-300 rounded-lg text-xs">Cancel</button>
                  <button onClick={handleAddProduct} className="flex-1 py-1.5 bg-pink-600 text-white rounded-lg text-xs font-medium">Save</button>
                </div>
              </div>
            )}

            <div className="space-y-2 max-h-52 overflow-y-auto">
              {products.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">No products registered</p>
              )}
              {products.map(p => (
                <div key={p.id} className="flex gap-2 items-start">
                  <div className="flex-1 min-w-0">
                    <ProductCard
                      product={p}
                      selected={selectedProductId === p.id}
                      onSelect={() => setSelectedProductId(prev => prev === p.id ? '' : p.id)}
                    />
                  </div>
                  <button onClick={() => handleDeleteProduct(p.id)}
                    className="p-2 text-gray-300 hover:text-red-500 shrink-0 mt-0.5">✕</button>
                </div>
              ))}
            </div>

            {selectedProduct && (
              <div className="mt-2 p-2 bg-indigo-50 rounded-lg text-xs text-indigo-700 border border-indigo-200">
                ✓ Selected: <strong>{selectedProduct.name}</strong>
              </div>
            )}
            {!selectedProductId && (
              <p className="mt-2 text-xs text-gray-400 text-center">No product — will skip attachment</p>
            )}
          </div>

          {/* Execution log */}
          <div className="flex-1 flex flex-col p-4 min-h-0">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Execution Log</p>
              <button onClick={() => setLogs([])} className="text-xs text-gray-400 hover:text-gray-600">Clear</button>
            </div>
            <div ref={logsRef} className="flex-1 overflow-y-auto space-y-1">
              {logs.length === 0 && (
                <p className="text-xs text-gray-300">No activity yet</p>
              )}
              {logs.map((line, i) => (
                <p key={i} className="text-xs font-mono text-gray-600 leading-relaxed">{line}</p>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
