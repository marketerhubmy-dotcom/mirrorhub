import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { createControlSocket, sendControl } from '../services/websocket'
import NavControls from '../components/NavControls'
import type { ControlCommand, Device } from '../types'

export default function DevicePage() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const [device, setDevice] = useState<Device | null>(null)
  const [textInput, setTextInput] = useState('')
  const [mirroring, setMirroring] = useState(false)
  const [mirrorLoading, setMirrorLoading] = useState(false)
  const [ws, setWs] = useState<WebSocket | null>(null)

  useEffect(() => {
    if (!deviceId) return
    api.getDevice(deviceId).then(setDevice).catch(() => {})
    api.getMirrorStatus(deviceId).then((s) => setMirroring(s.mirroring)).catch(() => {})

    const ctrl = createControlSocket(deviceId)
    setWs(ctrl)
    return () => ctrl.close()
  }, [deviceId])

  const send = useCallback((cmd: ControlCommand) => {
    if (ws) sendControl(ws, cmd)
  }, [ws])

  if (!deviceId) return null

  const toggleMirror = async () => {
    setMirrorLoading(true)
    try {
      if (mirroring) {
        await api.stopMirror(deviceId)
        setMirroring(false)
      } else {
        await api.startMirror(deviceId)
        setMirroring(true)
      }
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setMirrorLoading(false)
    }
  }

  const sendText = () => {
    if (!textInput.trim()) return
    send({ type: 'text', value: textInput.trim() })
    setTextInput('')
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="text-gray-400 hover:text-white text-sm">
            ← Back
          </button>
          <span className="font-semibold">{device?.device_name ?? deviceId}</span>
          {device?.is_online && (
            <span className="text-xs px-2 py-0.5 bg-green-900 text-green-400 rounded-full">Online</span>
          )}
        </div>

        {device?.adb_address && (
          <button
            onClick={toggleMirror}
            disabled={mirrorLoading}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              disabled:opacity-50 disabled:cursor-not-allowed
              ${mirroring ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'}`}
          >
            {mirrorLoading ? '...' : mirroring ? '⏹ Stop Mirror' : '▶ Start Mirror'}
          </button>
        )}
      </header>

      <main className="max-w-sm mx-auto px-4 py-6 flex flex-col gap-5">

        {/* Mirror status */}
        {mirroring && (
          <div className="bg-emerald-900/30 border border-emerald-700 rounded-xl p-4 text-center">
            <p className="text-emerald-400 font-medium text-sm">📱 Mirror sedang berjalan</p>
            <p className="text-emerald-600 text-xs mt-1">Tengok window scrcpy yang terbuka</p>
          </div>
        )}

        {/* Navigation */}
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-3">Navigation</p>
          <NavControls onCommand={send} />
        </div>

        {/* Keyboard */}
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-3">Keyboard</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); send({ type: 'key', code: 'KEYCODE_ENTER' }) }
                else if (e.key === 'Backspace' && !textInput) send({ type: 'key', code: 'KEYCODE_DEL' })
              }}
              placeholder="Type to send..."
              className="flex-1 bg-gray-800 text-white rounded-lg px-4 py-2.5 text-sm
                placeholder:text-gray-600 outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={sendText}
              className="px-4 py-2.5 bg-indigo-600 rounded-lg text-sm font-medium hover:bg-indigo-700"
            >
              Send
            </button>
          </div>
        </div>

        {/* Device info */}
        {device && (
          <div className="bg-gray-800 rounded-xl p-4 text-sm text-gray-400 space-y-1">
            <div className="flex justify-between">
              <span>Battery</span>
              <span className="text-white">{device.battery}%</span>
            </div>
            <div className="flex justify-between">
              <span>ADB Address</span>
              <span className="text-white font-mono text-xs">{device.adb_address ?? '—'}</span>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
