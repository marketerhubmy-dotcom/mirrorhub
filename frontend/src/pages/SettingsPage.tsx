import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { systemApi, AppSettings } from '../services/systemApi'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
      <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
        {title}
      </h2>
      <div className="divide-y divide-gray-100 dark:divide-gray-700">{children}</div>
    </div>
  )
}

function SettingRow({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="flex items-start justify-between py-2.5">
      <div>
        <div className="text-sm text-gray-800 dark:text-gray-200">{label}</div>
        {hint && <div className="text-xs text-gray-400 mt-0.5">{hint}</div>}
      </div>
      <span className="font-mono text-sm text-indigo-600 dark:text-indigo-400 ml-4 text-right">{value}</span>
    </div>
  )
}

export default function SettingsPage() {
  const navigate = useNavigate()
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    systemApi.settings()
      .then(setSettings)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/')}
              className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            >
              ← Dashboard
            </button>
            <h1 className="text-xl font-semibold">Settings</h1>
          </div>
          <div className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 rounded px-2 py-1">
            Read-only · Edit in <code>backend/.env</code>
          </div>
        </div>

        {loading ? (
          <p className="text-gray-500 text-sm">Loading…</p>
        ) : error ? (
          <p className="text-red-500 text-sm">{error}</p>
        ) : settings ? (
          <div className="flex flex-col gap-4">
            <Section title="Application">
              <SettingRow label="App name" value={settings.app_name} />
              <SettingRow label="Host" value={settings.host} />
              <SettingRow label="Port" value={settings.port} />
              <SettingRow label="Log level" value={settings.log_level} />
            </Section>

            <Section title="Security">
              <SettingRow
                label="CORS origins"
                value={settings.cors_origins}
                hint='Set CORS_ORIGINS="https://yourdomain.com" in .env to restrict access'
              />
            </Section>

            <Section title="Devices">
              <SettingRow
                label="Device timeout"
                value={`${settings.device_timeout}s`}
                hint="Seconds before a device is considered unreachable"
              />
            </Section>

            <Section title="AI / OpenAI">
              <SettingRow
                label="API key"
                value={settings.openai_api_key || '⚠ Not configured'}
                hint="Set OPENAI_API_KEY in backend/.env"
              />
              <SettingRow label="Model" value={settings.openai_model} />
              <SettingRow label="Max tokens" value={settings.openai_max_tokens} />
            </Section>

            <Section title="Vision Engine">
              <SettingRow
                label="Cache TTL"
                value={`${settings.vision_cache_ttl}s`}
                hint="How long a screen analysis result is cached"
              />
              <SettingRow label="Poll interval" value={`${settings.vision_poll_interval}s`} />
              <SettingRow label="Default timeout" value={`${settings.vision_default_timeout}s`} />
            </Section>

            <Section title="Campaign Scheduler">
              <SettingRow label="Poll interval" value={`${settings.campaign_poll_interval}s`} />
              <SettingRow
                label="Retry delay"
                value={`${settings.campaign_retry_delay}s`}
                hint="Wait time before retrying a failed job"
              />
            </Section>

            <div className="text-xs text-gray-400 text-center mt-2">
              Settings are read from <code>backend/.env</code> at startup. Restart the server to apply changes.
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
