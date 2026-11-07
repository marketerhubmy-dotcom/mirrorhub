import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { workflowApi } from '../services/workflowApi'
import { useDevices } from '../hooks/useDevices'
import type { Workflow, WorkflowExecution } from '../types/workflow'
import { EXECUTION_STATUS_COLOR } from '../types/workflow'

export default function WorkflowManagerPage() {
  const navigate = useNavigate()
  const { devices } = useDevices()
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [executions, setExecutions] = useState<WorkflowExecution[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newApp, setNewApp] = useState('generic')
  const [playTarget, setPlayTarget] = useState<{ wf: Workflow; deviceId: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [wfs, execs] = await Promise.all([
        workflowApi.list(),
        workflowApi.listExecutions(),
      ])
      setWorkflows(wfs)
      setExecutions(execs.slice(0, 10))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleCreate() {
    if (!newName.trim()) return
    try {
      const wf = await workflowApi.create({ name: newName.trim(), application: newApp })
      setShowCreate(false)
      setNewName('')
      navigate(`/workflows/${wf.id}/edit`)
    } catch (e) { setError((e as Error).message) }
  }

  async function handleDelete(id: number) {
    if (!confirm('Delete this workflow?')) return
    try {
      await workflowApi.remove(id)
      setWorkflows(prev => prev.filter(w => w.id !== id))
    } catch (e) { setError((e as Error).message) }
  }

  async function handlePlay() {
    if (!playTarget) return
    try {
      const res = await workflowApi.play(playTarget.wf.id, playTarget.deviceId)
      setPlayTarget(null)
      navigate(`/workflows/executions/${res.execution_id}`)
    } catch (e) { setError((e as Error).message) }
  }

  async function handleExport(id: number) {
    window.open(workflowApi.exportUrl(id), '_blank')
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      await workflowApi.importWorkflow(data)
      await load()
    } catch (err) { setError((err as Error).message) }
    e.target.value = ''
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-gray-400 hover:text-gray-600 text-sm">← Dashboard</button>
          <span className="text-gray-300">/</span>
          <h1 className="text-lg font-bold text-gray-900">Workflow Manager</h1>
        </div>
        <div className="flex items-center gap-2">
          <label className="px-3 py-2 text-sm font-medium bg-gray-100 text-gray-700 rounded-lg
            hover:bg-gray-200 transition-colors cursor-pointer">
            📥 Import
            <input type="file" accept=".json" className="hidden" onChange={handleImport} />
          </label>
          <button onClick={() => navigate('/workflows/record')}
            className="px-3 py-2 text-sm font-medium bg-rose-600 text-white rounded-lg hover:bg-rose-700 transition-colors">
            ⏺ Record
          </button>
          <button onClick={() => setShowCreate(true)}
            className="px-3 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors">
            + New Workflow
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* ── Workflow list ── */}
        <main className="flex-1 overflow-y-auto p-6">
          {error && <div className="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{error}</div>}
          {loading && <p className="text-sm text-gray-400">Loading...</p>}
          {!loading && workflows.length === 0 && (
            <div className="text-center py-16">
              <p className="text-4xl mb-3">🎬</p>
              <p className="text-gray-600 font-medium">No workflows yet</p>
              <p className="text-gray-400 text-sm mt-1">Create one or record a new workflow</p>
            </div>
          )}
          <div className="space-y-3">
            {workflows.map(wf => (
              <div key={wf.id} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-900 truncate">{wf.name}</span>
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{wf.application}</span>
                    <span className="text-xs text-gray-400">v{wf.current_version}</span>
                  </div>
                  {wf.description && <p className="text-xs text-gray-500 mt-0.5 truncate">{wf.description}</p>}
                  <p className="text-xs text-gray-400 mt-1">{wf.step_count ?? 0} steps</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => setPlayTarget({ wf, deviceId: '' })}
                    className="px-3 py-1.5 text-xs font-medium bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200">
                    ▶ Play
                  </button>
                  <button onClick={() => navigate(`/workflows/${wf.id}/edit`)}
                    className="px-3 py-1.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded-lg hover:bg-indigo-200">
                    ✏️ Edit
                  </button>
                  <button onClick={() => handleExport(wf.id)}
                    className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200">
                    📤
                  </button>
                  <button onClick={() => handleDelete(wf.id)}
                    className="px-3 py-1.5 text-xs font-medium bg-red-100 text-red-600 rounded-lg hover:bg-red-200">
                    🗑
                  </button>
                </div>
              </div>
            ))}
          </div>
        </main>

        {/* ── Recent executions sidebar ── */}
        <aside className="w-72 bg-white border-l border-gray-200 overflow-y-auto shrink-0 p-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Recent Executions
          </p>
          {executions.length === 0 && (
            <p className="text-xs text-gray-400">No executions yet</p>
          )}
          {executions.map(ex => (
            <button key={ex.id}
              onClick={() => navigate(`/workflows/executions/${ex.id}`)}
              className="w-full text-left p-3 rounded-lg border border-gray-100 hover:bg-gray-50 mb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold text-gray-700">#{ex.id}</span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${EXECUTION_STATUS_COLOR[ex.status] ?? 'bg-gray-100 text-gray-600'}`}>
                  {ex.status}
                </span>
              </div>
              <p className="text-xs text-gray-500 truncate">wf#{ex.workflow_id} · {ex.device_id}</p>
              <div className="mt-1.5 h-1 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-400 rounded-full" style={{ width: `${ex.progress}%` }} />
              </div>
            </button>
          ))}
        </aside>
      </div>

      {/* ── Create modal ── */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h2 className="text-lg font-bold mb-4">New Workflow</h2>
            <div className="space-y-3">
              <input value={newName} onChange={e => setNewName(e.target.value)}
                placeholder="Workflow name..."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
              <select value={newApp} onChange={e => setNewApp(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
                <option value="generic">Generic</option>
                <option value="youtube_create">YouTube Create</option>
                <option value="tiktok">TikTok</option>
                <option value="capcut">CapCut</option>
              </select>
              <div className="flex gap-2 pt-1">
                <button onClick={() => setShowCreate(false)} className="flex-1 py-2 border border-gray-300 rounded-lg text-sm">Cancel</button>
                <button onClick={handleCreate} className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium">Create</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Play modal ── */}
      {playTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h2 className="text-lg font-bold mb-1">Play Workflow</h2>
            <p className="text-sm text-gray-500 mb-4">{playTarget.wf.name}</p>
            <select value={playTarget.deviceId}
              onChange={e => setPlayTarget(t => t ? { ...t, deviceId: e.target.value } : t)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-indigo-300">
              <option value="">— Select device —</option>
              {devices.map(d => <option key={d.device_id} value={d.device_id}>{d.device_name || d.device_id}</option>)}
            </select>
            <div className="flex gap-2">
              <button onClick={() => setPlayTarget(null)} className="flex-1 py-2 border border-gray-300 rounded-lg text-sm">Cancel</button>
              <button onClick={handlePlay} disabled={!playTarget.deviceId}
                className="flex-1 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                ▶ Start
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
