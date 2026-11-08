import { Fragment, useCallback, useMemo, useState } from 'react'
import { Page } from '../components/AppShell'
import { LineChart, UsageBar, type Series } from '../components/Charts'
import { Button, Card, EmptyState, Field, Modal, PageHeader, Pill, inputCls, useAction, useToast } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { fmtBytes, perfApi, saveBlob, type Health, type PerfDevice, type PerfEvent, type PerfOverview, type PerfPoint, type PerfRange } from '../services/deviceApi'

const RANGES: [PerfRange, string][] = [['5m', '5 min'], ['15m', '15 min'], ['1h', '1 jam'], ['session', 'Sesi']]

const HEALTH: Record<Health | 'system-healthy' | 'system-degraded', { label: string; cls: string; dot: string }> = {
  healthy: { label: 'Sihat', cls: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30', dot: 'bg-emerald-400' },
  degraded: { label: 'Terjejas', cls: 'bg-amber-500/10 text-amber-300 ring-amber-500/30', dot: 'bg-amber-400' },
  reconnecting: { label: 'Menyambung semula', cls: 'bg-sky-500/10 text-sky-300 ring-sky-500/30', dot: 'bg-sky-400 animate-pulse' },
  disconnected: { label: 'Terputus', cls: 'bg-gray-500/10 text-gray-400 ring-gray-500/30', dot: 'bg-gray-500' },
  authorization_required: { label: 'Perlu kebenaran', cls: 'bg-orange-500/10 text-orange-300 ring-orange-500/30', dot: 'bg-orange-400' },
  'system-healthy': { label: 'Sistem sihat', cls: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30', dot: 'bg-emerald-400' },
  'system-degraded': { label: 'Perlu perhatian', cls: 'bg-amber-500/10 text-amber-300 ring-amber-500/30', dot: 'bg-amber-400' },
}

function HealthChip({ h }: { h: keyof typeof HEALTH }) {
  const s = HEALTH[h]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap ${s.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />{s.label}
    </span>
  )
}

const NA = ({ why }: { why?: string }) => <span className="text-gray-500" title={why}>N/A{why ? <span className="sr-only"> — {why}</span> : null}</span>
const n1 = (v: number | null | undefined, unit = '') => (v === null || v === undefined ? null : `${Math.round(v * 10) / 10}${unit}`)

function fmtDur(s: number | null): string | null {
  if (s === null) return null
  if (s < 90) return `${Math.round(s)} s`
  if (s < 5400) return `${Math.round(s / 60)} min`
  return `${(s / 3600).toFixed(1)} j`
}

function Stat({ label, value, sub, bar, tone, children }: { label: string; value: React.ReactNode; sub?: React.ReactNode; bar?: number | null; tone?: string; children?: React.ReactNode }) {
  return (
    <Card className="p-4 flex flex-col gap-2 min-w-0">
      <div className="text-[11px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${tone ?? 'text-white'}`}>{value}</div>
      {bar !== undefined && <UsageBar pct={bar} />}
      {sub && <div className="text-xs text-gray-400 leading-snug">{sub}</div>}
      {children}
    </Card>
  )
}

export default function PerformancePage() {
  const toast = useToast()
  const { busy, run } = useAction()
  const [range, setRange] = useState<PerfRange>('5m')
  const [ov, setOv] = useState<PerfOverview | null>(null)
  const [hist, setHist] = useState<PerfPoint[] | null>(null)
  const [devs, setDevs] = useState<PerfDevice[] | null>(null)
  const [events, setEvents] = useState<PerfEvent[]>([])
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [tab, setTab] = useState<'events' | 'alerts' | 'summary'>('events')
  const [evFilter, setEvFilter] = useState('')
  const [showTh, setShowTh] = useState(false)
  const [summary, setSummary] = useState<string[] | null>(null)

  const loadFast = useCallback(async () => {
    try {
      const s = await perfApi.snapshot()            // one request for cards + device table
      setOv(s.overview); setDevs(s.devices); setErr('')
    } catch (e) { setErr((e as Error).message) }
  }, [])
  const loadSlow = useCallback(async () => {
    try {
      const [h, e] = await Promise.all([perfApi.history(range), perfApi.events(150)])
      setHist(h.points); setEvents(e)
    } catch { /* the fast poll already reports a backend outage */ }
  }, [range])
  usePolling(loadFast, 3000)
  usePolling(loadSlow, range === 'session' ? 10000 : 5000)

  const rows = (hist ?? []) as unknown as { t: number; [k: string]: number | null }[]
  const th = ov?.thresholds
  const charts: { title: string; series: Series[]; yMax?: number; fixed?: boolean; unit?: string; empty?: string }[] = useMemo(() => [
    { title: 'CPU', yMax: 100, fixed: true, unit: '%', series: [{ key: 'sys_cpu', label: 'PC', color: '#818cf8', unit: '%' }, { key: 'proc_cpu', label: 'Mirrorhub', color: '#34d399', unit: '%' }] },
    { title: 'RAM PC', yMax: 100, fixed: true, unit: '%', series: [{ key: 'sys_ram_pct', label: 'PC', color: '#f472b6', unit: '%' }] },
    { title: 'Memori proses Mirrorhub', unit: ' MB', series: [{ key: 'proc_rss_mb', label: 'RSS', color: '#34d399', unit: ' MB' }] },
    { title: 'FPS strim (purata strim aktif)', unit: ' fps', empty: 'N/A: tiada strim aktif, atau semua strim idle (skrin statik tidak menghantar bingkai).', series: [{ key: 'fps_avg', label: 'FPS', color: '#fbbf24', unit: ' fps' }] },
    { title: 'Strim aktif', unit: '', series: [{ key: 'streams', label: 'Strim', color: '#60a5fa' }, { key: 'devices_connected', label: 'Peranti', color: '#94a3b8', dashed: true }] },
    { title: 'Sambungan semula (per sampel)', unit: '', series: [{ key: 'reconnects', label: 'Reconnect', color: '#fb923c' }] },
    { title: 'Sambungan WebSocket', unit: '', series: [{ key: 'ws', label: 'WebSocket', color: '#a78bfa' }] },
    { title: 'Thread & handle proses', unit: '', series: [{ key: 'proc_threads', label: 'Thread', color: '#2dd4bf' }, { key: 'proc_handles', label: 'Handle', color: '#64748b', dashed: true }] },
  ], [])

  const copyReport = () => run('copy', async () => {
    const txt = await perfApi.reportText()
    try { await navigator.clipboard.writeText(txt) } catch {
      const ta = document.createElement('textarea'); ta.value = txt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove()
    }
    return txt
  }, 'Laporan disalin ke papan klip (IP, kunci dan nama pengguna disembunyikan).')
  const exportJson = () => run('json', async () => {
    const r = await perfApi.reportJson()
    saveBlob(new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' }), `mirrorhub-diagnostik-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.json`)
  }, 'Laporan JSON dimuat turun.')
  const showSummary = () => run('sum', async () => {
    const r = (await perfApi.reportJson()) as { summary?: string[] }
    setSummary(r.summary ?? []); setTab('summary')
  })

  const sortedDevs = useMemo(() => {
    const rank: Record<string, number> = { degraded: 0, reconnecting: 1, authorization_required: 2, healthy: 3, disconnected: 4 }
    return [...(devs ?? [])].sort((a, b) => Number(b.online) - Number(a.online) || rank[a.health] - rank[b.health] || a.name.localeCompare(b.name))
  }, [devs])
  const toggle = (id: string) => setOpen((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const evShown = events.filter((e) => !evFilter || e.kind === evFilter || e.device_id === evFilter).slice().reverse()
  const nameOf = (id: string | null) => devs?.find((d) => d.device_id === id)?.name ?? (id ? id.slice(0, 8) : '—')
  const sysHealth = ov ? (ov.health.status === 'healthy' ? 'system-healthy' : 'system-degraded') : null

  return (
    <Page wide>
      <PageHeader
        title="Prestasi"
        subtitle="Metrik sebenar PC, proses Mirrorhub dan setiap telefon. Nilai yang tidak dapat diukur dipaparkan N/A dengan sebabnya."
        actions={<>
          <div className="inline-flex rounded-xl bg-ink-850 border border-ink-700 p-1" role="group" aria-label="Tempoh sejarah">
            {RANGES.map(([k, l]) => (
              <button key={k} onClick={() => setRange(k)} aria-pressed={range === k}
                className={`px-3 py-1 rounded-lg text-xs font-medium ${range === k ? 'bg-brand-600 text-white' : 'text-gray-400 hover:text-white'}`}>{l}</button>
            ))}
          </div>
          <Button onClick={() => setShowTh(true)}>Ambang</Button>
          <Button busy={busy === 'copy'} onClick={copyReport}>Salin laporan</Button>
          <Button busy={busy === 'json'} onClick={exportJson}>Eksport JSON</Button>
          <a href={perfApi.csvUrl('history', range === 'session' ? 'session' : range)} download>
            <Button variant="secondary">Eksport CSV</Button>
          </a>
        </>}
      />

      {err && (
        <Card className="p-4 mb-5 border-red-500/40" role="alert">
          <p className="text-sm text-red-300">Tidak dapat menghubungi backend: {err}</p>
          <p className="text-xs text-gray-400 mt-1">Data akan dimuat semula secara automatik apabila backend pulih.</p>
        </Card>
      )}

      {ov && ov.alerts.length > 0 && (
        <div className="space-y-2 mb-5" aria-live="polite">
          {ov.alerts.map((a) => (
            <div key={a.key + a.scope} className={`rounded-xl border px-4 py-3 text-sm flex flex-wrap items-center gap-3 ${a.severity === 'critical' ? 'border-red-500/40 bg-red-500/10 text-red-200' : 'border-amber-500/40 bg-amber-500/10 text-amber-100'}`}>
              <b>{a.title}</b>
              <span className="opacity-90">{a.message}</span>
              {a.scope !== 'system' && <Pill tone="warn">{nameOf(a.scope)}</Pill>}
            </div>
          ))}
        </div>
      )}

      {/* Overview */}
      {!ov ? (
        <p className="text-sm text-gray-500 mb-6">Memuatkan metrik…</p>
      ) : (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-3 mb-6">
          <Stat label="Kesihatan" value={<HealthChip h={sysHealth!} />} sub={ov.health.reason} />
          <Stat label="Peranti" value={<span>{ov.devices.connected}<span className="text-sm text-gray-500"> / {ov.devices_total}</span></span>}
            sub={<>Terputus {ov.devices.disconnected} · Perlu kebenaran {ov.devices.unauthorized}{ov.devices.reconnecting ? ` · Menyambung ${ov.devices.reconnecting}` : ''}</>} />
          <Stat label="Strim aktif" value={ov.active_streams} sub={`WebSocket: ${ov.ws_total} (video ${ov.ws.video ?? 0}, kawalan ${ov.ws.control ?? 0}, acara ${ov.ws.devices ?? 0})`} />
          <Stat label="FPS purata (strim aktif)" value={ov.fps_avg === null ? <NA why={ov.fps_note ?? undefined} /> : n1(ov.fps_avg)}
            sub={ov.fps_avg === null ? ov.fps_note : 'Strim idle tidak dikira dalam purata.'} />
          <Stat label="CPU PC (keseluruhan)" value={ov.pc.cpu_pct === null ? <NA why="Belum ada sampel kedua / bukan Windows" /> : `${n1(ov.pc.cpu_pct)}%`}
            bar={ov.pc.cpu_pct} sub={`${ov.pc.cpu_count ?? '?'} CPU logik`} />
          <Stat label="RAM PC (keseluruhan)" value={ov.pc.ram_pct === null ? <NA why="Tidak dapat dibaca" /> : `${n1(ov.pc.ram_pct)}%`}
            bar={ov.pc.ram_pct} sub={ov.pc.ram_used_mb !== null && ov.pc.ram_total_mb ? `${fmtBytes(ov.pc.ram_used_mb * 1048576)} / ${fmtBytes(ov.pc.ram_total_mb * 1048576)}` : undefined} />
          <Stat label="Mirrorhub: CPU" value={ov.process.cpu_pct === null ? <NA /> : `${n1(ov.process.cpu_pct)}%`} bar={ov.process.cpu_pct === null ? null : Math.min(100, ov.process.cpu_pct * 4)}
            sub={<span title={ov.process.note}>Proses backend sahaja (dinormalkan kepada semua CPU)</span>} />
          <Stat label="Mirrorhub: RAM" value={ov.process.rss_mb === null ? <NA /> : fmtBytes(ov.process.rss_mb * 1048576)}
            sub={`${ov.process.threads ?? '?'} thread · ${ov.process.handles ?? '?'} handle`} />
          <Stat label="Sambung semula (5 min)" value={ov.reconnects['5m']} sub={`15 min: ${ov.reconnects['15m']} · 1 jam: ${ov.reconnects['1h']}`}
            tone={ov.reconnects['5m'] >= Number(th?.perf_reconnect_loop_count ?? 5) ? 'text-amber-300' : undefined} />
        </div>
      )}

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2 mb-8">
        {charts.map((c) => (
          <LineChart key={c.title} title={c.title} rows={rows} series={c.series} yMax={c.yMax} fixedMax={c.fixed} yUnit={c.unit} loading={hist === null} empty={c.empty} />
        ))}
      </div>

      {/* Per-device */}
      <h2 className="text-lg font-semibold text-white mb-3">Peranti</h2>
      <Card className="overflow-hidden mb-8">
        {devs === null ? <p className="p-5 text-sm text-gray-500">Memuatkan…</p> : devs.length === 0 ? (
          <EmptyState icon="📱" title="Tiada peranti didaftarkan">Sambung telefon dari Pairing Center untuk melihat prestasi per peranti.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[860px]">
              <thead className="text-[11px] uppercase tracking-wider text-gray-500 text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">Peranti</th><th className="px-2 py-3 font-medium">Kesihatan</th>
                  <th className="px-2 py-3 font-medium">FPS</th><th className="px-2 py-3 font-medium">Resolusi</th>
                  <th className="px-2 py-3 font-medium">Bitrate</th><th className="px-2 py-3 font-medium">Mula</th>
                  <th className="px-2 py-3 font-medium">Reconnect</th><th className="px-2 py-3 font-medium">Uptime</th><th className="px-2 py-3 font-medium">Bateri</th><th />
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {sortedDevs.map((d) => (
                  <Fragment key={d.device_id}>
                    <tr className="hover:bg-ink-800/60 cursor-pointer" onClick={() => toggle(d.device_id)}>
                      <td className="px-4 py-3 min-w-0">
                        <div className="font-medium text-white truncate max-w-[14rem]" title={d.name}>{d.name}</div>
                        <div className="text-[11px] text-gray-500 flex gap-2 items-center">
                          <span className="font-mono">{d.device_id.slice(0, 8)}</span>
                          {d.transport ? <Pill tone="brand">{d.transport === 'emulator' ? 'Maya' : d.transport === 'wifi' ? 'WiFi' : 'USB'}</Pill> : <NA why="Pengangkutan belum diketahui" />}
                        </div>
                      </td>
                      <td className="px-2 py-3"><HealthChip h={d.health} /></td>
                      <td className="px-2 py-3 tabular-nums">
                        {d.fps === null ? <NA why={d.na.fps} /> : <span title={`purata bergolek ${n1(d.fps_avg)} fps`}>{n1(d.fps)} <span className="text-gray-500 text-xs">({n1(d.fps_avg)})</span></span>}
                        {d.activity === 'idle' && <div className="text-[10px] text-gray-500">idle</div>}
                      </td>
                      <td className="px-2 py-3">{d.resolution ?? <NA why={d.na.resolution} />}</td>
                      <td className="px-2 py-3 tabular-nums">{d.bitrate_kbps === null ? <NA why={d.na.bitrate_kbps ?? d.na.fps} /> : `${Math.round(d.bitrate_kbps)} kbps`}</td>
                      <td className="px-2 py-3 tabular-nums">{d.startup_s === null ? <NA why={d.na.startup_s} /> : `${d.startup_s} s`}</td>
                      <td className="px-2 py-3 tabular-nums">{d.reconnects}{d.reconnects_recent > 0 && <span className="text-amber-300 text-xs"> ({d.reconnects_recent} baru)</span>}</td>
                      <td className="px-2 py-3 tabular-nums">{fmtDur(d.uptime_s) ?? <NA why={d.na.uptime_s} />}</td>
                      <td className="px-2 py-3 tabular-nums">{d.battery === null ? <NA why="Peranti offline" /> : `${d.battery}%`}</td>
                      <td className="px-3 py-3 text-gray-500">{open.has(d.device_id) ? '▾' : '▸'}</td>
                    </tr>
                    {open.has(d.device_id) && (
                      <tr className="bg-ink-900/60">
                        <td colSpan={10} className="px-4 py-4">
                          <p className="text-sm text-gray-200 mb-3">{d.health_reason}</p>
                          <div className="grid gap-4 md:grid-cols-3 text-xs">
                            <div>
                              <h4 className="text-gray-500 uppercase tracking-wider mb-1.5">Bingkai</h4>
                              <p className="text-gray-300">Dihantar server: <b className="tabular-nums">{d.frames_sent}</b> · Digugurkan (backpressure): <b className="tabular-nums">{d.frames_dropped_server}</b></p>
                              {d.client ? (
                                <p className="text-gray-300 mt-1">Pelayar ({d.client.profile}): diterima <b className="tabular-nums">{d.client.received}</b> · dinyahkod <b className="tabular-nums">{d.client.decoded}</b> · digugurkan <b className="tabular-nums">{d.client.dropped}</b></p>
                              ) : <p className="text-gray-500 mt-1">Pelayar: <NA why={d.na.client} /> — {d.na.client}</p>}
                            </div>
                            <div>
                              <h4 className="text-gray-500 uppercase tracking-wider mb-1.5">Peranti</h4>
                              <p className="text-gray-300">Status: {d.state} · Storan bebas: {d.storage_free_mb && d.storage_total_mb ? `${fmtBytes(d.storage_free_mb * 1048576)} / ${fmtBytes(d.storage_total_mb * 1048576)}` : <NA why={d.na.storage} />}</p>
                              <p className="text-gray-300 mt-1">Ralat terakhir: {d.last_error ? <span className="text-red-300">{d.last_error}</span> : <span className="text-gray-500">tiada</span>}</p>
                            </div>
                            <div>
                              <h4 className="text-gray-500 uppercase tracking-wider mb-1.5">Sesi strim</h4>
                              {d.streams.length === 0 ? <p className="text-gray-500">Tiada strim aktif.</p> : d.streams.map((s) => (
                                <p key={s.profile} className="text-gray-300">{s.profile}: {s.state} · {s.viewers} penonton · {s.reconnects} reconnect · {s.activity}</p>
                              ))}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Diagnostics */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="inline-flex rounded-xl bg-ink-850 border border-ink-700 p-1" role="tablist">
          {([['events', 'Peristiwa'], ['alerts', 'Amaran'], ['summary', 'Ringkasan masalah']] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => { setTab(k); if (k === 'summary') showSummary() }}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium ${tab === k ? 'bg-brand-600 text-white' : 'text-gray-400 hover:text-white'}`}>{l}</button>
          ))}
        </div>
        <div className="flex gap-2 items-center">
          {tab === 'events' && (
            <select className={`${inputCls} !w-auto !py-1.5`} value={evFilter} onChange={(e) => setEvFilter(e.target.value)} aria-label="Tapis peristiwa">
              <option value="">Semua</option>
              {['stream', 'device', 'adb', 'alert', 'error'].map((k) => <option key={k} value={k}>{k}</option>)}
              {(devs ?? []).map((d) => <option key={d.device_id} value={d.device_id}>{d.name}</option>)}
            </select>
          )}
          <a href={perfApi.csvUrl('events')} download><Button size="sm">CSV peristiwa</Button></a>
          <a href={perfApi.csvUrl('devices')} download><Button size="sm">CSV peranti</Button></a>
        </div>
      </div>
      <Card className="p-0 overflow-hidden mb-4">
        {tab === 'events' && (evShown.length === 0 ? <p className="p-5 text-sm text-gray-500">Tiada peristiwa direkodkan sejak aplikasi dimulakan.</p> : (
          <ul className="divide-y divide-ink-800 max-h-80 overflow-auto font-mono text-xs">
            {evShown.map((e) => (
              <li key={e.id} className="px-4 py-2 flex gap-3">
                <span className="text-gray-500 shrink-0">{new Date(e.t * 1000).toLocaleTimeString()}</span>
                <span className={`shrink-0 w-14 ${e.level === 'warn' || e.level === 'error' ? 'text-amber-300' : 'text-gray-400'}`}>{e.kind}</span>
                {e.device_id && <span className="shrink-0 text-brand-300 truncate max-w-[8rem]">{nameOf(e.device_id)}</span>}
                <span className="text-gray-200 break-all">{e.message}</span>
              </li>
            ))}
          </ul>
        ))}
        {tab === 'alerts' && <AlertsTab />}
        {tab === 'summary' && (
          <div className="p-5 space-y-2 text-sm text-gray-200">
            {summary === null ? <p className="text-gray-500">Menjana ringkasan…</p> : summary.map((s, i) => <p key={i}>• {s}</p>)}
            <p className="text-xs text-gray-500 pt-2">Eksport tidak mengandungi kunci, fail peribadi atau kandungan skrin; IP, nombor siri dan nama pengguna Windows disembunyikan.</p>
          </div>
        )}
      </Card>

      {showTh && <ThresholdsModal onClose={() => setShowTh(false)} onSaved={(m) => { toast('ok', m); loadFast() }} />}
    </Page>
  )
}

function AlertsTab() {
  const [data, setData] = useState<Awaited<ReturnType<typeof perfApi.alerts>> | null>(null)
  usePolling(async () => setData(await perfApi.alerts()), 5000)
  if (!data) return <p className="p-5 text-sm text-gray-500">Memuatkan…</p>
  return (
    <div className="p-5 space-y-4">
      <div>
        <h4 className="text-xs uppercase tracking-wider text-gray-500 mb-2">Aktif</h4>
        {data.active.length === 0 ? <p className="text-sm text-gray-400">Tiada amaran aktif.</p> : data.active.map((a) => <p key={a.key + a.scope} className="text-sm text-amber-200">• {a.title}: {a.message}</p>)}
      </div>
      <div>
        <h4 className="text-xs uppercase tracking-wider text-gray-500 mb-2">Sejarah terkini</h4>
        {data.history.length === 0 ? <p className="text-sm text-gray-500">Belum ada.</p> : (
          <ul className="text-xs font-mono space-y-1 max-h-48 overflow-auto">
            {data.history.slice().reverse().map((h, i) => <li key={i} className="text-gray-300"><span className="text-gray-500">{new Date(h.t * 1000).toLocaleTimeString()}</span> {h.event === 'cleared' ? '✓' : '⚠'} {h.message}</li>)}
          </ul>
        )}
      </div>
    </div>
  )
}

const TH_FIELDS: { key: string; label: string; hint: string; unit: string; bool?: boolean }[] = [
  { key: 'perf_ram_high_pct', label: 'RAM PC tinggi', hint: 'Amaran bila RAM ≥ nilai ini (pulih di bawah nilai − 5).', unit: '%' },
  { key: 'perf_cpu_high_pct', label: 'CPU PC tinggi', hint: 'Dikira berterusan; pulih di bawah nilai − 15.', unit: '%' },
  { key: 'perf_cpu_sustain_s', label: 'CPU tinggi berterusan', hint: 'Tempoh minimum sebelum amaran.', unit: 's' },
  { key: 'perf_fps_low', label: 'FPS rendah (strim aktif)', hint: 'Hanya untuk strim yang sedang menghantar data; skrin statik (idle) tidak dikira.', unit: 'fps' },
  { key: 'perf_reconnect_loop_count', label: 'Gelung reconnect: bilangan', hint: 'Bilangan sambungan semula dalam tetingkap di bawah.', unit: '×' },
  { key: 'perf_reconnect_window_s', label: 'Gelung reconnect: tetingkap', hint: '', unit: 's' },
  { key: 'perf_startup_slow_s', label: 'Strim lambat bermula', hint: 'Masa hingga bingkai pertama.', unit: 's' },
  { key: 'perf_max_streams', label: 'Had strim aktif', hint: 'Amaran bila melebihi.', unit: '' },
  { key: 'perf_rss_growth_mb', label: 'Pertumbuhan memori proses', hint: 'Kenaikan RSS dalam ≤ 10 min.', unit: 'MB' },
  { key: 'perf_alert_cooldown_s', label: 'Cooldown amaran', hint: 'Amaran yang sama tidak diumumkan semula dalam tempoh ini.', unit: 's' },
  { key: 'perf_alerts_enabled', label: 'Beri notifikasi amaran', hint: 'Matikan untuk senyap (kad dan jadual tetap dikemas kini).', unit: '', bool: true },
]

function ThresholdsModal({ onClose, onSaved }: { onClose: () => void; onSaved: (m: string) => void }) {
  const { busy, run } = useAction()
  const [vals, setVals] = useState<Record<string, number | boolean> | null>(null)
  const [defaults, setDefaults] = useState<Record<string, number | boolean>>({})
  usePolling(async () => {
    if (vals) return
    const { defaults: d, ...cur } = await perfApi.thresholds()
    setDefaults(d); setVals(cur as Record<string, number | boolean>)
  }, 60000)
  const save = async () => {
    const patch = Object.fromEntries(Object.entries(vals ?? {}).filter(([k]) => k in defaults))
    const r = await run('save', () => perfApi.putThresholds(patch))
    if (r) { onSaved('Ambang disimpan.'); onClose() }
  }
  return (
    <Modal wide title="Ambang amaran dan kesihatan" onClose={onClose} footer={<>
      <Button onClick={() => setVals({ ...defaults })}>Set semula lalai</Button>
      <Button onClick={onClose}>Batal</Button>
      <Button variant="primary" busy={busy === 'save'} disabled={!vals} onClick={save}>Simpan</Button>
    </>}>
      {!vals ? <p className="text-sm text-gray-500">Memuatkan…</p> : (
        <div className="grid gap-4 sm:grid-cols-2">
          {TH_FIELDS.map((f) => (
            <Field key={f.key} label={`${f.label}${f.unit ? ` (${f.unit})` : ''}`} hint={f.hint}>
              {f.bool ? (
                <input type="checkbox" checked={Boolean(vals[f.key])} onChange={(e) => setVals({ ...vals, [f.key]: e.target.checked })} />
              ) : (
                <input className={inputCls} type="number" value={Number(vals[f.key])} onChange={(e) => setVals({ ...vals, [f.key]: Number(e.target.value) })} />
              )}
            </Field>
          ))}
        </div>
      )}
      <p className="text-xs text-gray-500 mt-4 leading-relaxed">
        <b>Tafsiran:</b> Sihat = peranti online dan strim lancar (atau idle). Terjejas = FPS rendah semasa skrin aktif, gelung reconnect, strim lambat/gagal. Menyambung semula = peranti atau strim sedang pulih. Terputus = tiada sambungan. Perlu kebenaran = telefon belum menekan Allow.
      </p>
    </Modal>
  )
}
