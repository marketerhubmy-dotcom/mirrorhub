import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useDeviceEvents } from '../hooks/useDeviceEvents'
import { ToastProvider, useToast } from './ui'

const NAV = [
  { to: '/', label: 'Peranti', icon: '📱', end: true },
  { to: '/device-wall', label: 'Device Wall', icon: '🖥️' },
  { to: '/pairing', label: 'Pairing Center', icon: '🔗' },
  { to: '/performance', label: 'Prestasi', icon: '📈' },
  { to: '/apps', label: 'Aplikasi & APK', icon: '📦' },
  { to: '/files', label: 'Fail', icon: '📁' },
  { to: '/automation', label: 'Automasi', icon: '⚡' },
  { to: '/advanced', label: 'Lanjutan', icon: '🧰' },
  { to: '/system', label: 'Sistem', icon: '⚙️' },
]

function EventToaster() {
  const toast = useToast()
  useDeviceEvents((e) => {
    if (e.type === 'device' && e.action === 'state' && e.state === 'unauthorized') {
      toast('warn', e.message || 'Telefon perlu membenarkan PC ini.')
    } else if (e.type === 'device' && e.action === 'online') {
      toast('ok', `Peranti disambungkan (${e.serial})`)
    } else if (e.type === 'device' && e.action === 'gone') {
      toast('info', `Peranti terputus (${e.serial})`)
    } else if (e.type === 'device' && e.action === 'reconnect_failed') {
      toast('error', `Tidak dapat sambung semula ${e.serial}. Port Wireless Debugging mungkin berubah.`)
    } else if (e.type === 'alert' && e.action === 'triggered') {
      toast('warn', String(e.message ?? 'Amaran prestasi'))
    } else if (e.type === 'alert' && e.action === 'cleared') {
      toast('ok', String(e.message ?? 'Amaran pulih'))
    } else if (e.type === 'adb' && e.ok === false) {
      toast('error', `ADB bermasalah: ${e.message}`)
    } else if (e.type === 'adb' && e.ok === true) {
      toast('ok', 'ADB pulih.')
    }
  })
  return null
}

function Inner({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  useEffect(() => setOpen(false), [loc.pathname])

  const link = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive ? 'bg-brand-600/20 text-white ring-1 ring-brand-500/40' : 'text-gray-400 hover:text-white hover:bg-ink-700'}`

  return (
    <div className="h-screen flex bg-ink-900 text-gray-100 font-sans">
      <EventToaster />
      {open && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={`fixed lg:static z-40 inset-y-0 left-0 w-60 shrink-0 bg-ink-950 border-r border-ink-700 flex flex-col
        transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="px-5 py-5 flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand-500 to-fuchsia-500 grid place-items-center text-white font-bold">M</span>
          <span className="text-lg font-semibold tracking-tight text-white">Mirrorhub</span>
        </div>
        <nav className="flex-1 px-3 space-y-1 overflow-y-auto" aria-label="Navigasi utama">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={link}>
              <span aria-hidden className="w-5 text-center">{n.icon}</span>{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 text-[11px] text-gray-500 border-t border-ink-700">
          API tempatan sahaja (127.0.0.1)
        </div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 border-b border-ink-700 bg-ink-950">
          <button onClick={() => setOpen(true)} className="text-gray-300 text-xl" aria-label="Buka menu">☰</button>
          <span className="font-semibold">Mirrorhub</span>
        </div>
        <main className="flex-1 min-h-0 overflow-auto">{children}</main>
      </div>
    </div>
  )
}

export default function AppShell({ children }: { children: ReactNode }) {
  return <ToastProvider><Inner>{children}</Inner></ToastProvider>
}

/** Standard padded page container for non-fullscreen pages. */
export function Page({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return <div className={`mx-auto w-full ${wide ? 'max-w-7xl' : 'max-w-5xl'} px-4 sm:px-8 py-6 sm:py-8`}>{children}</div>
}
