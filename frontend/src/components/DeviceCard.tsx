import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import type { Device } from '../types'
import { api } from '../services/api'

interface Props {
  device: Device
}

export default function DeviceCard({ device }: Props) {
  const navigate = useNavigate()
  const [mirroring, setMirroring] = useState(false)
  const [loading, setLoading] = useState(false)

  const toggleMirror = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setLoading(true)
    try {
      if (mirroring) {
        await api.stopMirror(device.device_id)
        setMirroring(false)
      } else {
        await api.startMirror(device.device_id)
        setMirroring(true)
      }
    } catch (err) {
      alert((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex flex-col gap-3 shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="font-semibold text-gray-900 truncate">{device.device_name}</span>
        <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ml-2 ${
          device.is_online ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
        }`}>
          {device.is_online ? 'Online' : 'Offline'}
        </span>
      </div>

      {/* Info */}
      <div className="text-sm text-gray-500 flex items-center gap-3">
        <span>🔋 {device.battery}%</span>
        {device.wifi && <span>📶 WiFi</span>}
        {device.adb_address && (
          <span className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
            {device.adb_address}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-1">
        {device.adb_address && (
          <button
            onClick={toggleMirror}
            disabled={loading || !device.is_online}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all
              disabled:opacity-40 disabled:cursor-not-allowed
              ${mirroring
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-emerald-600 text-white hover:bg-emerald-700'
              }`}
          >
            {loading ? '...' : mirroring ? '⏹ Stop' : '▶ Mirror'}
          </button>
        )}
        <button
          onClick={() => navigate(`/device/${device.device_id}`)}
          disabled={!device.is_online}
          className="flex-1 py-2 rounded-lg text-sm font-medium transition-colors
            bg-indigo-600 text-white hover:bg-indigo-700
            disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
        >
          Controls
        </button>
      </div>
    </div>
  )
}
