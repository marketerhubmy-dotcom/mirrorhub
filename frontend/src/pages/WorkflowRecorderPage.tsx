import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { workflowApi } from '../services/workflowApi'
import { useDevices } from '../hooks/useDevices'
import type { WorkflowStep, RecordingSession } from '../types/workflow'
import { STEP_TYPE_LABELS } from '../types/workflow'

const QUICK_STEPS: { label: string; type: string; params: Record<string, unknown> }[] = [
  { label: '← Back',  type: 'back',         params: {} },
  { label: '⌂ Home',  type: 'home',         params: {} },
  { label: '⏳ Wait',  type: 'wait',         params: { seconds: 2 } },
  { label: '📸 Shot', type: 'take_screenshot', params: {} },
]

function StepChip({ step, index, onRemove }: {
  step: WorkflowStep
  index: number
  onRemove: () => void
}) {
  return (
    <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-2 group">
      <span className="text-xs text-gray-400 w-5 text-right shrink-0">{index + 1}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{step.label}</p>
        <p className="text-xs text-gray-400">{STEP_TYPE_LABELS[step.step_type] ?? step.step_type}</p>
      </div>
      <button onClick={onRemove}
        className="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
        ✕
      </button>
    </div>
  )
}

export default function WorkflowRecorderPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()

  const [selectedDevice, setSelectedDevice] = useState('')
  const [session, setSession] = useState<RecordingSession | null>(null)
  const [recording, setRecording] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wsMessages, setWsMessages] = useState<string[]>([])

  // Add step form
  const [addType, setAddType] = useState('tap_button')
  const [addLabel, setAddLabel] = useState('')
  const [addParams, setAddParams] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)

  // Save modal
  const [showSave, setShowSave] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveApp, setSaveApp] = useState('generic')
  const [saving, setSaving] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)

  const scrollToBottom = () => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }

  useEffect(() => scrollToBottom(), [session?.steps])

  const connectWs = useCallback((sessionId: string) => {
    if (wsRef.current) { wsRef.current.close() }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/workflow/${sessionId}`)
    ws.onmessage = ev => {
      try {
        const msg = JSON.parse(ev.data)
        setWsMessages(prev => [...prev.slice(-19), `[${msg.event}] ${JSON.stringify(msg.data ?? '')}`])
        if (msg.event === 'recorder_new_step' || msg.event === 'recorder_step_removed') {
          workflowApi.recorderGet(sessionId).then(s => setSession(s)).catch(() => {})
        }
      } catch {}
    }
    wsRef.current = ws
    return () => ws.close()
  }, [])

  useEffect(() => {
    if (session) { return connectWs(session.session_id) }
  }, [session?.session_id, connectWs])

  async function handleStart() {
    if (!selectedDevice) return
    setLoading(true)
    setError(null)
    try {
      const s = await workflowApi.recorderStart(selectedDevice, 'New Recording')
      setSession(s)
      setRecording(true)
      setSaveName(s.name)
    } catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  async function handleQuickStep(type: string, params: Record<string, unknown>) {
    if (!session) return
    try {
      const res = await workflowApi.recorderAddStep(session.session_id, {
        step_type: type,
        label: STEP_TYPE_LABELS[type] ?? type,
        parameters: params,
      })
      setSession(prev => prev ? { ...prev, steps: [...prev.steps.slice(0, res.total_steps - 1), res.step], step_count: res.total_steps } : prev)
    } catch (e) { setError((e as Error).message) }
  }

  async function handleAddCustom() {
    if (!session) return
    let params: Record<string, unknown> = {}
    if (addParams.trim()) {
      try { params = JSON.parse(addParams) }
      catch { setError('Parameters must be valid JSON'); return }
    }
    try {
      const res = await workflowApi.recorderAddStep(session.session_id, {
        step_type: addType,
        label: addLabel || (STEP_TYPE_LABELS[addType] ?? addType),
        parameters: params,
      })
      setSession(prev => prev ? { ...prev, steps: [...prev.steps.slice(0, res.total_steps - 1), res.step], step_count: res.total_steps } : prev)
      setAddLabel('')
      setAddParams('')
      setShowAddForm(false)
    } catch (e) { setError((e as Error).message) }
  }

  async function handleRemoveStep(index: number) {
    if (!session) return
    try {
      await workflowApi.recorderRemoveStep(session.session_id, index)
      setSession(prev => {
        if (!prev) return prev
        const steps = [...prev.steps]
        steps.splice(index, 1)
        return { ...prev, steps, step_count: prev.step_count - 1 }
      })
    } catch (e) { setError((e as Error).message) }
  }

  async function handleStop(save: boolean) {
    if (!session) return
    if (save) {
      setShowSave(true)
      return
    }
    try {
      await workflowApi.recorderStop(session.session_id, { save: false })
      wsRef.current?.close()
      setSession(null)
      setRecording(false)
    } catch (e) { setError((e as Error).message) }
  }

  async function handleSave() {
    if (!session) return
    setSaving(true)
    try {
      const res = await workflowApi.recorderStop(session.session_id, {
        name: saveName,
        application: saveApp,
        save: true,
      })
      wsRef.current?.close()
      if (res.workflow) {
        navigate(`/workflows/${res.workflow.id}/edit`)
      } else {
        navigate('/workflows')
      }
    } catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/workflows')} className="text-gray-400 hover:text-gray-600 text-sm">← Workflows</button>
          <span className="text-gray-300">/</span>
          <h1 className="text-lg font-bold text-gray-900">Workflow Recorder</h1>
          {recording && (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded-full">
              <span className="w-2 h-2 bg-rose-500 rounded-full animate-pulse" />
              Recording
            </span>
          )}
        </div>
        {recording && (
          <div className="flex items-center gap-2">
            <button onClick={() => handleStop(false)}
              className="px-3 py-1.5 text-xs font-medium border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100">
              Discard
            </button>
            <button onClick={() => handleStop(true)}
              className="px-3 py-1.5 text-xs font-medium bg-emerald-600 text-white rounded-lg hover:bg-emerald-700">
              ⏹ Stop & Save
            </button>
          </div>
        )}
      </header>

      {error && (
        <div className="mx-6 mt-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 flex justify-between items-start">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-4 text-red-400 hover:text-red-600">✕</button>
        </div>
      )}

      {!recording && (
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 w-full max-w-sm text-center">
            <p className="text-4xl mb-3">⏺</p>
            <h2 className="font-bold text-gray-900 text-lg mb-1">Start Recording</h2>
            <p className="text-gray-500 text-sm mb-6">Select a device to begin capturing workflow steps</p>
            <select value={selectedDevice} onChange={e => setSelectedDevice(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-300">
              <option value="">— Select device —</option>
              {devices.map(d => (
                <option key={d.device_id} value={d.device_id}>{d.device_name || d.device_id}</option>
              ))}
            </select>
            <button onClick={handleStart} disabled={!selectedDevice || loading}
              className="w-full py-2.5 bg-rose-600 text-white rounded-lg font-semibold text-sm hover:bg-rose-700 disabled:opacity-40">
              {loading ? 'Starting...' : '⏺ Start Recording'}
            </button>
          </div>
        </div>
      )}

      {recording && session && (
        <div className="flex flex-1 overflow-hidden">
          {/* ── Left: quick actions + add step ── */}
          <aside className="w-64 bg-white border-r border-gray-200 p-4 flex flex-col gap-4 shrink-0 overflow-y-auto">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Quick Actions</p>
              <div className="grid grid-cols-2 gap-2">
                {QUICK_STEPS.map(qs => (
                  <button key={qs.type} onClick={() => handleQuickStep(qs.type, qs.params)}
                    className="py-2 text-xs font-medium border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50">
                    {qs.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Add Step</p>
              <button onClick={() => setShowAddForm(v => !v)}
                className="w-full py-2 text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100">
                {showAddForm ? '− Collapse' : '+ Custom Step'}
              </button>
              {showAddForm && (
                <div className="mt-3 space-y-2">
                  <select value={addType} onChange={e => setAddType(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-300">
                    {Object.keys(STEP_TYPE_LABELS).map(t => (
                      <option key={t} value={t}>{STEP_TYPE_LABELS[t]}</option>
                    ))}
                  </select>
                  <input value={addLabel} onChange={e => setAddLabel(e.target.value)}
                    placeholder="Label (optional)"
                    className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-300" />
                  <textarea value={addParams} onChange={e => setAddParams(e.target.value)}
                    placeholder='{"button": "Next"}'
                    rows={3}
                    className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-indigo-300 resize-none" />
                  <button onClick={handleAddCustom}
                    className="w-full py-1.5 bg-indigo-600 text-white text-xs rounded-lg font-medium">
                    Add
                  </button>
                </div>
              )}
            </div>

            {/* WebSocket event log */}
            <div className="mt-auto">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Events</p>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {wsMessages.length === 0 && <p className="text-xs text-gray-300">Waiting for events...</p>}
                {wsMessages.map((m, i) => (
                  <p key={i} className="text-xs text-gray-400 font-mono leading-tight">{m}</p>
                ))}
              </div>
            </div>
          </aside>

          {/* ── Right: recorded step list ── */}
          <main className="flex-1 overflow-y-auto p-6" ref={listRef}>
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm font-semibold text-gray-700">
                Steps captured: <span className="text-indigo-600">{session.step_count}</span>
              </p>
              <p className="text-xs text-gray-400">Device: {selectedDevice}</p>
            </div>
            {session.steps.length === 0 && (
              <div className="text-center py-16">
                <p className="text-3xl mb-2">👆</p>
                <p className="text-gray-500 text-sm">Use quick actions or add custom steps to record a workflow</p>
              </div>
            )}
            <div className="space-y-2 max-w-lg">
              {session.steps.map((step, idx) => (
                <StepChip key={step.id} step={step} index={idx} onRemove={() => handleRemoveStep(idx)} />
              ))}
            </div>
          </main>
        </div>
      )}

      {/* ── Save modal ── */}
      {showSave && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h2 className="text-lg font-bold mb-4">Save Workflow</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
                <input value={saveName} onChange={e => setSaveName(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Application</label>
                <select value={saveApp} onChange={e => setSaveApp(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
                  <option value="generic">Generic</option>
                  <option value="youtube_create">YouTube Create</option>
                  <option value="tiktok">TikTok</option>
                  <option value="capcut">CapCut</option>
                </select>
              </div>
              <p className="text-xs text-gray-400">{session?.step_count ?? 0} steps will be saved</p>
              <div className="flex gap-2 pt-1">
                <button onClick={() => setShowSave(false)} className="flex-1 py-2 border border-gray-300 rounded-lg text-sm">Back</button>
                <button onClick={handleSave} disabled={saving || !saveName.trim()}
                  className="flex-1 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                  {saving ? 'Saving...' : 'Save & Open Editor'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
