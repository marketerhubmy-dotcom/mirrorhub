import { createContext, useCallback, useContext, useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import type { DeviceState } from '../types'

// ── Button ────────────────────────────────────────────────────────────────────
type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
const VARIANT: Record<Variant, string> = {
  primary: 'bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-600/20',
  secondary: 'bg-ink-700 hover:bg-ink-600 text-gray-100 border border-ink-600',
  ghost: 'hover:bg-ink-700 text-gray-300',
  danger: 'bg-red-600/90 hover:bg-red-500 text-white',
}

export function Button({ variant = 'secondary', busy, size = 'md', className = '', children, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean; size?: 'sm' | 'md' }) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors
        focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:opacity-50 disabled:cursor-not-allowed
        ${size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-2 text-sm'} ${VARIANT[variant]} ${className}`}
    >
      {busy && <Spinner />}
      {children}
    </button>
  )
}

export function Spinner({ className = 'w-4 h-4' }: { className?: string }) {
  return <span className={`${className} inline-block rounded-full border-2 border-current border-t-transparent animate-spin`} />
}

// ── Card / Section ────────────────────────────────────────────────────────────
export function Card({ className = '', children, role }: { className?: string; children: ReactNode; role?: string }) {
  return <div role={role} className={`rounded-2xl border border-ink-700 bg-ink-850 ${className}`}>{children}</div>
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 mb-6">
      <div>
        <h1 className="text-2xl font-semibold text-white tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-gray-400 mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

export function EmptyState({ icon, title, children }: { icon: string; title: string; children?: ReactNode }) {
  return (
    <div className="text-center py-14 px-4">
      <div className="text-4xl mb-3" aria-hidden>{icon}</div>
      <p className="text-gray-200 font-medium">{title}</p>
      {children && <div className="text-sm text-gray-400 mt-1.5 max-w-md mx-auto">{children}</div>}
    </div>
  )
}

// ── Status ────────────────────────────────────────────────────────────────────
const STATE_STYLE: Record<string, { dot: string; label: string; chip: string }> = {
  online: { dot: 'bg-emerald-400', label: 'Online', chip: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30' },
  offline: { dot: 'bg-gray-500', label: 'Offline', chip: 'bg-gray-500/10 text-gray-400 ring-gray-500/30' },
  unauthorized: { dot: 'bg-amber-400', label: 'Perlu kebenaran', chip: 'bg-amber-500/10 text-amber-300 ring-amber-500/30' },
  reconnecting: { dot: 'bg-sky-400 animate-pulse', label: 'Menyambung semula', chip: 'bg-sky-500/10 text-sky-300 ring-sky-500/30' },
  absent: { dot: 'bg-gray-600', label: 'Tiada', chip: 'bg-gray-500/10 text-gray-500 ring-gray-500/20' },
}

export function stateOf(d: { state?: DeviceState; is_online: boolean }): DeviceState {
  if (d.state && d.state !== 'absent') return d.state
  return d.is_online ? 'online' : 'offline'
}

export function StatusChip({ state }: { state: string }) {
  const s = STATE_STYLE[state] ?? STATE_STYLE.offline
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${s.chip}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

export function Pill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'brand' | 'warn' }) {
  const t = tone === 'brand' ? 'bg-brand-500/15 text-brand-300' : tone === 'warn' ? 'bg-amber-500/15 text-amber-300' : 'bg-ink-700 text-gray-300'
  return <span className={`inline-block rounded-md px-1.5 py-0.5 text-[11px] font-medium ${t}`}>{children}</span>
}

export function Meter({ value, max, warnBelow = 0.15 }: { value: number; max: number; warnBelow?: number }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  const low = max > 0 && value / max < warnBelow
  return (
    <div className="h-1.5 w-full rounded-full bg-ink-700 overflow-hidden" role="progressbar" aria-valuenow={Math.round(pct)}>
      <div className={`h-full rounded-full ${low ? 'bg-amber-400' : 'bg-brand-500'}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

// ── Modal / Confirm ───────────────────────────────────────────────────────────
export function Modal({ title, onClose, children, footer, wide }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/60 backdrop-blur-sm" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}
        className={`w-full ${wide ? 'sm:max-w-2xl' : 'sm:max-w-md'} max-h-[90vh] overflow-auto rounded-t-2xl sm:rounded-2xl bg-ink-850 border border-ink-600 shadow-2xl animate-slidein`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-700">
          <h2 className="font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl leading-none" aria-label="Tutup">×</button>
        </div>
        <div className="p-5">{children}</div>
        {footer && <div className="px-5 py-4 border-t border-ink-700 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  )
}

export function ConfirmDialog({ title, message, confirmLabel = 'Teruskan', danger, onConfirm, onCancel }: {
  title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void
}) {
  return (
    <Modal title={title} onClose={onCancel} footer={<>
      <Button onClick={onCancel}>Batal</Button>
      <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>{confirmLabel}</Button>
    </>}>
      <div className="text-sm text-gray-300 leading-relaxed">{message}</div>
    </Modal>
  )
}

// ── Toasts ────────────────────────────────────────────────────────────────────
type ToastKind = 'ok' | 'error' | 'info' | 'warn'
interface Toast { id: number; kind: ToastKind; text: string }
const ToastCtx = createContext<(kind: ToastKind, text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const idRef = useRef(0)
  const push = useCallback((kind: ToastKind, text: string) => {
    const id = ++idRef.current
    setItems((p) => [...p.slice(-4), { id, kind, text }])
    setTimeout(() => setItems((p) => p.filter((t) => t.id !== id)), kind === 'error' ? 8000 : 4500)
  }, [])
  const tone: Record<ToastKind, string> = {
    ok: 'border-emerald-500/40', error: 'border-red-500/50', info: 'border-ink-500', warn: 'border-amber-500/50',
  }
  const icon: Record<ToastKind, string> = { ok: '✓', error: '✕', info: 'i', warn: '!' }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed z-[60] bottom-4 right-4 left-4 sm:left-auto sm:w-96 flex flex-col gap-2 pointer-events-none" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`pointer-events-auto flex gap-3 items-start rounded-xl border ${tone[t.kind]} bg-ink-800 px-4 py-3 shadow-xl animate-slidein`}>
            <span className="font-bold text-gray-300 w-4 text-center">{icon[t.kind]}</span>
            <p className="text-sm text-gray-100 break-words">{t.text}</p>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

// ── Form bits ─────────────────────────────────────────────────────────────────
export const inputCls =
  'w-full rounded-lg bg-ink-900 border border-ink-600 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 ' +
  'focus:outline-none focus:ring-2 focus:ring-brand-500/60 focus:border-brand-500'

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-gray-400 mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-xs text-gray-500 mt-1">{hint}</span>}
    </label>
  )
}

/** Async action helper: tracks busy flag and routes errors/success to toasts. */
export function useAction() {
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, okMsg?: string | ((r: T) => string)): Promise<T | undefined> => {
    setBusy(key)
    try {
      const r = await fn()
      if (okMsg) toast('ok', typeof okMsg === 'function' ? okMsg(r) : okMsg)
      return r
    } catch (e) {
      toast('error', (e as Error).message)
      return undefined
    } finally {
      setBusy(null)
    }
  }, [toast])
  return { busy, run }
}
