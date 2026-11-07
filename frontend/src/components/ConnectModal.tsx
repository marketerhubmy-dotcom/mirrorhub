import { useState } from 'react'
import { api } from '../services/api'
import type { Device } from '../types'

interface Props {
  onClose: () => void
  onConnected: (device: Device) => void
}

export default function ConnectModal({ onClose, onConnected }: Props) {
  const [adbAddress, setAdbAddress] = useState('')
  const [deviceName, setDeviceName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<'guide' | 'connect'>('guide')

  const handleConnect = async () => {
    if (!adbAddress.trim()) return
    setLoading(true)
    setError(null)
    try {
      const device = await api.connectAdb(adbAddress.trim(), deviceName.trim() || undefined)
      onConnected(device)
      onClose()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-xl overflow-hidden">

        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-gray-100">
          <h2 className="text-lg font-semibold text-gray-900">Tambah Device Baru</h2>
          <div className="flex gap-1 mt-3">
            {(['guide', 'connect'] as const).map((s, i) => (
              <button
                key={s}
                onClick={() => setStep(s)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  step === s
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                }`}
              >
                {i + 1}. {s === 'guide' ? 'Setup Phone' : 'Connect'}
              </button>
            ))}
          </div>
        </div>

        {/* Step 1 — Guide */}
        {step === 'guide' && (
          <div className="px-6 py-5">
            <p className="text-sm font-medium text-gray-700 mb-4">
              Buat langkah ni dalam phone baru:
            </p>

            <div className="space-y-3">
              <div className="flex gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold flex items-center justify-center">1</span>
                <div>
                  <p className="text-sm font-medium text-gray-800">Enable Developer Options</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Settings → About Phone → ketuk <strong>Build Number 7 kali</strong>
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold flex items-center justify-center">2</span>
                <div>
                  <p className="text-sm font-medium text-gray-800">Enable Wireless Debugging</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Settings → Developer Options → <strong>Wireless Debugging → ON</strong>
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold flex items-center justify-center">3</span>
                <div>
                  <p className="text-sm font-medium text-gray-800">Pair device (WiFi baru sahaja)</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Tap <strong>"Pair device with pairing code"</strong> → double-click{' '}
                    <code className="bg-gray-100 px-1 rounded">connect_phone.bat</code> di folder MirrorHub
                  </p>
                </div>
              </div>

              <div className="flex gap-3">
                <span className="shrink-0 w-6 h-6 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold flex items-center justify-center">4</span>
                <div>
                  <p className="text-sm font-medium text-gray-800">Catat IP address & Port</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Dalam skrin <strong>Wireless Debugging</strong>, ada tertulis{' '}
                    <code className="bg-gray-100 px-1 rounded">192.168.x.x:PORT</code> — salin tu
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-5 p-3 bg-amber-50 rounded-lg border border-amber-200">
              <p className="text-xs text-amber-700">
                <strong>WiFi sama?</strong> Skip langkah 3 — terus ke Connect.
              </p>
            </div>
          </div>
        )}

        {/* Step 2 — Connect */}
        {step === 'connect' && (
          <div className="px-6 py-5">
            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1.5 block">
                  IP:PORT <span className="text-gray-400 font-normal">(dari Wireless Debugging)</span>
                </label>
                <input
                  autoFocus
                  type="text"
                  value={adbAddress}
                  onChange={(e) => setAdbAddress(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
                  placeholder="192.168.x.x:PORT"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm
                    outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-600 mb-1.5 block">
                  Nama Device <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={deviceName}
                  onChange={(e) => setDeviceName(e.target.value)}
                  placeholder="Samsung A34, Pixel 6..."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm
                    outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {error && (
                <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-6 pb-6 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-lg border border-gray-200 text-sm
              text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Batal
          </button>

          {step === 'guide' ? (
            <button
              onClick={() => setStep('connect')}
              className="flex-1 py-2.5 rounded-lg bg-indigo-600 text-white text-sm
                font-medium hover:bg-indigo-700 transition-colors"
            >
              Seterusnya →
            </button>
          ) : (
            <button
              onClick={handleConnect}
              disabled={loading || !adbAddress.trim()}
              className="flex-1 py-2.5 rounded-lg bg-indigo-600 text-white text-sm
                font-medium hover:bg-indigo-700 transition-colors
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Connecting...' : 'Connect'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
