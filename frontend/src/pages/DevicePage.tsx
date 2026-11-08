import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { useDeviceControl } from '../hooks/useDeviceControl'
import DeviceTile from '../components/DeviceTile'
import type { Device } from '../types'

export default function DevicePage() {
  const { deviceId } = useParams<{ deviceId: string }>()
  if (!deviceId) return null
  return <DeviceView deviceId={deviceId} />
}

function DeviceView({ deviceId }: { deviceId: string }) {
  const navigate = useNavigate()
  const [device, setDevice] = useState<Device | null>(null)
  const [loadError, setLoadError] = useState('')
  const [paused, setPaused] = useState(false)
  const [textInput, setTextInput] = useState('')
  const [externalOpen, setExternalOpen] = useState(false)
  const [externalMsg, setExternalMsg] = useState('')
  const { send } = useDeviceControl(deviceId)

  useEffect(() => {
    api.getDevice(deviceId).then(setDevice).catch((e: Error) => setLoadError(e.message))
    api.getMirrorStatus(deviceId).then((s) => setExternalOpen(s.mirroring)).catch(() => {})
  }, [deviceId])

  const sendText = () => {
    if (!textInput) return
    send({ type: 'text', value: textInput })
    setTextInput('')
  }

  // Optional: classic scrcpy window (supports audio). Not the primary view.
  const toggleExternal = async () => {
    setExternalMsg('')
    try {
      if (externalOpen) { await api.stopMirror(deviceId); setExternalOpen(false) }
      else { await api.startMirror(deviceId); setExternalOpen(true) }
    } catch (e) {
      setExternalMsg((e as Error).message)
    }
  }

  return (
    <div className="min-h-full bg-ink-900 text-white">
      <header className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-gray-400 hover:text-white text-sm">← Kembali</button>
          <span className="font-semibold">{device?.device_name ?? deviceId}</span>
          {device?.is_online && (
            <span className="text-xs px-2 py-0.5 bg-green-900 text-green-400 rounded-full">Online</span>
          )}
        </div>
        <button onClick={() => navigate('/device-wall')} className="text-sm text-gray-400 hover:text-white">
          Device Wall →
        </button>
      </header>

      <main className="max-w-md mx-auto px-4 py-6 flex flex-col gap-5">
        {loadError && <p className="text-sm text-red-300">Gagal memuatkan peranti: {loadError}</p>}

        {device && !device.adb_address && (
          <p className="text-sm text-yellow-300">
            Peranti ini tiada alamat ADB, jadi paparan embedded tidak tersedia.
          </p>
        )}

        {device?.adb_address && (
          <div style={{ height: '70vh' }}>
            <DeviceTile device={device} profile="focus" focused paused={paused} onTogglePause={() => setPaused((p) => !p)} />
          </div>
        )}

        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-3">Papan kekunci</p>
          <div className="flex gap-2">
            <input
              type="text" value={textInput} onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); if (textInput) sendText(); else send({ type: 'key', code: 'KEYCODE_ENTER' }) }
                else if (e.key === 'Backspace' && !textInput) send({ type: 'key', code: 'KEYCODE_DEL' })
              }}
              placeholder="Taip untuk hantar…" maxLength={500}
              className="flex-1 bg-gray-800 text-white rounded-lg px-4 py-2.5 text-sm placeholder:text-gray-600
                outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button onClick={sendText} className="px-4 py-2.5 bg-indigo-600 rounded-lg text-sm font-medium hover:bg-indigo-700">
              Hantar
            </button>
          </div>
        </div>

        {device && (
          <div className="bg-gray-800 rounded-xl p-4 text-sm text-gray-400 space-y-1">
            <div className="flex justify-between"><span>Bateri</span><span className="text-white">{device.battery}%</span></div>
            <div className="flex justify-between">
              <span>Alamat ADB</span><span className="text-white font-mono text-xs">{device.adb_address ?? '—'}</span>
            </div>
          </div>
        )}

        {device?.adb_address && (
          <details className="text-sm text-gray-400">
            <summary className="cursor-pointer">Lanjutan: tetingkap scrcpy berasingan (audio)</summary>
            <div className="mt-3 flex items-center gap-3">
              <button onClick={toggleExternal}
                className={`px-3 py-1.5 rounded-lg text-xs ${externalOpen ? 'bg-red-600 hover:bg-red-700' : 'bg-gray-700 hover:bg-gray-600'}`}>
                {externalOpen ? 'Tutup tetingkap scrcpy' : 'Buka tetingkap scrcpy'}
              </button>
              {externalMsg && <span className="text-xs text-red-300">{externalMsg}</span>}
            </div>
          </details>
        )}
      </main>
    </div>
  )
}
