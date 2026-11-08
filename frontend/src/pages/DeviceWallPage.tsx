import { useEffect, useMemo, useState } from 'react'
import { usePreferences } from '../hooks/usePreferences'
import { Link } from 'react-router-dom'
import DeviceTile from '../components/DeviceTile'
import { useDevices } from '../hooks/useDevices'

type Layout = 'auto' | 1 | 2 | 4 | 9

function columnsFor(layout: Layout, count: number): number {
  if (layout === 1) return 1
  if (layout === 2) return 2
  if (layout === 4) return 2
  if (layout === 9) return 3
  if (count <= 1) return 1
  if (count <= 4) return 2
  if (count <= 9) return 3
  return 4
}

const LAYOUTS: Layout[] = ['auto', 1, 2, 4, 9]

export default function DeviceWallPage() {
  const { devices, loading, error } = useDevices(3000)
  const [layout, setLayout] = useState<Layout>('auto')
  const [focusId, setFocusId] = useState<string | null>(null)
  const [pausedAll, setPausedAll] = useState(false)
  const [pausedIds, setPausedIds] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [showOffline, setShowOffline] = useState(false)
  const { prefs, update: updatePrefs } = usePreferences()
  const [quality, setQuality] = useState<'auto' | 'thumb' | 'normal' | 'focus'>('auto')
  useEffect(() => {          // apply saved preferences once they arrive
    if (!prefs) return
    setLayout(prefs.wall_layout)
    setShowOffline(prefs.wall_show_offline)
    setQuality(prefs.wall_quality)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs === null])

  const wallDevices = useMemo(
    () => devices
      .filter((d) => d.adb_address && (showOffline || d.is_online))
      .filter((d) => d.device_name.toLowerCase().includes(query.toLowerCase())),
    [devices, query, showOffline],
  )

  const focused = focusId ? wallDevices.find((d) => d.device_id === focusId) ?? null : null
  const others = focused ? wallDevices.filter((d) => d.device_id !== focused.device_id) : wallDevices
  const cols = columnsFor(layout, wallDevices.length)
  // Many tiles => low-FPS thumbnails; few tiles => smoother "normal" profile.
  const wallProfile = quality !== 'auto' ? quality : wallDevices.length > 4 ? 'thumb' : 'normal'

  const togglePause = (id: string) =>
    setPausedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })

  const isPaused = (id: string) => pausedAll || pausedIds.has(id)

  return (
    <div className="h-full flex flex-col bg-ink-900 text-white">
      <header className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-gray-800">
        <h1 className="font-semibold">Device Wall</h1>
        <span className="text-xs text-gray-400">{wallDevices.length} peranti</span>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <input
            value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari peranti…"
            className="bg-gray-800 rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-indigo-500 w-40"
          />
          <div className="flex rounded-lg overflow-hidden border border-gray-700" role="group" aria-label="Susun atur">
            {LAYOUTS.map((l) => (
              <button
                key={String(l)} onClick={() => { setLayout(l); updatePrefs({ wall_layout: l }) }} aria-pressed={layout === l}
                className={`px-2.5 py-1.5 text-xs ${layout === l ? 'bg-indigo-600' : 'bg-gray-800 hover:bg-gray-700'}`}
              >
                {l === 'auto' ? 'Auto' : l}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
            <input type="checkbox" checked={showOffline} onChange={(e) => { setShowOffline(e.target.checked); updatePrefs({ wall_show_offline: e.target.checked }) }} /> Termasuk offline
          </label>
          <button
            onClick={() => setPausedAll((p) => !p)}
            className="px-3 py-1.5 rounded-lg text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700"
          >
            {pausedAll ? '▶ Sambung semua' : '⏸ Jeda semua'}
          </button>
        </div>
      </header>

      {error && (
        <div className="px-5 py-2 text-sm bg-red-900/40 text-red-200 border-b border-red-900">
          Tidak dapat mengambil senarai peranti: {error}
        </div>
      )}

      <main className="flex-1 min-h-0 p-4">
        {loading ? (
          <p className="text-gray-400">Memuatkan peranti…</p>
        ) : wallDevices.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 text-center text-gray-400">
            <p>{devices.length === 0 ? 'Tiada peranti didaftarkan.' : 'Tiada peranti sepadan dengan carian.'}</p>
            <Link to="/pairing" className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500">
              Sambung peranti di Pairing Center
            </Link>
          </div>
        ) : focused ? (
          <div className="h-full grid gap-3" style={{ gridTemplateColumns: 'minmax(0,1fr) 220px' }}>
            <DeviceTile
              key={`${focused.device_id}-focus`} device={focused} profile="focus" focused
              paused={isPaused(focused.device_id)} onFocus={() => setFocusId(null)}
              onTogglePause={() => togglePause(focused.device_id)}
            />
            <div className="flex flex-col gap-3 overflow-y-auto min-h-0">
              {others.map((d) => (
                <div key={d.device_id} className="h-72 shrink-0">
                  <DeviceTile
                    device={d} profile="thumb" paused={isPaused(d.device_id)}
                    onFocus={() => setFocusId(d.device_id)} onTogglePause={() => togglePause(d.device_id)}
                  />
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div
            className="h-full grid gap-3 overflow-auto"
            style={{ gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gridAutoRows: 'minmax(260px, 1fr)' }}
          >
            {others.map((d) => (
              <DeviceTile
                key={`${d.device_id}-${wallProfile}`} device={d} profile={wallProfile}
                paused={isPaused(d.device_id)} onFocus={() => setFocusId(d.device_id)}
                onTogglePause={() => togglePause(d.device_id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
