import { useState, useEffect, useCallback, useRef } from 'react'
import type { Device } from '../types'
import { api } from '../services/api'
import { useDeviceEvents } from './useDeviceEvents'

/** Device list: polled as a safety net, refreshed immediately on lifecycle events from /ws/devices. */
export function useDevices(pollMs = 5000) {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const fetchDevices = useCallback(async () => {
    try {
      setDevices(await api.getDevices())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchDevices()
    const id = setInterval(fetchDevices, pollMs)
    return () => clearInterval(id)
  }, [fetchDevices, pollMs])

  useDeviceEvents((e) => {
    if (e.type === 'changed' || e.type === 'device') {
      clearTimeout(debounce.current)
      debounce.current = setTimeout(fetchDevices, 250)
    }
  })

  useEffect(() => () => clearTimeout(debounce.current), [])

  return { devices, loading, error, refresh: fetchDevices }
}
