import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'
import { visionApi } from '../services/visionApi'
import type { ScreenAnalysis } from '../types/vision'
import { SCREEN_TYPE_COLOR } from '../types/vision'

// ── Bounding Box Canvas Overlay ───────────────────────────────────────────────

function BoundingBoxOverlay({
  analysis,
  imgRef,
}: {
  analysis: ScreenAnalysis
  imgRef: React.RefObject<HTMLImageElement | null>
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas || !img || !img.complete || img.naturalWidth === 0) return

    const scaleX = img.offsetWidth / img.naturalWidth
    const scaleY = img.offsetHeight / img.naturalHeight
    canvas.width = img.offsetWidth
    canvas.height = img.offsetHeight

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    for (const btn of analysis.buttons) {
      if (btn.source === 'ai' || btn.bounds[2] === 0) continue
      const [x1, y1, x2, y2] = btn.bounds
      const bx = x1 * scaleX
      const by = y1 * scaleY
      const bw = (x2 - x1) * scaleX
      const bh = (y2 - y1) * scaleY

      ctx.strokeStyle = 'rgba(99,102,241,0.85)'
      ctx.lineWidth = 1.5
      ctx.strokeRect(bx, by, bw, bh)

      // Label
      const label = btn.text.substring(0, 18)
      ctx.font = '10px monospace'
      const textW = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(99,102,241,0.85)'
      ctx.fillRect(bx, by - 14, textW + 4, 14)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, bx + 2, by - 3)
    }
  })

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
    />
  )
}

