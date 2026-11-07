import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { campaignApi, Campaign, CampaignCreate, ValidationResult } from '../services/campaignApi'

const STATUS_COLOR: Record<string, string> = {
  DRAFT: 'bg-gray-500',
  SCHEDULED: 'bg-blue-500',
  RUNNING: 'bg-green-500',
  PAUSED: 'bg-yellow-500',
  COMPLETED: 'bg-indigo-500',
  FAILED: 'bg-red-500',
  CANCELLED: 'bg-gray-400',
}

function ProgressBar({ total, completed }: { total: number; completed: number }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0
  return (
    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mt-1">
      <div
        className="bg-indigo-500 h-1.5 rounded-full transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function CampaignCard({
  campaign,
  onStart,
  onPause,
  onResume,
  onCancel,
  onDelete,
  onView,
}: {
  campaign: Campaign
  onStart: (simulate: boolean) => void
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  onDelete: () => void
  onView: () => void
}) {
  const [validating, setValidating] = useState(false)
  const [validation, setValidation] = useState<ValidationResult | null>(null)

  async function handleValidate() {
    setValidating(true)
    try {
      const v = await campaignApi.validate(campaign.id)
      setValidation(v)
    } finally {
      setValidating(false)
    }
  }

  const pct =
    campaign.total_jobs > 0
      ? Math.round((campaign.completed_jobs / campaign.total_jobs) * 100)
      : 0

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block text-xs text-white px-2 py-0.5 rounded-full ${STATUS_COLOR[campaign.status] ?? 'bg-gray-500'}`}
            >
              {campaign.status}
            </span>
            <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">{campaign.name}</h3>
          </div>
          {campaign.description && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 truncate">{campaign.description}</p>
          )}
        </div>
        <button onClick={onView} className="text-xs text-indigo-500 hover:underline shrink-0">
          View Jobs
        </button>
      </div>

      {/* Progress */}
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {campaign.completed_jobs}/{campaign.total_jobs} jobs · {campaign.failed_jobs} failed · {pct}%
        <ProgressBar total={campaign.total_jobs} completed={campaign.completed_jobs} />
      </div>

      {/* Validation messages */}
      {validation && (
        <div
          className={`text-xs rounded p-2 ${validation.valid ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'}`}
        >
          {validation.valid ? '✓ Valid' : validation.errors.join(' · ')}
          {validation.warnings.length > 0 && (
            <div className="text-yellow-600 dark:text-yellow-400 mt-1">
              ⚠ {validation.warnings.join(' · ')}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {campaign.status === 'DRAFT' || campaign.status === 'COMPLETED' || campaign.status === 'FAILED' ? (
          <>
            <button
              onClick={() => onStart(false)}
              className="text-xs bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded"
            >
              Start
            </button>
            <button
              onClick={() => onStart(true)}
              className="text-xs bg-green-100 dark:bg-green-900/30 hover:bg-green-200 dark:hover:bg-green-900/50 text-green-800 dark:text-green-300 px-3 py-1 rounded"
            >
              Simulate
            </button>
          </>
        ) : campaign.status === 'RUNNING' ? (
          <>
            <button
              onClick={onPause}
              className="text-xs bg-yellow-500 hover:bg-yellow-600 text-white px-3 py-1 rounded"
            >
              Pause
            </button>
            <button
              onClick={onCancel}
              className="text-xs bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded"
            >
              Cancel
            </button>
          </>
        ) : campaign.status === 'PAUSED' ? (
          <>
            <button
              onClick={onResume}
              className="text-xs bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded"
            >
              Resume
            </button>
            <button
              onClick={onCancel}
              className="text-xs bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded"
            >
              Cancel
            </button>
          </>
        ) : null}

        <button
          onClick={handleValidate}
          disabled={validating}
          className="text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 px-3 py-1 rounded"
        >
          {validating ? '…' : 'Validate'}
        </button>
        <button
          onClick={onDelete}
          className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded"
        >
          Delete
        </button>
      </div>
    </div>
  )
}

// ── Create Campaign Modal ─────────────────────────────────────────────────────

function CreateCampaignModal({
  onClose,
  onCreate,
}: {
  onClose: () => void
  onCreate: (c: Campaign) => void
}) {
  const [form, setForm] = useState<CampaignCreate>({ name: '', description: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit() {
    if (!form.name.trim()) { setError('Name is required'); return }
    setLoading(true)
    try {
      const c = await campaignApi.create(form)
      onCreate(c)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">New Campaign</h2>
        <div className="flex flex-col gap-3">
          <div>
            <label className="text-xs text-gray-500 dark:text-gray-400">Name *</label>
            <input
              className="w-full mt-1 border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="My campaign"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 dark:text-gray-400">Description</label>
            <textarea
              className="w-full mt-1 border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 h-20 resize-none"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-400">Platform default</label>
              <select
                className="w-full mt-1 border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
                value={form.platform_default ?? ''}
                onChange={e => setForm(f => ({ ...f, platform_default: e.target.value }))}
              >
                <option value="">— any —</option>
                <option value="tiktok">TikTok</option>
                <option value="youtube_create">YouTube Create</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 dark:text-gray-400">Timezone</label>
              <input
                className="w-full mt-1 border border-gray-300 dark:border-gray-600 rounded px-3 py-1.5 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
                value={form.timezone ?? ''}
                onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))}
                placeholder="UTC"
              />
            </div>
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="text-sm px-4 py-1.5 rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="text-sm px-4 py-1.5 rounded bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50"
          >
            {loading ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CampaignManagerPage() {
  const navigate = useNavigate()
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [wsMessages, setWsMessages] = useState<string[]>([])

  useEffect(() => {
    campaignApi.list().then(setCampaigns).finally(() => setLoading(false))
  }, [])

  // Live updates from queue WebSocket
  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/ws/campaign/queue`)
    ws.onmessage = evt => {
      setWsMessages(prev => [evt.data, ...prev].slice(0, 20))
      // Refresh campaigns when queue changes
      campaignApi.list().then(setCampaigns)
    }
    return () => ws.close()
  }, [])

  async function refresh() {
    setCampaigns(await campaignApi.list())
  }

  async function handleStart(id: number, simulate: boolean) {
    await campaignApi.start(id, simulate)
    refresh()
  }

  async function handlePause(id: number) {
    await campaignApi.pause(id)
    refresh()
  }

  async function handleResume(id: number) {
    await campaignApi.resume(id)
    refresh()
  }

  async function handleCancel(id: number) {
    await campaignApi.cancel(id)
    refresh()
  }

  async function handleDelete(id: number) {
    if (!confirm('Delete this campaign?')) return
    await campaignApi.delete(id)
    setCampaigns(prev => prev.filter(c => c.id !== id))
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            ← Dashboard
          </button>
          <h1 className="text-xl font-semibold">Campaigns</h1>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate('/queue')}
            className="text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 px-3 py-1.5 rounded"
          >
            Queue Monitor →
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded"
          >
            + New Campaign
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-lg font-medium">No campaigns yet</p>
          <p className="text-sm mt-1">Create a campaign to start scheduling jobs</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {campaigns.map(c => (
            <CampaignCard
              key={c.id}
              campaign={c}
              onStart={simulate => handleStart(c.id, simulate)}
              onPause={() => handlePause(c.id)}
              onResume={() => handleResume(c.id)}
              onCancel={() => handleCancel(c.id)}
              onDelete={() => handleDelete(c.id)}
              onView={() => navigate(`/campaigns/${c.id}/jobs`)}
            />
          ))}
        </div>
      )}

      {/* Live event log */}
      {wsMessages.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Live Events</h2>
          <div className="bg-black rounded-lg p-3 max-h-40 overflow-y-auto font-mono text-xs text-green-400 space-y-1">
            {wsMessages.map((m, i) => (
              <div key={i} className="truncate">{m}</div>
            ))}
          </div>
        </div>
      )}

      {showCreate && (
        <CreateCampaignModal
          onClose={() => setShowCreate(false)}
          onCreate={c => {
            setCampaigns(prev => [c, ...prev])
            setShowCreate(false)
          }}
        />
      )}
    </div>
  )
}
