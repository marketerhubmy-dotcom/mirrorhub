import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Page } from '../components/AppShell'
import { Button, Card, ConfirmDialog, EmptyState, Field, PageHeader, Pill, inputCls, stateOf, useAction, useToast } from '../components/ui'
import { useDevices } from '../hooks/useDevices'
import { appsApi, fmtBytes, type ApkInfo, type InstallResult } from '../services/deviceApi'

export default function AppsPage() {
  const toast = useToast()
  const [params] = useSearchParams()
  const { devices } = useDevices(5000)
  const online = useMemo(() => devices.filter((d) => stateOf(d) === 'online'), [devices])
  const { busy, run } = useAction()

  const [apks, setApks] = useState<ApkInfo[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set(params.get('device') ? [params.get('device')!] : []))
  const [apk, setApk] = useState('')
  const [opts, setOpts] = useState({ replace: true, grant: true, downgrade: false })
  const [results, setResults] = useState<InstallResult[] | null>(null)
  const [drag, setDrag] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const loadApks = useCallback(async () => {
    try { const a = await appsApi.apks(); setApks(a); setApk((cur) => cur || a[0]?.name || '') } catch (e) { toast('error', (e as Error).message) }
  }, [toast])
  useEffect(() => { loadApks() }, [loadApks])

  const upload = async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      if (!f.name.toLowerCase().endsWith('.apk')) { toast('error', `${f.name}: hanya fail .apk`); continue }
      const r = await run(`up:${f.name}`, () => appsApi.uploadApk(f), (x) => `${x.name} dimuat naik (${fmtBytes(x.size)})`)
      if (r) setApk(r.name)
    }
    loadApks()
  }

  const toggle = (id: string) => setSelected((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const allOnline = online.length > 0 && online.every((d) => selected.has(d.device_id))

  const install = async () => {
    setResults(null)
    const r = await run('install', () => appsApi.installMany([...selected], apk, opts))
    if (r) {
      setResults(r.results)
      toast(r.succeeded === r.total ? 'ok' : 'warn', `${r.succeeded}/${r.total} peranti berjaya.`)
    }
  }

  return (
    <Page wide>
      <PageHeader title="Aplikasi & APK" subtitle="Pasang APK pada satu atau banyak telefon sekaligus, dan urus aplikasi sedia ada." />

      <div className="grid gap-5 lg:grid-cols-5">
        <Card className="p-5 lg:col-span-2 space-y-4">
          <h2 className="font-semibold text-white">Pustaka APK</h2>
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}
            onClick={() => fileRef.current?.click()} role="button" tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && fileRef.current?.click()}
            className={`cursor-pointer rounded-xl border-2 border-dashed px-4 py-8 text-center text-sm transition-colors
              ${drag ? 'border-brand-400 bg-brand-600/10' : 'border-ink-600 hover:border-ink-500'}`}>
            <p className="text-gray-300">Seret fail .apk ke sini atau klik untuk pilih</p>
            <p className="text-xs text-gray-500 mt-1">Disimpan dalam folder data Mirrorhub</p>
            <input ref={fileRef} type="file" accept=".apk" multiple hidden onChange={(e) => e.target.files && upload(e.target.files)} />
          </div>
          {busy?.startsWith('up:') && <p className="text-xs text-gray-400">Memuat naik…</p>}

          {apks.length === 0 ? <p className="text-sm text-gray-500">Belum ada APK.</p> : (
            <ul className="space-y-1.5" aria-label="Senarai APK">
              {apks.map((a) => (
                <li key={a.name}>
                  <label className={`flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer border ${apk === a.name ? 'border-brand-500 bg-brand-600/10' : 'border-transparent hover:bg-ink-700'}`}>
                    <input type="radio" name="apk" checked={apk === a.name} onChange={() => setApk(a.name)} />
                    <span className="min-w-0 flex-1 truncate text-sm text-gray-100" title={a.name}>{a.name}</span>
                    <span className="text-xs text-gray-500">{fmtBytes(a.size)}</span>
                    <button className="text-gray-500 hover:text-red-400 text-sm" aria-label={`Padam ${a.name}`}
                      onClick={async (e) => { e.preventDefault(); await run('delapk', () => appsApi.deleteApk(a.name), 'APK dipadam daripada pustaka.'); if (apk === a.name) setApk(''); loadApks() }}>🗑</button>
                  </label>
                </li>
              ))}
            </ul>
          )}

          <div className="space-y-2 text-sm text-gray-300 pt-2 border-t border-ink-700">
            {([['replace', 'Ganti jika sudah dipasang (-r)'], ['grant', 'Beri semua kebenaran (-g)'], ['downgrade', 'Benarkan downgrade (-d)']] as const).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />{label}</label>
            ))}
          </div>
        </Card>

        <Card className="p-5 lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-white">Pasang pada peranti</h2>
            {online.length > 0 && (
              <Button size="sm" variant="ghost" onClick={() => setSelected(allOnline ? new Set() : new Set(online.map((d) => d.device_id)))}>
                {allOnline ? 'Nyahpilih semua' : 'Pilih semua online'}
              </Button>
            )}
          </div>
          {online.length === 0 ? (
            <EmptyState icon="📱" title="Tiada peranti online">Sambung telefon dari Pairing Center.</EmptyState>
          ) : (
            <ul className="grid sm:grid-cols-2 gap-2" aria-label="Pilih peranti">
              {online.map((d) => (
                <li key={d.device_id}>
                  <label className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer ${selected.has(d.device_id) ? 'border-brand-500 bg-brand-600/10' : 'border-ink-700 hover:border-ink-500'}`}>
                    <input type="checkbox" checked={selected.has(d.device_id)} onChange={() => toggle(d.device_id)} />
                    <span className="min-w-0"><span className="block text-sm text-white truncate">{d.device_name}</span>
                      <span className="block text-xs text-gray-500 truncate">{d.model || d.adb_address}</span></span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <Button variant="primary" busy={busy === 'install'} disabled={!apk || selected.size === 0} onClick={install}>
            Pasang pada {selected.size} peranti
          </Button>

          {results && (
            <div className="rounded-xl border border-ink-700 divide-y divide-ink-700" role="status">
              {results.map((r) => (
                <div key={r.device_id} className="flex gap-3 px-4 py-2.5 text-sm">
                  <span className={r.ok ? 'text-emerald-400' : 'text-red-400'}>{r.ok ? '✓' : '✕'}</span>
                  <span className="text-gray-200 w-40 truncate">{r.name ?? r.device_id}</span>
                  <span className="text-gray-400 flex-1">{r.message}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <InstalledApps devices={online} initial={params.get('device') ?? ''} />
    </Page>
  )
}

function InstalledApps({ devices, initial }: { devices: { device_id: string; device_name: string }[]; initial: string }) {
  const { busy, run } = useAction()
  const [id, setId] = useState(initial)
  const [list, setList] = useState<string[]>([])
  const [q, setQ] = useState('')
  const [confirm, setConfirm] = useState<{ kind: 'uninstall' | 'clear'; pkg: string } | null>(null)

  useEffect(() => { if (!id && devices[0]) setId(devices[0].device_id) }, [devices, id])
  const load = useCallback(async () => {
    if (!id) return
    const r = await run('list', () => appsApi.packages(id))
    if (r) setList(r.packages)
  }, [id, run])
  useEffect(() => { setList([]); load() }, [load])

  const filtered = list.filter((p) => p.toLowerCase().includes(q.toLowerCase()))

  return (
    <Card className="p-5 mt-5">
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <h2 className="font-semibold text-white mr-auto">Aplikasi dipasang (pihak ketiga)</h2>
        <Field label="Peranti">
          <select className={inputCls} value={id} onChange={(e) => setId(e.target.value)}>
            {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.device_name}</option>)}
          </select>
        </Field>
        <input className={`${inputCls} sm:w-56`} placeholder="Cari pakej…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari pakej" />
        <Button busy={busy === 'list'} onClick={load}>Muat semula</Button>
      </div>
      {!id ? <p className="text-sm text-gray-500">Pilih peranti online.</p> : filtered.length === 0 ? (
        <p className="text-sm text-gray-500">{busy === 'list' ? 'Memuatkan…' : 'Tiada aplikasi.'}</p>
      ) : (
        <div className="divide-y divide-ink-700 max-h-[26rem] overflow-auto">
          {filtered.map((p) => (
            <div key={p} className="flex flex-wrap items-center gap-2 py-2">
              <span className="font-mono text-sm text-gray-200 mr-auto break-all">{p}</span>
              <Button size="sm" onClick={() => run(`l:${p}`, () => appsApi.launch(id, p), (r) => r.message)}>Buka</Button>
              <Button size="sm" variant="ghost" onClick={() => run(`s:${p}`, () => appsApi.forceStop(id, p), (r) => r.message)}>Henti</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirm({ kind: 'clear', pkg: p })}>Kosongkan data</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirm({ kind: 'uninstall', pkg: p })}>Nyahpasang</Button>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-gray-500 mt-3"><Pill>{filtered.length}</Pill> pakej dipaparkan</p>

      {confirm && (
        <ConfirmDialog danger title={confirm.kind === 'uninstall' ? 'Nyahpasang aplikasi?' : 'Kosongkan data aplikasi?'}
          confirmLabel={confirm.kind === 'uninstall' ? 'Nyahpasang' : 'Kosongkan'}
          message={<><span className="font-mono">{confirm.pkg}</span><br />
            {confirm.kind === 'uninstall' ? 'Aplikasi dan datanya akan dipadam daripada telefon.' : 'Semua data aplikasi (log masuk, tetapan) akan dipadam. Tindakan ini tidak boleh dibuat asal.'}</>}
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            const c = confirm; setConfirm(null)
            await run('c', () => c.kind === 'uninstall' ? appsApi.uninstall(id, c.pkg) : appsApi.clearData(id, c.pkg), (r) => r.message)
            load()
          }} />
      )}
    </Card>
  )
}
