import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Page } from '../components/AppShell'
import { Button, Card, EmptyState, Field, PageHeader, Pill, StatusChip, inputCls, useAction, useToast } from '../components/ui'
import { useDeviceEvents } from '../hooks/useDeviceEvents'
import { pairingApi, type MdnsService, type PairingStatus } from '../services/deviceApi'

type Tab = 'usb' | 'wifi'

const LIVE_STATE: Record<string, string> = {
  device: 'online', unauthorized: 'unauthorized', offline: 'offline', authorizing: 'unauthorized', 'no permissions': 'offline',
}

const STATE_ADVICE: Record<string, string> = {
  unauthorized: 'Lihat skrin telefon dan tekan "Allow" pada dialog USB debugging. Tandakan "Always allow from this computer".',
  offline: 'Cabut dan pasang semula kabel, atau matikan/hidupkan semula USB debugging / Wireless debugging.',
  authorizing: 'Menunggu kebenaran pada telefon…',
  'no permissions': 'Windows tiada pemacu USB untuk telefon ini. Pasang pemacu USB pengeluar (Google USB driver / Xiaomi / Samsung).',
}

export default function PairingPage() {
  const nav = useNavigate()
  const [tab, setTab] = useState<Tab>('usb')
  const [status, setStatus] = useState<PairingStatus | null>(null)
  const [err, setErr] = useState('')

  const load = useCallback(async () => {
    try { setStatus(await pairingApi.status()); setErr('') } catch (e) { setErr((e as Error).message) }
  }, [])

  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [load])
  useDeviceEvents((e) => { if (e.type === 'changed' || e.type === 'device') load() })

  return (
    <Page>
      <PageHeader title="Pairing Center" subtitle="Sambung telefon melalui USB atau ADB WiFi. Senarai dikemas kini secara langsung." actions={
        <Button onClick={load}>Muat semula</Button>} />

      {status && !status.adb_ok && (
        <Card className="p-4 mb-5 border-red-500/40">
          <p className="text-sm text-red-300"><b>ADB bermasalah:</b> {status.adb_error}</p>
          <p className="text-xs text-gray-400 mt-1">Tutup program lain yang memakai adb (Android Studio, Vysor), kemudian tekan Muat semula.</p>
        </Card>
      )}
      {err && <p className="text-sm text-red-400 mb-4">{err}</p>}

      <div className="inline-flex rounded-xl bg-ink-850 border border-ink-700 p-1 mb-6" role="tablist">
        {([['usb', 'USB'], ['wifi', 'ADB WiFi']] as [Tab, string][]).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`px-5 py-1.5 rounded-lg text-sm font-medium transition-colors ${tab === k ? 'bg-brand-600 text-white' : 'text-gray-400 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'usb' && <UsbTab status={status} onOpen={(id) => nav(`/device/${id}`)} />}
      {tab === 'wifi' && <WifiTab status={status} onChanged={load} />}

      <Card className="p-5 mt-8">
        <h2 className="font-semibold text-white mb-3">Bantuan cepat</h2>
        <ol className="list-decimal pl-5 space-y-1.5 text-sm text-gray-300">
          <li>Settings → About phone → ketuk <b>Build number</b> 7 kali untuk membuka Developer options.</li>
          <li>Developer options → hidupkan <b>USB debugging</b> (untuk kabel) dan/atau <b>Wireless debugging</b> (Android 11+).</li>
          <li>Sambung kabel dan terima dialog <i>Allow USB debugging</i>. Untuk WiFi, guna tab ADB WiFi.</li>
          <li>Xiaomi/Redmi/Poco: hidupkan juga <b>Install via USB</b> dan <b>USB debugging (Security settings)</b>.</li>
          <li>Port Wireless debugging berubah setiap kali ia dihidupkan semula — sambung dengan port terkini.</li>
        </ol>
      </Card>
    </Page>
  )
}

function UsbTab({ status, onOpen }: { status: PairingStatus | null; onOpen: (id: string) => void }) {
  const list = (status?.devices ?? []).filter((d) => d.transport !== 'wifi')
  if (!status) return <p className="text-sm text-gray-500">Mengimbas…</p>
  if (list.length === 0) {
    return (
      <Card><EmptyState icon="🔌" title="Tiada peranti USB dikesan">
        Sambung telefon dengan kabel data (bukan kabel cas sahaja) dan pastikan USB debugging ON. Senarai ini dikemas kini automatik.
      </EmptyState></Card>
    )
  }
  return (
    <div className="grid gap-3">
      {list.map((d) => {
        const st = LIVE_STATE[d.state] ?? 'offline'
        return (
          <Card key={d.serial} className="p-4 flex flex-wrap items-center gap-4">
            <div className="min-w-0 flex-1">
              <p className="font-medium text-white truncate">{d.name}</p>
              <p className="font-mono text-xs text-gray-500 truncate">{d.serial}</p>
              {STATE_ADVICE[d.state] && <p className="text-xs text-amber-300/90 mt-2 leading-relaxed">{STATE_ADVICE[d.state]}</p>}
            </div>
            <Pill tone="brand">{d.transport.toUpperCase()}</Pill>
            <StatusChip state={st} />
            {d.registered && d.device_id && st === 'online' &&
              <Button size="sm" variant="primary" onClick={() => onOpen(d.device_id!)}>Buka</Button>}
          </Card>
        )
      })}
    </div>
  )
}

function WifiTab({ status, onChanged }: { status: PairingStatus | null; onChanged: () => void }) {
  const toast = useToast()
  const { busy, run } = useAction()
  const [pairAddr, setPairAddr] = useState('')
  const [code, setCode] = useState('')
  const [connAddr, setConnAddr] = useState('')
  const [services, setServices] = useState<MdnsService[]>([])
  const [scanned, setScanned] = useState(false)

  const scan = useCallback(async () => {
    const r = await run('scan', () => pairingApi.discover())
    if (r) { setServices(r.services); setScanned(true) }
  }, [run])

  const wifiLive = (status?.devices ?? []).filter((d) => d.transport === 'wifi')

  const doPair = async () => {
    const r = await run('pair', () => pairingApi.pair(pairAddr.trim(), code.trim()))
    if (!r) return
    toast(r.ok ? 'ok' : 'error', r.message)
    if (r.ok) { setCode(''); scan(); onChanged() }
  }
  const doConnect = async (addr = connAddr) => {
    const r = await run('connect', () => pairingApi.connect(addr.trim()))
    if (!r) return
    toast(r.ok ? 'ok' : 'error', r.message)
    if (r.ok) onChanged()
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="p-5 space-y-4">
        <div>
          <h2 className="font-semibold text-white">1 · Pasangkan (sekali sahaja)</h2>
          <p className="text-xs text-gray-400 mt-1">Telefon: Developer options → Wireless debugging → <b>Pair device with pairing code</b>. Masukkan alamat dan kod 6 digit yang dipaparkan.</p>
        </div>
        <Field label="Alamat pairing (IP:port)"><input className={inputCls} placeholder="192.168.1.5:41999" value={pairAddr} onChange={(e) => setPairAddr(e.target.value)} inputMode="url" /></Field>
        <Field label="Kod pairing"><input className={inputCls} placeholder="123456" value={code} maxLength={6} inputMode="numeric"
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} /></Field>
        <Button variant="primary" busy={busy === 'pair'} disabled={!pairAddr.trim() || code.length !== 6} onClick={doPair}>Pasangkan</Button>
      </Card>

      <Card className="p-5 space-y-4">
        <div>
          <h2 className="font-semibold text-white">2 · Sambung</h2>
          <p className="text-xs text-gray-400 mt-1">Gunakan <b>IP address &amp; port</b> pada skrin utama Wireless debugging (bukan port pairing).</p>
        </div>
        <Field label="Alamat sambungan (IP:port)"><input className={inputCls} placeholder="192.168.1.5:37123" value={connAddr}
          onChange={(e) => setConnAddr(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && connAddr.trim() && doConnect()} inputMode="url" /></Field>
        <Button variant="primary" busy={busy === 'connect'} disabled={!connAddr.trim()} onClick={() => doConnect()}>Sambung</Button>
      </Card>

      <Card className="p-5 lg:col-span-2">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="font-semibold text-white">Penemuan automatik (mDNS)</h2>
            <p className="text-xs text-gray-400">Telefon dengan Wireless debugging ON dalam rangkaian yang sama.</p>
          </div>
          <Button busy={busy === 'scan'} onClick={scan}>Imbas rangkaian</Button>
        </div>
        {scanned && services.length === 0 && (
          <p className="text-sm text-gray-400">Tiada perkhidmatan ditemui. mDNS kadang-kadang disekat oleh router/firewall — taip alamat secara manual.</p>
        )}
        <div className="divide-y divide-ink-700">
          {services.map((s) => (
            <div key={s.name + s.kind} className="flex flex-wrap items-center gap-3 py-2.5">
              <Pill tone={s.kind === 'pairing' ? 'warn' : 'brand'}>{s.kind === 'pairing' ? 'Pairing' : 'Sambungan'}</Pill>
              <span className="font-mono text-sm text-gray-200">{s.address}</span>
              <span className="ml-auto flex gap-2">
                {s.kind === 'pairing'
                  ? <Button size="sm" onClick={() => setPairAddr(s.address)}>Guna untuk pairing</Button>
                  : <Button size="sm" variant="primary" busy={busy === 'connect'} onClick={() => { setConnAddr(s.address); doConnect(s.address) }}>Sambung</Button>}
              </span>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-5 lg:col-span-2">
        <h2 className="font-semibold text-white mb-3">Peranti WiFi aktif</h2>
        {wifiLive.length === 0 ? <p className="text-sm text-gray-400">Tiada.</p> : (
          <div className="divide-y divide-ink-700">
            {wifiLive.map((d) => (
              <div key={d.serial} className="flex flex-wrap items-center gap-3 py-2.5">
                <span className="text-sm text-white">{d.name}</span>
                <span className="font-mono text-xs text-gray-500 truncate max-w-[18rem]">{d.serial}</span>
                <StatusChip state={LIVE_STATE[d.state] ?? 'offline'} />
                {/^\d+\.\d+\.\d+\.\d+:\d+$/.test(d.serial) && (
                  <Button size="sm" variant="ghost" className="ml-auto" busy={busy === `d:${d.serial}`}
                    onClick={async () => { await run(`d:${d.serial}`, () => pairingApi.disconnect(d.serial), 'Diputuskan.'); onChanged() }}>
                    Putuskan
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