// ── Confidence Bar ────────────────────────────────────────────────────────────

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 60 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function VisionDebuggerPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()

  const [selectedDevice, setSelectedDevice] = useState<string>('')
  const [provider, setProvider] = useState<string>('uiautomator')
  const [analysis, setAnalysis] = useState<ScreenAnalysis | null>(null)
  const [history, setHistory] = useState<ScreenAnalysis[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [showRawXml, setShowRawXml] = useState(false)

  const imgRef = useRef<HTMLImageElement | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── WebSocket connection ────────────────────────────────────────────────────
  const connectWs = useCallback((deviceId: string) => {
    wsRef.current?.close()
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/vision/${deviceId}`)
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'vision_state') {
          const a = msg.payload as ScreenAnalysis
          setAnalysis(a)
          setHistory((prev) => [a, ...prev].slice(0, 20))
        }
      } catch {
        // ignore
      }
    }
    wsRef.current = ws
  }, [])

  useEffect(() => () => { wsRef.current?.close() }, [])

  // ── Device selection ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!selectedDevice) return
    connectWs(selectedDevice)
    setAnalysis(null)
    setHistory([])
    setError(null)
    // Try to load cached state
    visionApi.state(selectedDevice)
      .then((a) => { setAnalysis(a); setHistory([a]) })
      .catch(() => {})
    visionApi.history(selectedDevice, 20)
      .then((h) => setHistory(h))
      .catch(() => {})
  }, [selectedDevice, connectWs])

  // ── Auto-refresh ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    if (autoRefresh && selectedDevice) {
      autoRefreshRef.current = setInterval(() => {
        visionApi.analyze(selectedDevice, provider).catch(() => {})
      }, 3000)
    }
    return () => {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
  }, [autoRefresh, selectedDevice, provider])

  // ── Manual analyze ──────────────────────────────────────────────────────────
  async function handleAnalyze() {
    if (!selectedDevice) return
    setLoading(true)
    setError(null)
    try {
      const a = await visionApi.analyze(selectedDevice, provider)
      setAnalysis(a)
      setHistory((prev) => [a, ...prev].slice(0, 20))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const screenColor = analysis
    ? SCREEN_TYPE_COLOR[analysis.screen_type] ?? 'bg-gray-100 text-gray-600'
    : ''

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ── header ── */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 text-sm">
            ← Dashboard
          </button>
          <span className="text-gray-300">/</span>
          <h1 className="text-lg font-bold text-gray-900">Vision Debugger</h1>
        </div>
        <div className="flex items-center gap-3">
          {/* Device selector */}
          <select
            value={selectedDevice}
            onChange={(e) => setSelectedDevice(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm
              focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="">— Pilih device —</option>
            {devices.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.device_name || d.device_id}
              </option>
            ))}
          </select>
          {/* Provider selector */}
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm
              focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="uiautomator">UIAutomator</option>
            <option value="ai_vision">AI Vision (GPT-4o)</option>
          </select>
          {/* Auto-refresh toggle */}
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-indigo-600"
            />
            Auto (3s)
          </label>
          <button
            onClick={handleAnalyze}
            disabled={!selectedDevice || loading}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg
              hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Analyzing...' : '🔍 Analyze'}
          </button>
        </div>
      </header>

      {/* ── main layout ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT: screenshot + overlay */}
        <aside className="w-80 bg-white border-r border-gray-200 flex flex-col shrink-0">
          <div className="p-4 border-b border-gray-100">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Screenshot
            </p>
            {analysis?.timestamp && (
              <p className="text-xs text-gray-400 mt-0.5">{analysis.timestamp.slice(11, 19)} UTC</p>
            )}
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {!analysis?.screenshot_path && (
              <div className="h-96 bg-gray-50 border border-dashed border-gray-200 rounded-lg
                flex items-center justify-center text-sm text-gray-400">
                {selectedDevice ? 'Klik Analyze' : 'Pilih device dulu'}
              </div>
            )}
            {analysis?.screenshot_path && (
              <div style={{ position: 'relative', display: 'inline-block', width: '100%' }}>
                <img
                  ref={imgRef}
                  src={analysis.screenshot_path}
                  alt="Screenshot"
                  className="w-full rounded-lg border border-gray-200"
                  onLoad={() => {
                    // Trigger canvas redraw after image loads
                    setAnalysis((a) => (a ? { ...a } : null))
                  }}
                />
                {analysis && imgRef.current && (
                  <BoundingBoxOverlay analysis={analysis} imgRef={imgRef} />
                )}
              </div>
            )}

            {/* History strip */}
            {history.length > 1 && (
              <div className="mt-3">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  History ({history.length})
                </p>
                <div className="flex gap-1 flex-wrap">
                  {history.slice(0, 12).map((h, i) => (
                    <button
                      key={i}
                      onClick={() => setAnalysis(h)}
                      className={`w-12 h-16 rounded border overflow-hidden
                        ${analysis?.timestamp === h.timestamp ? 'border-indigo-500' : 'border-gray-200'}`}
                    >
                      {h.screenshot_path ? (
                        <img src={h.screenshot_path} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full bg-gray-100" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>

        {/* CENTER: analysis details */}
        <main className="flex-1 overflow-y-auto p-6 min-w-0 space-y-4">
          {!selectedDevice && (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <p className="text-4xl mb-3">👁️</p>
                <p className="text-gray-600 font-medium">Vision Debugger</p>
                <p className="text-gray-400 text-sm mt-1">Pilih device dan klik Analyze</p>
              </div>
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
              {error}
            </div>
          )}

          {analysis && (
            <>
              {/* Screen identification */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-gray-900">Screen Detection</h2>
                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${screenColor}`}>
                    {analysis.screen_type}
                  </span>
                </div>
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">Provider</span>
                    <span className="font-medium text-gray-700 font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">
                      {analysis.provider}
                    </span>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-gray-500">Confidence</span>
                    </div>
                    <ConfidenceBar value={analysis.confidence} />
                  </div>
                  {analysis.loading && (
                    <div className="flex items-center gap-2 text-amber-600 text-sm">
                      <span className="animate-pulse">⏳</span> Screen is loading
                    </div>
                  )}
                  {analysis.progress !== null && (
                    <div>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span className="text-gray-500">Progress</span>
                        <span className="text-gray-700">{analysis.progress}%</span>
                      </div>
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-violet-500 rounded-full"
                          style={{ width: `${analysis.progress}%` }}
                        />
                      </div>
                    </div>
                  )}
                  {analysis.ai_suggestion && (
                    <div className="mt-2 p-3 bg-indigo-50 rounded-lg text-sm text-indigo-700">
                      <span className="font-medium">AI Suggestion:</span> {analysis.ai_suggestion}
                    </div>
                  )}
                  {analysis.errors.length > 0 && (
                    <div className="mt-2 p-3 bg-red-50 rounded-lg text-sm text-red-700">
                      <span className="font-medium">Errors:</span> {analysis.errors.join(', ')}
                    </div>
                  )}
                </div>
              </div>

              {/* Detected buttons */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h2 className="font-semibold text-gray-900 mb-3">
                  Buttons ({analysis.buttons.length})
                </h2>
                {analysis.buttons.length === 0 && (
                  <p className="text-sm text-gray-400">Tiada button dikesan</p>
                )}
                <div className="flex flex-wrap gap-2">
                  {analysis.buttons.map((btn, i) => (
                    <div
                      key={i}
                      className="px-2.5 py-1 bg-indigo-50 border border-indigo-200 rounded-lg
                        text-xs text-indigo-700 flex items-center gap-1.5"
                      title={`(${btn.x}, ${btn.y}) conf=${btn.confidence.toFixed(2)} src=${btn.source}`}
                    >
                      <span>{btn.text}</span>
                      <span className="text-indigo-400 text-[10px]">
                        {Math.round(btn.confidence * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Visible text */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h2 className="font-semibold text-gray-900 mb-3">
                  Visible Text ({analysis.visible_text.length})
                </h2>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {analysis.visible_text.map((t, i) => (
                    <div key={i} className="text-sm text-gray-700 font-mono truncate">{t}</div>
                  ))}
                  {analysis.visible_text.length === 0 && (
                    <p className="text-sm text-gray-400">Tiada teks dikesan</p>
                  )}
                </div>
              </div>

              {/* Dialogs / editable fields */}
              {(analysis.dialogs.length > 0 || analysis.editable_fields.length > 0) && (
                <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
                  {analysis.dialogs.length > 0 && (
                    <div>
                      <h2 className="font-semibold text-gray-900 mb-2">
                        Dialogs ({analysis.dialogs.length})
                      </h2>
                      {analysis.dialogs.map((d, i) => (
                        <div key={i} className="text-sm text-orange-700 bg-orange-50 rounded p-2">{d}</div>
                      ))}
                    </div>
                  )}
                  {analysis.editable_fields.length > 0 && (
                    <div>
                      <h2 className="font-semibold text-gray-900 mb-2">
                        Editable Fields ({analysis.editable_fields.length})
                      </h2>
                      {analysis.editable_fields.map((f, i) => (
                        <div key={i} className="text-sm text-gray-600 font-mono bg-gray-50 rounded px-2 py-1">{f}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Raw XML toggle */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <button
                  onClick={() => setShowRawXml((v) => !v)}
                  className="flex items-center justify-between w-full"
                >
                  <h2 className="font-semibold text-gray-900">Raw UI Hierarchy (XML)</h2>
                  <span className="text-xs text-indigo-600">{showRawXml ? 'Sembunyikan' : 'Tunjuk'}</span>
                </button>
                {showRawXml && (
                  <pre className="mt-3 text-xs text-gray-600 bg-gray-50 rounded-lg p-3
                    overflow-x-auto max-h-64 overflow-y-auto font-mono whitespace-pre-wrap">
                    {analysis.raw_xml || '(kosong)'}
                  </pre>
                )}
              </div>
            </>
          )}
        </main>

        {/* RIGHT: quick stats */}
        <aside className="w-56 bg-white border-l border-gray-200 flex flex-col shrink-0 p-4 gap-4">
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Stats
            </p>
            {[
              { label: 'Buttons', value: analysis?.buttons.length ?? '—' },
              { label: 'Text items', value: analysis?.visible_text.length ?? '—' },
              { label: 'Dialogs', value: analysis?.dialogs.length ?? '—' },
              { label: 'Edit fields', value: analysis?.editable_fields.length ?? '—' },
              { label: 'Resolution', value: analysis?.width ? `${analysis.width}×${analysis.height}` : '—' },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between py-1.5 border-b border-gray-50">
                <span className="text-xs text-gray-500">{label}</span>
                <span className="text-sm font-semibold text-gray-800">{value}</span>
              </div>
            ))}
          </div>

          {history.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Recent Screens
              </p>
              <div className="space-y-1">
                {history.slice(0, 8).map((h, i) => (
                  <button
                    key={i}
                    onClick={() => setAnalysis(h)}
                    className={`w-full text-left px-2 py-1.5 rounded text-xs
                      ${analysis?.timestamp === h.timestamp ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-50'}`}
                  >
                    {h.screen_type}
                    <span className="text-gray-400 ml-1">{h.timestamp.slice(11, 19)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
