import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { campaignApi, QueueEntry, QueueState } from '../services/campaignApi'

const STATUS_COLOR: Record<string, string> = {
  READY: 'bg-blue-500',
  RUNNING: 'bg-green-500',
  PAUSED: 'bg-yellow-500',
  WAITING: 'bg-gray-400',
  RETRY: 'bg-orange-500',
  COMPLETED: 'bg-indigo-500',
  FAILED: 'bg-red-500',
  CANCELLED: 'bg-gray-300 text-gray-600',
}

const PRIORITY_LABEL = ['CRITICAL', 'HIGH', 'NORMAL', 'LOW']
const PRIORITY_COLOR = ['text-red-500', 'text-orange-500', 'text-blue-500', 'text-gray-500']

function CountBadge({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div className={`flex flex-col items-center px-3 py-2 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 min-w-[70px]`}>
      <span className={`text-lg font-bold tabular-nums ${color}`}>{count}</span>
      <span className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{label}</span>
    </div>
  )
}

function QueueRow({
  entry,
  onPause,
  onResume,
  onCancel,
  onRetry,
}: {
  entry: QueueEntry
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  onRetry: () => void
}) {
  const cj = entry.campaign_job
  const priority = cj?.priority ?? 2

  return (
    <div className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      {/* Order */}
      <div className="text-sm font-mono text-gray-400 w-6 text-right shrink-0">
        {entry.queue_order}
      </div>

      {/* Status pill */}
      <span
        className={`text-xs text-white px-2 py-0.5 rounded-full shrink-0 ${STATUS_COLOR[entry.status] ?? 'bg-gray-400'}`}
      >
        {entry.status}
      </span>

      {/* Platform + priority */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {cj?.platform ?? '—'}
          </span>
          <span className={`text-xs ${PRIORITY_COLOR[priority]}`}>
            {PRIORITY_LABEL[priority]}
          </span>
        </div>
        {cj?.device_id && (
          <div className="text-xs text-gray-400 truncate">{cj.device_id}</div>
        )}
      </div>

      {/* Error */}
      {cj?.error && (
        <div className="text-xs text-red-500 truncate max-w-[180px]" title={cj.error}>
          {cj.error}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-1 shrink-0">
        {entry.status === 'PAUSED' && (
          <button
            onClick={onResume}
            className="text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 hover:bg-green-200 px-2 py-1 rounded"
          >
            Resume
          </button>
        )}
        {(entry.status === 'READY' || entry.status === 'WAITING') && (
          <button
            onClick={onPause}
            className="text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 hover:bg-yellow-200 px-2 py-1 rounded"
          >
            Pause
          </button>
        )}
        {entry.status === 'FAILED' && cj && (
          <button
            onClick={onRetry}
            className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 px-2 py-1 rounded"
          >
            Retry
          </button>
        )}
        {!['COMPLETED', 'FAILED', 'CANCELLED', 'RUNNING'].includes(entry.status) && (
          <button
            onClick={onCancel}
            className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QueueManagerPage() {
  const navigate = useNavigate()
  const [queueState, setQueueState] = useState<QueueState | null>(null)
  const [loading, setLoading] = useState(true)
  const wsRef = useRef<WebSocket | null>(null)

  async function fetchQueue() {
    try {
      const q = await campaignApi.queue()
      setQueueState(q)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchQueue()

    const ws = new WebSocket(`ws://${location.host}/ws/campaign/queue`)
    wsRef.current = ws

    ws.onmessage = evt => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.event === 'queue_update') {
          setQueueState({ queue: msg.queue ?? [], counts: msg.counts ?? {}, paused: msg.paused ?? false })
        }
      } catch {
        // malformed — re-fetch
        fetchQueue()
      }
    }

    ws.onerror = () => fetchQueue()

    return () => ws.close()
  }, [])

  async function handlePauseQueue() {
    await campaignApi.pauseQueue()
    fetchQueue()
  }

  async function handleResumeQueue() {
    await campaignApi.resumeQueue()
    fetchQueue()
  }

  async function handlePauseJob(jobId: number) {
    await campaignApi.pauseJob(jobId)
    fetchQueue()
  }

  async function handleResumeJob(jobId: number) {
    await campaignApi.resumeJob(jobId)
    fetchQueue()
  }

  async function handleCancelEntry(entryId: number) {
    await campaignApi.removeFromQueue(entryId)
    fetchQueue()
  }

  async function handleRetryJob(jobId: number) {
    await campaignApi.retryJob(jobId)
    fetchQueue()
  }

  const counts = queueState?.counts ?? {}
  const queue = queueState?.queue ?? []
  const active = queue.filter(e => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(e.status))

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/campaigns')}
            className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            ← Campaigns
          </button>
          <h1 className="text-xl font-semibold">Queue Monitor</h1>
          {queueState?.paused && (
            <span className="text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 px-2 py-0.5 rounded-full">
              PAUSED
            </span>
          )}
        </div>

        <div className="flex gap-2">
          {queueState?.paused ? (
            <button
              onClick={handleResumeQueue}
              className="text-sm bg-green-600 hover:bg-green-700 text-white px-4 py-1.5 rounded"
            >
              Resume Queue
            </button>
          ) : (
            <button
              onClick={handlePauseQueue}
              className="text-sm bg-yellow-500 hover:bg-yellow-600 text-white px-4 py-1.5 rounded"
            >
              Pause Queue
            </button>
          )}
          <button
            onClick={fetchQueue}
            className="text-sm bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 px-3 py-1.5 rounded"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Count badges */}
      <div className="flex gap-3 flex-wrap mb-6">
        <CountBadge label="Ready" count={counts['READY'] ?? 0} color="text-blue-500" />
        <CountBadge label="Running" count={counts['RUNNING'] ?? 0} color="text-green-500" />
        <CountBadge label="Waiting" count={counts['WAITING'] ?? 0} color="text-gray-500" />
        <CountBadge label="Paused" count={counts['PAUSED'] ?? 0} color="text-yellow-500" />
        <CountBadge label="Retry" count={counts['RETRY'] ?? 0} color="text-orange-500" />
        <CountBadge label="Completed" count={counts['COMPLETED'] ?? 0} color="text-indigo-500" />
        <CountBadge label="Failed" count={counts['FAILED'] ?? 0} color="text-red-500" />
      </div>

      {/* Queue list */}
      {loading ? (
        <p className="text-gray-500 text-sm">Loading…</p>
      ) : active.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-4xl mb-3">⏳</p>
          <p className="text-lg font-medium">Queue is empty</p>
          <p className="text-sm mt-1">Start a campaign to enqueue jobs</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {active.map(e => (
            <QueueRow
              key={e.id}
              entry={e}
              onPause={() => e.campaign_job && handlePauseJob(e.campaign_job.id)}
              onResume={() => e.campaign_job && handleResumeJob(e.campaign_job.id)}
              onCancel={() => handleCancelEntry(e.id)}
              onRetry={() => e.campaign_job && handleRetryJob(e.campaign_job.id)}
            />
          ))}
        </div>
      )}

      {/* Completed/failed footer */}
      {queue.some(e => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(e.status)) && (
        <details className="mt-6">
          <summary className="text-sm text-gray-500 cursor-pointer select-none">
            Show completed / failed entries
          </summary>
          <div className="flex flex-col gap-2 mt-2">
            {queue
              .filter(e => ['COMPLETED', 'FAILED', 'CANCELLED'].includes(e.status))
              .map(e => (
                <QueueRow
                  key={e.id}
                  entry={e}
                  onPause={() => {}}
                  onResume={() => {}}
                  onCancel={() => {}}
                  onRetry={() => e.campaign_job && handleRetryJob(e.campaign_job.id)}
                />
              ))}
          </div>
        </details>
      )}
    </div>
  )
}
