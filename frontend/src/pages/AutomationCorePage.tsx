import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Page } from '../components/AppShell'
import { Button, Card, EmptyState, Field, PageHeader, Pill, inputCls, stateOf, useAction, useToast } from '../components/ui'
import { useDevices } from '../hooks/useDevices'
import { autoApi, type AutoRun, type AutoStep } from '../services/deviceApi'

interface Def { type: string; label: string; fields: { key: string; label: string; kind: 'text' | 'num' | 'rel' | 'bool' | 'select'; options?: string[]; placeholder?: string }[]; init: Record<string, unknown> }

const DEFS: Def[] = [
  { type: 'open_app', label: 'Buka aplikasi', fields: [{ key: 'package', label: 'Pakej', kind: 'text', placeholder: 'com.tiktok.android' }], init: { package: '' } },
  { type: 'close_app', label: 'Tutup aplikasi', fields: [{ key: 'package', label: 'Pakej', kind: 'text' }], init: { package: '' } },
  { type: 'tap', label: 'Ketik (x,y)', fields: [{ key: 'x', label: 'X 0–1', kind: 'rel' }, { key: 'y', label: 'Y 0–1', kind: 'rel' }], init: { x: 0.5, y: 0.5 } },
  { type: 'long_press', label: 'Tekan lama', fields: [{ key: 'x', label: 'X 0–1', kind: 'rel' }, { key: 'y', label: 'Y 0–1', kind: 'rel' }], init: { x: 0.5, y: 0.5 } },
  { type: 'swipe', label: 'Leret', fields: [{ key: 'x1', label: 'X1', kind: 'rel' }, { key: 'y1', label: 'Y1', kind: 'rel' }, { key: 'x2', label: 'X2', kind: 'rel' }, { key: 'y2', label: 'Y2', kind: 'rel' }], init: { x1: 0.5, y1: 0.8, x2: 0.5, y2: 0.2, ms: 300 } },
  { type: 'text', label: 'Taip teks', fields: [{ key: 'value', label: 'Teks (tanpa baris baharu)', kind: 'text' }], init: { value: '' } },
  { type: 'key', label: 'Tekan kekunci', fields: [{ key: 'code', label: 'Kod', kind: 'text', placeholder: 'KEYCODE_ENTER' }], init: { code: 'KEYCODE_ENTER' } },
  { type: 'nav', label: 'Navigasi', fields: [{ key: 'action', label: 'Tindakan', kind: 'select', options: ['home', 'back', 'recents'] }], init: { action: 'home' } },
  { type: 'wait', label: 'Tunggu (saat)', fields: [{ key: 'seconds', label: 'Saat', kind: 'num' }], init: { seconds: 2 } },
  { type: 'tap_text', label: 'Ketik teks pada skrin', fields: [{ key: 'text', label: 'Teks butang', kind: 'text' }, { key: 'contains', label: 'Mengandungi', kind: 'bool' }], init: { text: '', contains: false } },
  { type: 'wait_text', label: 'Tunggu teks muncul', fields: [{ key: 'text', label: 'Teks', kind: 'text' }, { key: 'contains', label: 'Mengandungi', kind: 'bool' }], init: { text: '', contains: false, timeout: 30 } },
  { type: 'screenshot', label: 'Tangkap skrin', fields: [], init: {} },
]
const DEF = Object.fromEntries(DEFS.map((d) => [d.type, d]))
const KEY = 'mirrorhub.automation.templates.v1'

type Row = AutoStep & { _id: number }

function loadTemplates(): Record<string, AutoStep[]> {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '{}') } catch { return {} }
}
function saveTemplates(t: Record<string, AutoStep[]>) {
  try { localStorage.setItem(KEY, JSON.stringify(t)) } catch { /* private mode: templates are a convenience only */ }
}

