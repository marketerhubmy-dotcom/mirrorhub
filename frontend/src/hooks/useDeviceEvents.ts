import { useEffect, useRef } from 'react'

export interface DeviceEvent {
  type: 'snapshot' | 'device' | 'changed' | 'adb'
  action?: string
  serial?: string
  state?: string
  message?: string
  ok?: boolean
  [k: string]: unknown
}

// One shared socket for the whole app (ref-counted); reconnects with back-off.
const listeners = new Set<(e: DeviceEvent) => void>()
let ws: WebSocket | null = null
let attempt = 0
let timer: ReturnType<typeof setTimeout> | undefined
let wanted = false

function open() {
  if (!wanted || ws) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const sock = new WebSocket(`${proto}://${location.host}/ws/devices`)
  ws = sock
  sock.onopen = () => { attempt = 0 }
  sock.onmessage = (m) => {
    try {
      const ev = JSON.parse(m.data as string) as DeviceEvent
      listeners.forEach((l) => l(ev))
    } catch { /* ignore malformed */ }
  }
  sock.onclose = () => {
    ws = null
    if (!wanted) return
    attempt += 1
    timer = setTimeout(open, Math.min(1000 * 2 ** attempt, 15000))
  }
}

/** Subscribe to /ws/devices (hot-plug, authorization, reconnect, adb outage). Pages also poll as a fallback. */
export function useDeviceEvents(onEvent: (e: DeviceEvent) => void) {
  const cb = useRef(onEvent)
  cb.current = onEvent

  useEffect(() => {
    const l = (e: DeviceEvent) => cb.current(e)
    listeners.add(l)
    wanted = true
    open()
    return () => {
      listeners.delete(l)
      if (listeners.size === 0) {
        wanted = false
        clearTimeout(timer)
        ws?.close()
        ws = null
      }
    }
  }, [])
}
