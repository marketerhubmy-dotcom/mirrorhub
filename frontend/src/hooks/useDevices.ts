import { useState, useEffect, useCallback } from 'react'
import type { Device } from '../types'
import { api } from '../services/api'

export function useDevices(pollMs = 5000) {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  return { devices, loading, error, refresh: fetchDevices }
}
