import { useCallback, useEffect, useState } from 'react'
import { prefsApi, type Preferences } from '../services/deviceApi'

/** Server-side persisted preferences (survive restarts). `ready` is false until the first load completes. */
export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences | null>(null)
  useEffect(() => { prefsApi.get().then(setPrefs).catch(() => { /* backend down: callers keep defaults */ }) }, [])
  const update = useCallback(async (patch: Partial<Preferences>) => {
    setPrefs((p) => (p ? { ...p, ...patch } : p))               // optimistic
    try { setPrefs(await prefsApi.put(patch)) } catch { prefsApi.get().then(setPrefs).catch(() => {}) }
  }, [])
  return { prefs, ready: prefs !== null, update }
}
