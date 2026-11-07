import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { workflowApi } from '../services/workflowApi'
import type { Workflow, WorkflowStep, WorkflowVersion } from '../types/workflow'
import { STEP_TYPE_LABELS } from '../types/workflow'

const ALL_STEP_TYPES = Object.keys(STEP_TYPE_LABELS)

function StepRow({
  step, selected, onSelect, onToggle, onDelete, onMoveUp, onMoveDown, onDuplicate,
}: {
  step: WorkflowStep
  selected: boolean
  onSelect: () => void
  onToggle: () => void
  onDelete: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  onDuplicate: () => void
}) {
  return (
    <div
      onClick={onSelect}
      className={`flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer border transition-colors
        ${selected ? 'border-indigo-300 bg-indigo-50' : 'border-transparent hover:bg-gray-50'}
        ${!step.enabled ? 'opacity-40' : ''}`}
    >
      <span className="text-xs text-gray-400 w-5 text-right shrink-0">{step.order + 1}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">{step.label}</p>
        <p className="text-xs text-gray-400">{STEP_TYPE_LABELS[step.step_type] ?? step.step_type}</p>
      </div>
      <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
        <button onClick={onMoveUp} title="Move up" className="p-1 text-gray-400 hover:text-gray-700">▲</button>
        <button onClick={onMoveDown} title="Move down" className="p-1 text-gray-400 hover:text-gray-700">▼</button>
        <button onClick={onDuplicate} title="Duplicate" className="p-1 text-gray-400 hover:text-gray-700">⎘</button>
        <button onClick={onToggle} title={step.enabled ? 'Disable' : 'Enable'}
          className={`p-1 ${step.enabled ? 'text-emerald-500' : 'text-gray-300'} hover:opacity-80`}>
          ●
        </button>
        <button onClick={onDelete} title="Delete" className="p-1 text-red-400 hover:text-red-600">✕</button>
      </div>
    </div>
  )
}

