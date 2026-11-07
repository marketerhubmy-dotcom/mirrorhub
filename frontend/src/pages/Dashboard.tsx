import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevices } from '../hooks/useDevices'
import DeviceCard from '../components/DeviceCard'
import ConnectModal from '../components/ConnectModal'
import type { Device } from '../types'

export default function Dashboard() {
  const navigate = useNavigate()
  const { devices, loading, error, refresh } = useDevices()
  const [showConnect, setShowConnect] = useState(false)

  const handleConnected = (_: Device) => refresh()

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">MirrorHub</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{devices.length} device(s)</span>
          <button
            onClick={() => navigate('/quicklaunch')}
            className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-bold
              rounded-lg hover:from-blue-700 hover:to-indigo-700 transition-colors shadow-md"
          >
            ▶ Quick Launch
          </button>
          <button
            onClick={() => navigate('/queue')}
            className="px-4 py-2 bg-cyan-600 text-white text-sm font-medium
              rounded-lg hover:bg-cyan-700 transition-colors"
          >
            ⏳ Queue
          </button>
          <button
            onClick={() => navigate('/campaigns')}
            className="px-4 py-2 bg-purple-600 text-white text-sm font-medium
              rounded-lg hover:bg-purple-700 transition-colors"
          >
            📋 Campaigns
          </button>
          <button
            onClick={() => navigate('/tiktok')}
            className="px-4 py-2 bg-pink-600 text-white text-sm font-medium
              rounded-lg hover:bg-pink-700 transition-colors"
          >
            TikTok
          </button>
          <button
            onClick={() => navigate('/workflows')}
            className="px-4 py-2 bg-indigo-500 text-white text-sm font-medium
              rounded-lg hover:bg-indigo-600 transition-colors"
          >
            🎬 Workflows
          </button>
          <button
            onClick={() => navigate('/vision')}
            className="px-4 py-2 bg-teal-600 text-white text-sm font-medium
              rounded-lg hover:bg-teal-700 transition-colors"
          >
            👁️ Vision
          </button>
          <button
            onClick={() => navigate('/execution')}
            className="px-4 py-2 bg-orange-600 text-white text-sm font-medium
              rounded-lg hover:bg-orange-700 transition-colors"
          >
            ⚙️ Execution
          </button>
          <button
            onClick={() => navigate('/pipeline')}
            className="px-4 py-2 bg-gradient-to-r from-violet-600 to-pink-600 text-white text-sm font-medium
              rounded-lg hover:from-violet-500 hover:to-pink-500 transition-colors"
          >
            🎬 AI Video Studio
          </button>
          <button
            onClick={() => navigate('/content')}
            className="px-4 py-2 bg-violet-600 text-white text-sm font-medium
              rounded-lg hover:bg-violet-700 transition-colors"
          >
            ✨ Content Studio
          </button>
          <button
            onClick={() => navigate('/automation')}
            className="px-4 py-2 bg-emerald-600 text-white text-sm font-medium
              rounded-lg hover:bg-emerald-700 transition-colors"
          >
            ⚡ Automation
          </button>
          <button
            onClick={() => setShowConnect(true)}
            className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium
              rounded-lg hover:bg-indigo-700 transition-colors"
          >
            + Connect Phone
          </button>
          <button
            onClick={() => navigate('/ai')}
            className="px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-medium
              rounded-lg hover:from-violet-500 hover:to-indigo-500 transition-colors"
          >
            🤖 AI Agent
          </button>
          <button
            onClick={() => navigate('/device-wall')}
            className="px-4 py-2 bg-slate-600 text-white text-sm font-medium
              rounded-lg hover:bg-slate-500 transition-colors"
          >
            🖥️ Device Wall
          </button>
          <button
            onClick={() => navigate('/orchestrator')}
            className="px-4 py-2 bg-sky-700 text-white text-sm font-medium
              rounded-lg hover:bg-sky-600 transition-colors"
          >
            🎛️ Orchestrator
          </button>
          <button
            onClick={() => navigate('/settings')}
            className="px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-sm
              rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            title="Settings"
          >
            ⚙
          </button>
          <button
            onClick={() => navigate('/about')}
            className="px-3 py-2 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-sm
              rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            title="About"
          >
            ℹ
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {loading && <p className="text-sm text-gray-400">Loading...</p>}
        {error && <p className="text-sm text-red-500">Error: {error}</p>}

        {!loading && devices.length === 0 && (
          <div className="max-w-md mx-auto py-10">
            <div className="text-center mb-8">
              <p className="text-5xl mb-3">📱</p>
              <p className="text-gray-700 font-semibold text-lg">Belum ada device</p>
              <p className="text-gray-400 text-sm mt-1">Ikut langkah di bawah untuk tambah phone pertama</p>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-5 space-y-4 shadow-sm">
              {[
                { n: 1, title: 'Enable Developer Options', desc: 'Settings → About Phone → ketuk Build Number 7 kali' },
                { n: 2, title: 'Enable Wireless Debugging', desc: 'Settings → Developer Options → Wireless Debugging → ON' },
                { n: 3, title: 'Pair device (WiFi baru)', desc: 'Tap "Pair device with pairing code" → jalankan connect_phone.bat' },
                { n: 4, title: 'Klik "+ Connect Phone"', desc: 'Masukkan IP:PORT dari skrin Wireless Debugging' },
              ].map(({ n, title, desc }) => (
                <div key={n} className="flex gap-3 items-start">
                  <span className="shrink-0 w-7 h-7 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center">
                    {n}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-gray-800">{title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-700">
              <strong>WiFi sama?</strong> Skip langkah 3 — terus klik "+ Connect Phone".
            </div>

            <button
              onClick={() => setShowConnect(true)}
              className="mt-5 w-full py-3 bg-indigo-600 text-white rounded-xl font-medium
                hover:bg-indigo-700 transition-colors"
            >
              + Connect Phone Sekarang
            </button>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {devices.map((device) => (
            <DeviceCard key={device.device_id} device={device} />
          ))}
        </div>
      </main>

      {showConnect && (
        <ConnectModal
          onClose={() => setShowConnect(false)}
          onConnected={handleConnected}
        />
      )}
    </div>
  )
}
