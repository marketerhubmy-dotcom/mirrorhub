import { useCallback, useEffect, useRef } from 'react'
import { useDeviceStream, type StreamProfile, type StreamState } from '../hooks/useDeviceStream'
import { useDeviceControl } from '../hooks/useDeviceControl'
import { containedContentRect, toRelative } from '../utils/geometry'
import type { Device } from '../types'

interface Props {
  device: Device
  profile: StreamProfile
  paused: boolean
  focused?: boolean
  onFocus?: () => void
  onTogglePause: () => void
}

const STATE_LABEL: Record<StreamState, string> = {
  paused: 'Dijeda',
  connecting: 'Menyambung…',
  starting: 'Memulakan strim…',
  streaming: 'Live',
  reconnecting: 'Menyambung semula…',
  failed: 'Gagal',
  stopped: 'Dihentikan',
  unsupported: 'Tidak disokong',
}

const STATE_DOT: Record<StreamState, string> = {
  paused: 'bg-yellow-500', connecting: 'bg-blue-500', starting: 'bg-blue-500', streaming: 'bg-green-500',
  reconnecting: 'bg-orange-500', failed: 'bg-red-500', stopped: 'bg-gray-500', unsupported: 'bg-red-500',
}

const NAV = [
  { label: '◀', title: 'Back', action: 'back' },
  { label: '●', title: 'Home', action: 'home' },
  { label: '■', title: 'Recents', action: 'recents' },
] as const

export default function DeviceTile({ device, profile, paused, focused = false, onFocus, onTogglePause }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const press = useRef<{ x: number; y: number; t: number } | null>(null)
  const textBuf = useRef('')
  const textTimer = useRef<number | undefined>(undefined)

  const { state, error, stats } = useDeviceStream(device.device_id, profile, canvasRef, paused)
  const { send, lastError, clearError } = useDeviceControl(device.device_id)

  const rel = useCallback((e: { clientX: number; clientY: number }) => {
    const box = boxRef.current
    const canvas = canvasRef.current
    if (!box || !canvas) return null
    const r = box.getBoundingClientRect()
    return toRelative(containedContentRect(r, canvas.width, canvas.height), e.clientX, e.clientY)
  }, [])

  const onPointerDown = (e: React.PointerEvent) => {
    if (state !== 'streaming') return
    boxRef.current?.focus()
    const p = rel(e)
    if (!p) return
    e.currentTarget.setPointerCapture(e.pointerId)
    press.current = { ...p, t: Date.now() }
  }

  const onPointerUp = (e: React.PointerEvent) => {
    const start = press.current
    press.current = null
    if (!start) return
    const end = rel(e) ?? start
    const moved = Math.abs(end.x - start.x) > 0.02 || Math.abs(end.y - start.y) > 0.02
    if (moved) send({ type: 'swipe', x1: start.x, y1: start.y, x2: end.x, y2: end.y })
    else if (Date.now() - start.t >= 500) send({ type: 'long_press', x: start.x, y: start.y })
    else send({ type: 'tap', x: start.x, y: start.y })
  }

  const flushText = useCallback(() => {
    if (textBuf.current) { send({ type: 'text', value: textBuf.current }); textBuf.current = '' }
  }, [send])

  useEffect(() => () => window.clearTimeout(textTimer.current), [])

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (state !== 'streaming' || e.ctrlKey || e.metaKey || e.altKey) return
    const special: Record<string, string> = { Enter: 'KEYCODE_ENTER', Backspace: 'KEYCODE_DEL', Tab: 'KEYCODE_TAB' }
    if (special[e.key]) { flushText(); send({ type: 'key', code: special[e.key] }); e.preventDefault() }
    else if (e.key === 'Escape') { flushText(); send({ type: 'nav', action: 'back' }); e.preventDefault() }
    else if (e.key.length === 1) {
      textBuf.current += e.key
      window.clearTimeout(textTimer.current)
      textTimer.current = window.setTimeout(flushText, 80)
      e.preventDefault()
    }
  }

  const border = focused ? 'border-indigo-500' : 'border-gray-700'
  const showOverlay = state !== 'streaming'

  return (
    <div className={`flex flex-col bg-gray-800 border ${border} rounded-xl overflow-hidden min-h-0`}>
      <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-2 h-2 rounded-full shrink-0 ${STATE_DOT[state]}`} />
          <span className="truncate text-white font-medium" title={device.adb_address ?? ''}>{device.device_name}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0 text-gray-400">
          {state === 'streaming' && <span className="tabular-nums">{stats.fps} fps</span>}
          <button onClick={onTogglePause} title={paused ? 'Sambung' : 'Jeda'}
            className="px-1.5 py-0.5 rounded hover:bg-gray-700">{paused ? '▶' : '⏸'}</button>
          {onFocus && (
            <button onClick={onFocus} title={focused ? 'Keluar Fokus' : 'Mod Fokus'}
              className="px-1.5 py-0.5 rounded hover:bg-gray-700">{focused ? '⤡' : '⤢'}</button>
          )}
          <button onClick={() => boxRef.current?.requestFullscreen?.()} title="Skrin penuh"
            className="px-1.5 py-0.5 rounded hover:bg-gray-700">⛶</button>
        </div>
      </div>

      <div
        ref={boxRef}
        tabIndex={0}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onPointerCancel={() => { press.current = null }}
        className="relative flex-1 min-h-0 bg-black outline-none focus:ring-1 focus:ring-indigo-500 select-none touch-none"
        style={{ minHeight: 120 }}
      >
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full object-contain" />
        {showOverlay && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/60 text-center px-3">
            <span className="text-sm text-gray-200">{STATE_LABEL[state]}</span>
            {error && (
              <span className="text-xs text-red-300 break-words max-h-20 overflow-auto" title={error}>
                {/* raw scrcpy server log lines follow "timed out"; keep the human sentence, full text stays in the tooltip */}
                {(error.split('timed out waiting')[0].trim() || 'Strim tidak bermula. Semak skrin telefon dan kebenaran.').slice(0, 200)}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 px-2 py-1.5">
        {NAV.map((b) => (
          <button key={b.action} title={b.title} disabled={state !== 'streaming'}
            onClick={() => send({ type: 'nav', action: b.action })}
            className="flex-1 py-1 rounded bg-gray-700 text-xs text-white hover:bg-gray-600 disabled:opacity-40">
            {b.label}
          </button>
        ))}
      </div>
      {lastError && (
        <button onClick={clearError} className="px-2 pb-1.5 text-left text-[11px] text-red-300 truncate" title={lastError}>
          ⚠ {lastError}
        </button>
      )}
    </div>
  )
}
