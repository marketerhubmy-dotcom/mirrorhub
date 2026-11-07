import { useCallback, useEffect, useRef, useState } from 'react'
import type { ControlCommand } from '../types'

/**
 * Control channel for ONE device. Every message carries `device_id`; the server
 * rejects a message whose id differs from the socket's device (no cross-device input).
 * The socket is opened lazily on the first command.
 */
export function useDeviceControl(deviceId: string) {
  const wsRef = useRef<WebSocket | null>(null)
  const queue = useRef<string[]>([])
  const [lastError, setLastError] = useState('')

  const ensure = useCallback((): WebSocket => {
    const cur = wsRef.current
    if (cur && (cur.readyState === WebSocket.OPEN || cur.readyState === WebSocket.CONNECTING)) return cur
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/control/${encodeURIComponent(deviceId)}`)
    ws.onopen = () => {
      for (const m of queue.current.splice(0)) ws.send(m)
    }
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string)
        if (msg.error) setLastError(msg.detail ? `${msg.error}: ${msg.detail}` : msg.error)
      } catch { /* ignore */ }
    }
    ws.onclose = () => { if (wsRef.current === ws) wsRef.current = null }
    wsRef.current = ws
    return ws
  }, [deviceId])

  const send = useCallback((cmd: ControlCommand) => {
    const payload = JSON.stringify({ ...cmd, device_id: deviceId })
    const ws = ensure()
    if (ws.readyState === WebSocket.OPEN) ws.send(payload)
    else if (queue.current.length < 50) queue.current.push(payload)
  }, [deviceId, ensure])

  useEffect(() => () => {
    wsRef.current?.close()
    wsRef.current = null
    queue.current = []
  }, [deviceId])

  return { send, lastError, clearError: () => setLastError('') }
}
