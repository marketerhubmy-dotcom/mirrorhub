import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'
import { executionApi } from '../services/executionApi'
import { visionApi } from '../services/visionApi'
import type {
  ExecutionJob,
  ExecutionStateResponse,
  StartExecutionRequest,
} from '../types/execution'
import type { ScreenAnalysis } from '../types/vision'
import {
  STATUS_LABEL,
  STATUS_COLOR,
  STEP_STATUS_COLOR,
} from '../types/execution'
import { SCREEN_TYPE_COLOR } from '../types/vision'

function useElapsedTime(startedAt: string | null | undefined): string {
  const [elapsed, setElapsed] = useState('')
  useEffect(() => {
    if (!startedAt) { setElapsed(''); return }
    const tick = () => {
      const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
      const m = Math.floor(secs / 60).toString().padStart(2, '0')
      const s = (secs % 60).toString().padStart(2, '0')
      setElapsed(`${m}:${s}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startedAt])
  return elapsed
}

// ── sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status as keyof typeof STATUS_COLOR] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
      {STATUS_LABEL[status as keyof typeof STATUS_LABEL] ?? status}
    </span>
  )
}

function StepDot({ status }: { status: string }) {
  const color = STEP_STATUS_COLOR[status] ?? 'bg-gray-200'
  const spin = status === 'running' ? 'animate-pulse' : ''
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color} ${spin}`} />
}

// ── main page ─────────────────────────────────────────────────────────────────

type LiveState = ExecutionStateResponse | null

interface NewJobForm {
  device_id: string
  video_prompt: string
  image_path: string
  post_type: string
}

function emptyForm(): NewJobForm {
  return { device_id: '', video_prompt: '', image_path: '', post_type: 'draft' }
}

export default function ExecutionMonitorPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()

  const [jobs, setJobs] = useState<ExecutionJob[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [liveState, setLiveState] = useState<LiveState>(null)
  const [visionState, setVisionState] = useState<ScreenAnalysis | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<NewJobForm>(emptyForm())
  const [starting, setStarting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const logEndRef = useRef<HTMLDivElement | null>(null)

  // ── fetch job list ──────────────────────────────────────────────────────────
  const loadJobs = useCallback(async () => {
    try {
      const list = await executionApi.list()
      setJobs(list)
    } catch {
      // silent
    }
  }, [])

  useEffect(() => {
    loadJobs()
    const id = setInterval(loadJobs, 4000)
    return () => clearInterval(id)
  }, [loadJobs])

  // ── poll Vision Engine state when a job is active ───────────────────────────
  useEffect(() => {
    const deviceId = jobs.find((j) => j.id === selectedId)?.device_id
    const running = liveState?.status === 'RUNNING'
      || liveState?.status === 'STARTING'
      || liveState?.status === 'EXPORTING'
    if (!deviceId || !running) {
      setVisionState(null)
      return
    }
    let live = true
    const poll = async () => {
      try {
        const s = await visionApi.state(deviceId)
        if (live) setVisionState(s)
      } catch { /* vision cache may be empty — ignore */ }
    }
    poll()
    const id = setInterval(poll, 4000)
    return () => { live = false; clearInterval(id) }
  }, [selectedId, liveState?.status, jobs])

  // ── WebSocket for live state ────────────────────────────────────────────────
  const connectWs = useCallback((deviceId: string) => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/execution/${deviceId}`)
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string)
        if (msg.type === 'execution_state') {
          setLiveState(msg.payload as ExecutionStateResponse)
        }
      } catch {
        // ignore malformed
      }
    }
    ws.onclose = () => {}
    wsRef.current = ws
  }, [])

  // ── select job ──────────────────────────────────────────────────────────────
  const selectJob = useCallback(
    async (job: ExecutionJob) => {
      setSelectedId(job.id)
      setLiveState(null)
      setActionError(null)
      connectWs(job.device_id)
      try {
        const state = await executionApi.get(job.id)
        setLiveState(state as ExecutionStateResponse)
      } catch {
        // ignore
      }
    },
    [connectWs],
  )

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  // scroll logs to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveState?.logs])

  // ── start execution ─────────────────────────────────────────────────────────
  async function handleStart() {
    if (!form.device_id || !form.video_prompt || !form.image_path) return
    setStarting(true)
    setActionError(null)
    try {
      const req: StartExecutionRequest = {
        device_id: form.device_id,
        video_prompt: form.video_prompt,
        image_path: form.image_path,
        post_type: form.post_type,
      }
      const res = await executionApi.start(req)
      setShowForm(false)
      setForm(emptyForm())
      await loadJobs()
      // auto-select new job
      const newJob = await executionApi.get(res.job_id)
      setSelectedId(res.job_id)
      setLiveState(newJob as ExecutionStateResponse)
      connectWs(form.device_id)
    } catch (e) {
      setActionError((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  async function handleAction(action: 'pause' | 'resume' | 'cancel') {
    if (!selectedId) return
    setActionError(null)
    try {
      if (action === 'pause') await executionApi.pause(selectedId)
      else if (action === 'resume') await executionApi.resume(selectedId)
      else await executionApi.cancel(selectedId)
    } catch (e) {
      setActionError((e as Error).message)
    }
  }

  const selectedJob = jobs.find((j) => j.id === selectedId) ?? null
  const displayState = liveState
  const isActive =
    displayState?.status === 'RUNNING' ||
    displayState?.status === 'STARTING' ||
    displayState?.status === 'EXPORTING'
  const isPaused = !isActive && selectedJob?.status === 'RUNNING'
  const elapsed = useElapsedTime(isActive ? selectedJob?.created_at : null)

  const logs = displayState?.logs ?? selectedJob?.logs ?? []

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ── header ── */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            ← Dashboard
          </button>
          <span className="text-gray-300">/</span>
          <h1 className="text-lg font-bold text-gray-900">Execution Monitor</h1>
        </div>
        <button
          onClick={() => { setShowForm(true); setActionError(null) }}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg
            hover:bg-indigo-700 transition-colors"
        >
          + New Execution
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── LEFT: job list ── */}
        <aside className="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0">
          <div className="p-4 border-b border-gray-100">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Jobs ({jobs.length})
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {jobs.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-8 px-4">
                Belum ada execution job
              </p>
            )}
            {jobs.map((job) => (
              <button
                key={job.id}
                onClick={() => selectJob(job)}
                className={`w-full text-left px-4 py-3 border-b border-gray-100
                  hover:bg-gray-50 transition-colors
                  ${selectedId === job.id ? 'bg-indigo-50 border-l-2 border-l-indigo-500' : ''}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-700">#{job.id}</span>
                  <StatusBadge status={job.status} />
                </div>
                <p className="text-xs text-gray-500 truncate">{job.device_id}</p>
                <div className="mt-1.5 h-1 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-400 rounded-full transition-all"
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* ── CENTER: step list + state ── */}
        <main className="flex-1 overflow-y-auto p-6 min-w-0">
          {!selectedId && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-4xl mb-3">⚙️</p>
                <p className="text-gray-600 font-medium">Pilih job untuk monitor</p>
                <p className="text-gray-400 text-sm mt-1">
                  Atau klik "+ New Execution" untuk mula
                </p>
              </div>
            </div>
          )}

          {selectedId && (
            <div className="space-y-5">
              {/* job header */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-bold text-gray-900">Job #{selectedId}</span>
                      {displayState && <StatusBadge status={displayState.status} />}
                    </div>
                    <p className="text-sm text-gray-500">
                      Device: <span className="font-medium text-gray-700">
                        {displayState?.device_id ?? selectedJob?.device_id}
                      </span>
                    </p>
                    {displayState?.error && (
                      <p className="text-sm text-red-600 mt-1">⚠ {displayState.error}</p>
                    )}
                  </div>
                  {/* action buttons */}
                  <div className="flex gap-2">
                    {isActive && (
                      <button
                        onClick={() => handleAction('pause')}
                        className="px-3 py-1.5 text-xs font-medium bg-amber-100 text-amber-700
                          rounded-lg hover:bg-amber-200 transition-colors"
                      >
                        ⏸ Jeda
                      </button>
                    )}
                    {isPaused && (
                      <button
                        onClick={() => handleAction('resume')}
                        className="px-3 py-1.5 text-xs font-medium bg-emerald-100 text-emerald-700
                          rounded-lg hover:bg-emerald-200 transition-colors"
                      >
                        ▶ Sambung
                      </button>
                    )}
                    {(isActive || isPaused) && (
                      <button
                        onClick={() => handleAction('cancel')}
                        className="px-3 py-1.5 text-xs font-medium bg-red-100 text-red-600
                          rounded-lg hover:bg-red-200 transition-colors"
                      >
                        ✕ Batal
                      </button>
                    )}
                  </div>
                </div>

                {/* elapsed time + current screen row */}
                <div className="flex items-center gap-4 mt-3 flex-wrap">
                  {elapsed && (
                    <span className="text-xs text-gray-500 font-mono">
                      ⏱ {elapsed}
                    </span>
                  )}
                  {visionState && (
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full
                      ${SCREEN_TYPE_COLOR[visionState.screen_type] ?? 'bg-gray-100 text-gray-600'}`}>
                      👁 {visionState.screen_name}
                    </span>
                  )}
                  {visionState?.progress != null && visionState.screen_name.toLowerCase().includes('generat') && (
                    <span className="text-xs text-indigo-600 font-semibold">
                      {visionState.progress.toFixed(0)}% generated
                    </span>
                  )}
                </div>

                {/* progress bar */}
                <div className="mt-4">
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                    <span>
                      {displayState?.current_step
                        ? `▶ ${displayState.current_step.label}`
                        : 'Menunggu...'}
                    </span>
                    <span>{(displayState?.progress ?? 0).toFixed(0)}%</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                      style={{ width: `${displayState?.progress ?? 0}%` }}
                    />
                  </div>
                  {displayState?.next_step && (
                    <p className="text-xs text-gray-400 mt-1">
                      Seterusnya: {displayState.next_step.label}
                    </p>
                  )}
                </div>
              </div>

              {/* step list */}
              {displayState?.steps && displayState.steps.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 p-5">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-4">
                    Steps ({displayState.steps.length})
                  </p>
                  <div className="space-y-2">
                    {displayState.steps.map((step) => (
                      <div
                        key={step.index}
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg
                          ${step.status === 'running' ? 'bg-amber-50' : ''}
                          ${step.status === 'failed' ? 'bg-red-50' : ''}
                          ${step.status === 'success' ? 'bg-emerald-50' : ''}
                          ${step.status === 'pending' ? 'bg-gray-50' : ''}`}
                      >
                        <StepDot status={step.status} />
                        <span className="text-sm text-gray-700 flex-1">{step.label}</span>
                        {step.error && (
                          <span className="text-xs text-red-500">{step.error}</span>
                        )}
                        {step.screenshot && (
                          <a
                            href={step.screenshot}
                            target="_blank"
                            rel="noreferrer"
                            className="text-xs text-indigo-500 hover:underline"
                          >
                            screenshot
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {actionError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                  {actionError}
                </div>
              )}
            </div>
          )}
        </main>

        {/* ── RIGHT: screenshot + log ── */}
        <aside className="w-80 bg-white border-l border-gray-200 flex flex-col shrink-0">
          {/* screenshot */}
          <div className="p-4 border-b border-gray-100">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
              Screenshot
            </p>
            {displayState?.last_screenshot ? (
              <img
                src={displayState.last_screenshot}
                alt="Last screenshot"
                className="w-full rounded-lg border border-gray-200 object-contain"
                style={{ maxHeight: '260px' }}
              />
            ) : (
              <div className="h-40 bg-gray-50 rounded-lg border border-dashed border-gray-200
                flex items-center justify-center text-xs text-gray-400">
                Tiada screenshot
              </div>
            )}
          </div>

          {/* vision state */}
          {visionState && (
            <div className="p-4 border-b border-gray-100">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Vision State
              </p>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full
                    ${SCREEN_TYPE_COLOR[visionState.screen_type] ?? 'bg-gray-100 text-gray-600'}`}>
                    {visionState.screen_name}
                  </span>
                  <span className="text-xs text-gray-400">
                    {(visionState.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {visionState.loading && (
                  <p className="text-xs text-amber-600 animate-pulse">⏳ Loading…</p>
                )}
                {visionState.progress != null && (
                  <div>
                    <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                      <span>Generation</span>
                      <span>{visionState.progress.toFixed(0)}%</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                        style={{ width: `${visionState.progress}%` }}
                      />
                    </div>
                  </div>
                )}
                {visionState.buttons.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {visionState.buttons.slice(0, 5).map((b, i) => (
                      <span key={i} className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                        {b.text}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* log stream */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Log ({logs.length})
              </p>
            </div>
            <div className="flex-1 overflow-y-auto font-mono text-xs p-3 space-y-0.5 bg-gray-950">
              {logs.map((entry, i) => {
                const color =
                  entry.level === 'error'
                    ? 'text-red-400'
                    : entry.level === 'warn'
                    ? 'text-amber-400'
                    : entry.level === 'success'
                    ? 'text-emerald-400'
                    : 'text-gray-300'
                return (
                  <div key={i} className={`leading-5 ${color}`}>
                    <span className="text-gray-600 mr-2">
                      {entry.ts.slice(11, 19)}
                    </span>
                    {entry.message}
                  </div>
                )
              })}
              <div ref={logEndRef} />
            </div>
          </div>
        </aside>
      </div>

      {/* ── New Execution modal ── */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold text-gray-900">New Execution</h2>
              <button
                onClick={() => setShowForm(false)}
                className="text-gray-400 hover:text-gray-600 text-lg"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Device</label>
                <select
                  value={form.device_id}
                  onChange={(e) => setForm({ ...form, device_id: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                    focus:outline-none focus:ring-2 focus:ring-indigo-300"
                >
                  <option value="">— Pilih device —</option>
                  {devices.map((d) => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.device_name || d.device_id}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Video Prompt / Script
                </label>
                <textarea
                  value={form.video_prompt}
                  onChange={(e) => setForm({ ...form, video_prompt: e.target.value })}
                  rows={5}
                  placeholder="Masukkan script atau prompt video..."
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                    focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Image Path (local)
                </label>
                <input
                  type="text"
                  value={form.image_path}
                  onChange={(e) => setForm({ ...form, image_path: e.target.value })}
                  placeholder="C:\path\to\product.jpg"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                    focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Post Type</label>
                <select
                  value={form.post_type}
                  onChange={(e) => setForm({ ...form, post_type: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                    focus:outline-none focus:ring-2 focus:ring-indigo-300"
                >
                  <option value="draft">Draft</option>
                  <option value="post_now">Post Now</option>
                  <option value="schedule">Schedule</option>
                </select>
              </div>

              {actionError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                  {actionError}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setShowForm(false)}
                  className="flex-1 py-2 border border-gray-300 rounded-lg text-sm
                    text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Batal
                </button>
                <button
                  onClick={handleStart}
                  disabled={starting || !form.device_id || !form.video_prompt || !form.image_path}
                  className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium
                    hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {starting ? 'Starting...' : '▶ Start Execution'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