export default function WorkflowEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const workflowId = Number(id)

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [steps, setSteps] = useState<WorkflowStep[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [versions, setVersions] = useState<WorkflowVersion[]>([])
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[]; warnings: string[] } | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAddStep, setShowAddStep] = useState(false)
  const [newStepType, setNewStepType] = useState('tap_button')
  const [newStepLabel, setNewStepLabel] = useState('')

  const load = useCallback(async () => {
    try {
      const [wf, vList] = await Promise.all([
        workflowApi.get(workflowId),
        workflowApi.listVersions(workflowId),
      ])
      setWorkflow(wf)
      setSteps(wf.steps ?? [])
      setVersions(vList)
    } catch (e) { setError((e as Error).message) }
  }, [workflowId])

  useEffect(() => { load() }, [load])

  const reload = async () => {
    const wf = await workflowApi.get(workflowId)
    setSteps(wf.steps ?? [])
  }

  const selectedStep = steps.find(s => s.id === selectedId) ?? null

  async function handleAddStep() {
    try {
      await workflowApi.addStep(workflowId, {
        step_type: newStepType,
        label: newStepLabel || (STEP_TYPE_LABELS[newStepType] ?? newStepType),
      })
      setShowAddStep(false)
      setNewStepLabel('')
      await reload()
    } catch (e) { setError((e as Error).message) }
  }

  async function handleToggle(step: WorkflowStep) {
    await workflowApi.updateStep(workflowId, step.id, { enabled: !step.enabled } as Partial<WorkflowStep>)
    await reload()
  }

  async function handleDelete(stepId: number) {
    if (!confirm('Delete this step?')) return
    await workflowApi.deleteStep(workflowId, stepId)
    if (selectedId === stepId) setSelectedId(null)
    await reload()
  }

  async function handleMoveUp(stepId: number) {
    const updated = await workflowApi.moveStepUp(workflowId, stepId)
    setSteps(updated)
  }

  async function handleMoveDown(stepId: number) {
    const updated = await workflowApi.moveStepDown(workflowId, stepId)
    setSteps(updated)
  }

  async function handleDuplicate(stepId: number) {
    await workflowApi.duplicateStep(workflowId, stepId)
    await reload()
  }

  async function handleSaveVersion() {
    setSaving(true)
    try {
      await workflowApi.saveVersion(workflowId, 'Manual save')
      await load()
      setValidation(null)
    } catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  async function handleValidate() {
    const result = await workflowApi.validate(workflowId)
    setValidation(result)
  }

  async function handleRollback(version: number) {
    if (!confirm(`Rollback to v${version}?`)) return
    await workflowApi.rollback(workflowId, version)
    await load()
  }

  async function handleStepParamChange(key: string, value: string) {
    if (!selectedStep) return
    const params = { ...selectedStep.parameters, [key]: value }
    const updated = await workflowApi.updateStep(workflowId, selectedStep.id, { parameters: params } as Partial<WorkflowStep>)
    setSteps(prev => prev.map(s => s.id === updated.id ? updated : s))
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/workflows')} className="text-gray-400 hover:text-gray-600 text-sm">← Workflows</button>
          <span className="text-gray-300">/</span>
          <span className="text-gray-900 font-semibold">{workflow?.name ?? '...'}</span>
          <span className="text-xs text-gray-400">v{workflow?.current_version ?? 0}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleValidate} className="px-3 py-1.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200">
            ✓ Validate
          </button>
          <button onClick={handleSaveVersion} disabled={saving}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
            {saving ? 'Saving...' : '💾 Save Version'}
          </button>
        </div>
      </header>

      {error && (
        <div className="mx-6 mt-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
          {error}
        </div>
      )}

      {validation && (
        <div className={`mx-6 mt-3 border rounded-lg p-3 text-sm
          ${validation.valid ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-700'}`}>
          {validation.valid ? '✓ Valid' : '⚠ Issues found'}
          {validation.errors.map((e, i) => <p key={i} className="text-xs mt-1">❌ {e}</p>)}
          {validation.warnings.map((w, i) => <p key={i} className="text-xs mt-1 text-amber-700">⚠ {w}</p>)}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* ── Left: step list ── */}
        <aside className="w-72 bg-white border-r border-gray-200 flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Steps ({steps.length})
            </p>
            <button onClick={() => setShowAddStep(true)}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800">+ Add</button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {steps.map(step => (
              <StepRow
                key={step.id} step={step} selected={selectedId === step.id}
                onSelect={() => setSelectedId(step.id)}
                onToggle={() => handleToggle(step)}
                onDelete={() => handleDelete(step.id)}
                onMoveUp={() => handleMoveUp(step.id)}
                onMoveDown={() => handleMoveDown(step.id)}
                onDuplicate={() => handleDuplicate(step.id)}
              />
            ))}
            {steps.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-8">No steps. Click + Add to begin.</p>
            )}
          </div>
        </aside>

        {/* ── Center: step editor ── */}
        <main className="flex-1 overflow-y-auto p-6">
          {!selectedStep && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-3xl mb-2">🎬</p>
                <p className="text-gray-500">Select a step to edit it</p>
              </div>
            </div>
          )}
          {selectedStep && (
            <div className="max-w-lg space-y-5">
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="font-semibold text-gray-900 mb-4">Step Details</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Label</label>
                    <input
                      defaultValue={selectedStep.label}
                      onBlur={async e => {
                        await workflowApi.updateStep(workflowId, selectedStep.id, { label: e.target.value } as Partial<WorkflowStep>)
                        await reload()
                      }}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Step Type</label>
                    <select
                      value={selectedStep.step_type}
                      onChange={async e => {
                        await workflowApi.updateStep(workflowId, selectedStep.id, { step_type: e.target.value } as Partial<WorkflowStep>)
                        await reload()
                        setSelectedId(selectedStep.id)
                      }}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                    >
                      {ALL_STEP_TYPES.map(t => (
                        <option key={t} value={t}>{STEP_TYPE_LABELS[t]}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Retry Max</label>
                      <input type="number" min={0} max={10} defaultValue={selectedStep.retry_max}
                        onBlur={async e => {
                          await workflowApi.updateStep(workflowId, selectedStep.id, { retry_max: Number(e.target.value) } as Partial<WorkflowStep>)
                        }}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="block text-xs font-medium text-gray-600 mb-1">Timeout (s)</label>
                      <input type="number" min={1} defaultValue={selectedStep.timeout}
                        onBlur={async e => {
                          await workflowApi.updateStep(workflowId, selectedStep.id, { timeout: Number(e.target.value) } as Partial<WorkflowStep>)
                        }}
                        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Parameters */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="font-semibold text-gray-900 mb-4">Parameters</h3>
                {Object.entries(selectedStep.parameters).map(([k, v]) => (
                  <div key={k} className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-1">{k}</label>
                    <input
                      defaultValue={String(v)}
                      onBlur={e => handleStepParamChange(k, e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                    />
                  </div>
                ))}
                <p className="text-xs text-gray-400 mt-2">
                  Use <code className="bg-gray-100 px-1 rounded">{'{{variable}}'}</code> for dynamic values
                </p>
              </div>

              {/* Conditions */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="font-semibold text-gray-900 mb-3">Conditions</h3>
                <div className="space-y-2">
                  {(['if_button_exists', 'if_not_button', 'if_screen'] as const).map(key => (
                    <div key={key} className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 w-36 shrink-0">{key}</span>
                      <input
                        defaultValue={String((selectedStep.conditions as Record<string, unknown>)[key] ?? '')}
                        placeholder="(empty = no condition)"
                        onBlur={async e => {
                          const cond = { ...selectedStep.conditions }
                          if (e.target.value) {
                            (cond as Record<string, string>)[key] = e.target.value
                          } else {
                            delete (cond as Record<string, unknown>)[key]
                          }
                          await workflowApi.updateStep(workflowId, selectedStep.id, { conditions: cond } as Partial<WorkflowStep>)
                        }}
                        className="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-300"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>

        {/* ── Right: versions ── */}
        <aside className="w-56 bg-white border-l border-gray-200 flex flex-col shrink-0 p-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Versions</p>
          {versions.length === 0 && (
            <p className="text-xs text-gray-400">No saved versions</p>
          )}
          {versions.map(v => (
            <div key={v.id} className="mb-3 p-2.5 rounded-lg border border-gray-100 bg-gray-50">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs font-semibold text-gray-700">v{v.version}</span>
                <button onClick={() => handleRollback(v.version)}
                  className="text-xs text-indigo-600 hover:underline">Restore</button>
              </div>
              {v.notes && <p className="text-xs text-gray-500 truncate">{v.notes}</p>}
              <p className="text-xs text-gray-400 mt-0.5">
                {v.created_at ? new Date(v.created_at).toLocaleDateString() : ''}
              </p>
            </div>
          ))}
        </aside>
      </div>

      {/* ── Add step modal ── */}
      {showAddStep && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h2 className="text-lg font-bold mb-4">Add Step</h2>
            <div className="space-y-3">
              <select value={newStepType} onChange={e => setNewStepType(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
                {ALL_STEP_TYPES.map(t => <option key={t} value={t}>{STEP_TYPE_LABELS[t]}</option>)}
              </select>
              <input value={newStepLabel} onChange={e => setNewStepLabel(e.target.value)}
                placeholder="Step label (optional)"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
              <div className="flex gap-2 pt-1">
                <button onClick={() => setShowAddStep(false)} className="flex-1 py-2 border border-gray-300 rounded-lg text-sm">Cancel</button>
                <button onClick={handleAddStep} className="flex-1 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium">Add</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
