import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { systemApi, BuildInfo, HealthCheck } from '../services/systemApi'

function Badge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${
        ok
          ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
          : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
      }`}
    >
      {ok ? '✓ OK' : '✗ Issue'}
    </span>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
        {title}
      </h2>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-1.5 text-sm border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-gray-500 dark:text-gray-400 shrink-0 min-w-[160px]">{label}</span>
      <span className="text-gray-900 dark:text-gray-100 text-right font-mono text-xs break-all">{value}</span>
    </div>
  )
}

export default function AboutPage() {
  const navigate = useNavigate()
  const [info, setInfo] = useState<BuildInfo | null>(null)
  const [health, setHealth] = useState<HealthCheck | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([systemApi.about(), systemApi.health()])
      .then(([a, h]) => { setInfo(a); setHealth(h) })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate('/')}
            className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            ← Dashboard
          </button>
          <h1 className="text-xl font-semibold">About MirrorHub</h1>
        </div>

        {loading ? (
          <p className="text-gray-500 text-sm">Loading…</p>
        ) : info ? (
          <div className="flex flex-col gap-4">
            {/* Version card */}
            <div className="bg-indigo-600 rounded-xl p-6 text-white">
              <div className="text-3xl font-bold mb-1">MirrorHub {info.version}</div>
              <div className="text-indigo-200 text-sm">{info.release_name} · Built {info.build_date}</div>
            </div>

            {/* System info */}
            <Section title="System">
              <Row label="Python" value={info.python_version} />
              <Row label="Platform" value={info.platform} />
              <Row label="Architecture" value={info.architecture} />
              <Row label="Server time" value={new Date(info.server_time).toLocaleString()} />
            </Section>

            {/* Database */}
            <Section title="Database">
              <Row label="Path" value={info.database.path} />
              <Row label="Status" value={info.database.exists ? 'Active' : 'Not found'} />
              <Row
                label="Size"
                value={info.database.exists ? `${(info.database.size_bytes / 1024).toFixed(1)} KB` : '—'}
              />
            </Section>

            {/* Health */}
            {health && (
              <Section title="Health Checks">
                {Object.entries(health.checks).map(([name, check]) => (
                  <div key={name} className="flex items-center justify-between py-1.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
                    <span className="text-sm capitalize text-gray-700 dark:text-gray-300">{name}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 dark:text-gray-400">{check.detail}</span>
                      <Badge ok={check.ok} />
                    </div>
                  </div>
                ))}
              </Section>
            )}

            {/* Plugins */}
            <Section title="Plugins">
              {Object.entries(info.plugins).map(([name, ver]) => (
                <Row key={name} label={name} value={`v${ver}`} />
              ))}
            </Section>

            {/* Modules */}
            <Section title="Modules">
              {Object.entries(info.modules).map(([name, ver]) => (
                <Row key={name} label={name.replace(/_/g, ' ')} value={`v${ver}`} />
              ))}
            </Section>
          </div>
        ) : (
          <p className="text-red-500 text-sm">Failed to load build information.</p>
        )}
      </div>
    </div>
  )
}