export default function AutomationCorePage() {
  const toast = useToast()
  const { devices } = useDevices(5000)
  const online = useMemo(() => devices.filter((d) => stateOf(d) === 'online'), [devices])
  const { busy, run } = useAction()
  const idRef = useRef(1)

  const [name, setName] = useState('Automasi baharu')
  const [steps, setSteps] = useState<Row[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [add, setAdd] = useState(DEFS[0].type)
  const [runId, setRunId] = useState('')
  const [current, setCurrent] = useState<AutoRun | null>(null)
  const [templates, setTemplates] = useState<Record<string, AutoStep[]>>(loadTemplates)

  const poll = useCallback(async () => {
    if (!runId) return
    try { setCurrent(await autoApi.run(runId)) } catch { /* transient */ }
  }, [runId])
  useEffect(() => {
    if (!runId) return
    poll()
    const t = setInterval(poll, 1000)
    return () => clearInterval(t)
  }, [runId, poll])
  const running = current?.state === 'running'

  const addStep = () => setSteps((s) => [...s, { _id: idRef.current++, type: add, ...DEF[add].init }])
  const patch = (id: number, p: Partial<AutoStep>) => setSteps((s) => s.map((r) => (r._id === id ? { ...r, ...p } : r)))
  const move = (i: number, d: number) => setSteps((s) => { const n = [...s]; const j = i + d; if (j < 0 || j >= n.length) return n; [n[i], n[j]] = [n[j], n[i]]; return n })
  const clean = (): AutoStep[] => steps.map(({ _id, ...rest }) => { void _id; return rest })

  const start = async () => {
    const r = await run('start', () => autoApi.start(name, [...selected], clean()))
    if (r) { setRunId(r.id); setCurrent(r); toast('info', 'Automasi dimulakan.') }
  }

  const check = () => run('validate', () => autoApi.validate(clean()), 'Semua langkah sah.')

  const saveTpl = () => {
    const n = name.trim()
    if (!n || steps.length === 0) return
    const next = { ...templates, [n]: clean() }
    setTemplates(next); saveTemplates(next); toast('ok', `Templat "${n}" disimpan.`)
  }
  const loadTpl = (n: string) => {
    const t = templates[n]
    if (!t) return
    setName(n)
    setSteps(t.map((s) => ({ ...s, _id: idRef.current++ })))
  }
  const delTpl = (n: string) => { const next = { ...templates }; delete next[n]; setTemplates(next); saveTemplates(next) }

  const toggle = (id: string) => setSelected((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })

  return (
    <Page wide>
      <PageHeader title="Automasi" subtitle="Bina urutan langkah dan jalankan pada satu atau banyak telefon serentak. Boleh dibatalkan pada bila-bila masa." />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <Card className="p-5 space-y-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="flex-1 min-w-[12rem]"><Field label="Nama"><input className={inputCls} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /></Field></div>
              {Object.keys(templates).length > 0 && (
                <Field label="Templat">
                  <select className={inputCls} value="" onChange={(e) => e.target.value && loadTpl(e.target.value)}>
                    <option value="">Muat templat…</option>
                    {Object.keys(templates).map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </Field>
              )}
              <Button onClick={saveTpl} disabled={steps.length === 0}>Simpan templat</Button>
            </div>

            {steps.length === 0 ? <EmptyState icon="🧩" title="Belum ada langkah">Tambah langkah di bawah.</EmptyState> : (
              <ol className="space-y-2">
                {steps.map((s, i) => {
                  const def = DEF[s.type]
                  return (
                    <li key={s._id} className="rounded-xl border border-ink-700 bg-ink-900 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Pill tone="brand">{i + 1}</Pill>
                        <span className="text-sm font-medium text-white mr-2">{def.label}</span>
                        {def.fields.map((f) => (
                          <label key={f.key} className="flex items-center gap-1.5 text-xs text-gray-400">
                            {f.kind !== 'bool' && f.label}
                            {f.kind === 'bool' ? (
                              <><input type="checkbox" checked={Boolean(s[f.key])} onChange={(e) => patch(s._id, { [f.key]: e.target.checked })} /> {f.label}</>
                            ) : f.kind === 'select' ? (
                              <select className={`${inputCls} !w-auto !py-1`} value={String(s[f.key])} onChange={(e) => patch(s._id, { [f.key]: e.target.value })}>
                                {f.options!.map((o) => <option key={o}>{o}</option>)}
                              </select>
                            ) : f.kind === 'text' ? (
                              <input className={`${inputCls} !py-1 min-w-[10rem]`} value={String(s[f.key] ?? '')} placeholder={f.placeholder} onChange={(e) => patch(s._id, { [f.key]: e.target.value })} />
                            ) : (
                              <input className={`${inputCls} !py-1 !w-20`} type="number" step={f.kind === 'rel' ? 0.05 : 1} min={0} max={f.kind === 'rel' ? 1 : 600}
                                value={Number(s[f.key] ?? 0)} onChange={(e) => patch(s._id, { [f.key]: Number(e.target.value) })} />
                            )}
                          </label>
                        ))}
                        <span className="ml-auto flex items-center gap-1">
                          <button className="px-1.5 text-gray-400 hover:text-white" onClick={() => move(i, -1)} aria-label="Naik">↑</button>
                          <button className="px-1.5 text-gray-400 hover:text-white" onClick={() => move(i, 1)} aria-label="Turun">↓</button>
                          <button className="px-1.5 text-gray-500 hover:text-red-400" onClick={() => setSteps((x) => x.filter((r) => r._id !== s._id))} aria-label="Buang">✕</button>
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-gray-500">
                        <label className="flex items-center gap-1">Cuba semula <input className={`${inputCls} !py-0.5 !w-14`} type="number" min={0} max={5} value={Number(s.retries ?? 0)} onChange={(e) => patch(s._id, { retries: Number(e.target.value) })} /></label>
                        <label className="flex items-center gap-1">Had masa (s) <input className={`${inputCls} !py-0.5 !w-16`} type="number" min={1} max={600} placeholder="auto" value={s.timeout === undefined ? '' : Number(s.timeout)} onChange={(e) => patch(s._id, { timeout: e.target.value ? Number(e.target.value) : undefined })} /></label>
                        <label className="flex items-center gap-1"><input type="checkbox" checked={Boolean(s.continue_on_error)} onChange={(e) => patch(s._id, { continue_on_error: e.target.checked })} /> Teruskan jika gagal</label>
                      </div>
                    </li>
                  )
                })}
              </ol>
            )}

            <div className="flex flex-wrap gap-2">
              <select className={`${inputCls} !w-auto`} value={add} onChange={(e) => setAdd(e.target.value)} aria-label="Jenis langkah">
                {DEFS.map((d) => <option key={d.type} value={d.type}>{d.label}</option>)}
              </select>
              <Button onClick={addStep}>+ Tambah langkah</Button>
              <Button variant="ghost" busy={busy === 'validate'} disabled={steps.length === 0} onClick={check}>Semak</Button>
              {steps.length > 0 && <Button variant="ghost" onClick={() => setSteps([])}>Kosongkan</Button>}
            </div>
          </Card>

          {current && <RunPanel run={current} onCancel={() => run('cancel', () => autoApi.cancel(current.id), 'Pembatalan dihantar.')} cancelling={busy === 'cancel'} />}
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-white">Peranti</h2>
              <Button size="sm" variant="ghost" onClick={() => setSelected(selected.size === online.length ? new Set() : new Set(online.map((d) => d.device_id)))}>
                {selected.size === online.length && online.length > 0 ? 'Nyahpilih' : 'Pilih semua'}
              </Button>
            </div>
            {online.length === 0 ? <p className="text-sm text-gray-500">Tiada peranti online.</p> : (
              <ul className="space-y-1.5">
                {online.map((d) => (
                  <li key={d.device_id}>
                    <label className={`flex items-center gap-3 rounded-lg border px-3 py-2 cursor-pointer ${selected.has(d.device_id) ? 'border-brand-500 bg-brand-600/10' : 'border-ink-700'}`}>
                      <input type="checkbox" checked={selected.has(d.device_id)} onChange={() => toggle(d.device_id)} />
                      <span className="text-sm text-white truncate">{d.device_name}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <Button className="w-full mt-4" variant="primary" busy={busy === 'start'} disabled={steps.length === 0 || selected.size === 0 || running} onClick={start}>
              {running ? 'Sedang berjalan…' : `Jalankan pada ${selected.size} peranti`}
            </Button>
            <p className="text-[11px] text-gray-500 mt-3 leading-relaxed">Automasi menggerakkan telefon sebenar (ketik, taip, buka aplikasi). Semak urutan dengan satu peranti dahulu.</p>
          </Card>

          {Object.keys(templates).length > 0 && (
            <Card className="p-5">
              <h2 className="font-semibold text-white mb-2">Templat tersimpan</h2>
              <ul className="space-y-1">
                {Object.keys(templates).map((n) => (
                  <li key={n} className="flex items-center justify-between text-sm">
                    <button className="text-brand-300 hover:underline truncate" onClick={() => loadTpl(n)}>{n}</button>
                    <button className="text-gray-500 hover:text-red-400 text-xs" onClick={() => delTpl(n)}>Padam</button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </Page>
  )
}

const STATE_TONE: Record<string, string> = {
  queued: 'text-gray-400', running: 'text-sky-300', succeeded: 'text-emerald-400', failed: 'text-red-400', cancelled: 'text-amber-300',
}
const STATE_LABEL: Record<string, string> = { queued: 'Beratur', running: 'Berjalan', succeeded: 'Berjaya', failed: 'Gagal', cancelled: 'Dibatalkan' }

function RunPanel({ run, onCancel, cancelling }: { run: AutoRun; onCancel: () => void; cancelling: boolean }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-semibold text-white">{run.name}</h2>
          <p className={`text-xs ${STATE_TONE[run.state] ?? 'text-gray-400'}`}>{STATE_LABEL[run.state] ?? run.state}</p>
        </div>
        {run.state === 'running' && <Button variant="danger" busy={cancelling} onClick={onCancel}>Batal</Button>}
      </div>
      <div className="space-y-4">
        {run.devices.map((d) => {
          const pct = run.total_steps ? Math.round((d.steps_done / run.total_steps) * 100) : 0
          return (
            <div key={d.device_id}>
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="text-white">{d.name}</span>
                <span className={`text-xs ${STATE_TONE[d.state]}`}>{STATE_LABEL[d.state]} · {d.steps_done}/{run.total_steps}</span>
              </div>
              <div className="h-1.5 rounded-full bg-ink-700 overflow-hidden"><div className={`h-full ${d.state === 'failed' ? 'bg-red-500' : 'bg-brand-500'}`} style={{ width: `${pct}%` }} /></div>
              {d.error && <p className="text-xs text-red-300 mt-1.5">{d.error}</p>}
              {d.logs && d.logs.length > 0 && (
                <pre className="mt-2 max-h-36 overflow-auto rounded-lg bg-ink-950 p-2.5 text-[11px] leading-relaxed text-gray-400 whitespace-pre-wrap">
                  {d.logs.slice(-12).map((l) => `${l.t.slice(11, 19)} ${l.msg}`).join('\n')}
                </pre>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
