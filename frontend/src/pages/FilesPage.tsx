import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Page } from '../components/AppShell'
import { Button, Card, ConfirmDialog, EmptyState, Field, Modal, PageHeader, inputCls, stateOf, useAction, useToast } from '../components/ui'
import { useDevices } from '../hooks/useDevices'
import { filesApi, fmtBytes, type DirListing, type RemoteEntry } from '../services/deviceApi'

const ROOTS = [['/sdcard', 'Storan dalaman'], ['/sdcard/DCIM', 'Kamera'], ['/sdcard/Download', 'Muat turun'], ['/sdcard/Pictures', 'Gambar'], ['/sdcard/Movies', 'Video'], ['/data/local/tmp', 'Sementara']]

const join = (dir: string, name: string) => (dir === '/' ? '' : dir.replace(/\/$/, '')) + '/' + name

export default function FilesPage() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const { devices } = useDevices(5000)
  const online = useMemo(() => devices.filter((d) => stateOf(d) === 'online'), [devices])
  const { busy, run } = useAction()

  const [id, setId] = useState(params.get('device') ?? '')
  const [path, setPath] = useState(params.get('path') ?? '/sdcard')
  const [listing, setListing] = useState<DirListing | null>(null)
  const [error, setError] = useState('')
  const [drag, setDrag] = useState(false)
  const [rename, setRename] = useState<RemoteEntry | null>(null)
  const [del, setDel] = useState<RemoteEntry | null>(null)
  const [mk, setMk] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { if (!id && online[0]) setId(online[0].device_id) }, [online, id])

  const load = useCallback(async (p = path) => {
    if (!id) return
    setError('')
    try { setListing(await filesApi.list(id, p)); setPath(p) } catch (e) { setError((e as Error).message); setListing(null) }
  }, [id, path])

  useEffect(() => { load() /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [id])
  useEffect(() => { setParams((p) => { const n = new URLSearchParams(p); if (id) n.set('device', id); n.set('path', path); return n }, { replace: true }) }, [id, path, setParams])

  const crumbs = useMemo(() => {
    const parts = path.split('/').filter(Boolean)
    return [{ label: '/', to: '/' }, ...parts.map((p, i) => ({ label: p, to: '/' + parts.slice(0, i + 1).join('/') }))]
  }, [path])

  const upload = async (files: FileList | File[]) => {
    const arr = Array.from(files)
    if (!arr.length) return
    const r = await run('upload', () => filesApi.upload(id, path, arr))
    if (r) {
      const failed = r.results.filter((x) => !x.ok)
      toast(failed.length ? 'warn' : 'ok', failed.length ? `${r.succeeded} berjaya, ${failed.length} gagal: ${failed[0].message ?? failed[0].name}` : `${r.succeeded} fail dimuat naik.`)
      load()
    }
  }

  const open = (e: RemoteEntry) => { if (e.is_dir) load(join(path, e.name)) }

  return (
    <Page wide>
      <PageHeader title="Pengurus Fail" subtitle="Layari storan telefon, muat naik/turun fail dan uruskan folder." actions={
        <Field label="Peranti">
          <select className={inputCls} value={id} onChange={(e) => setId(e.target.value)} aria-label="Peranti">
            {online.length === 0 && <option value="">Tiada peranti online</option>}
            {online.map((d) => <option key={d.device_id} value={d.device_id}>{d.device_name}</option>)}
          </select>
        </Field>} />

      {!id ? (
        <Card><EmptyState icon="📁" title="Pilih peranti online">Sambung telefon dari Pairing Center untuk melayari failnya.</EmptyState></Card>
      ) : (
        <Card className="overflow-hidden" >
          <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-ink-700">
            <nav className="flex flex-wrap items-center gap-1 text-sm min-w-0 mr-auto" aria-label="Laluan">
              {crumbs.map((c, i) => (
                <span key={c.to} className="flex items-center gap-1">
                  {i > 0 && <span className="text-gray-600">/</span>}
                  <button className="text-brand-300 hover:underline" onClick={() => load(c.to)}>{c.label}</button>
                </span>
              ))}
            </nav>
            <select className={`${inputCls} !w-auto`} value="" onChange={(e) => e.target.value && load(e.target.value)} aria-label="Pintasan">
              <option value="">Pintasan…</option>
              {ROOTS.map(([p, l]) => <option key={p} value={p}>{l}</option>)}
            </select>
            <Button size="sm" onClick={() => load()}>Muat semula</Button>
            <Button size="sm" onClick={() => setMk(true)}>Folder baharu</Button>
            <Button size="sm" variant="primary" busy={busy === 'upload'} onClick={() => fileRef.current?.click()}>Muat naik</Button>
            <input ref={fileRef} type="file" multiple hidden onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = '' }} />
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}
            className={`min-h-[22rem] ${drag ? 'bg-brand-600/10 outline outline-2 outline-dashed outline-brand-400 -outline-offset-4' : ''}`}>
            {error && <p className="p-5 text-sm text-red-400">{error}</p>}
            {listing && listing.entries.length === 0 && <EmptyState icon="🗂️" title="Folder kosong">Seret fail ke sini untuk memuat naik.</EmptyState>}
            {listing && listing.entries.length > 0 && (
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-500 text-left"><tr><th className="px-4 py-2 font-medium">Nama</th><th className="px-2 py-2 font-medium hidden sm:table-cell">Saiz</th><th className="px-2 py-2 font-medium hidden md:table-cell">Diubah</th><th /></tr></thead>
                <tbody className="divide-y divide-ink-800">
                  {listing.parent !== null && listing.path !== '/' && (
                    <tr className="hover:bg-ink-800 cursor-pointer" onClick={() => load(listing.parent!)}>
                      <td className="px-4 py-2 text-gray-300" colSpan={4}>↩ ..</td>
                    </tr>
                  )}
                  {listing.entries.map((e) => (
                    <tr key={e.name} className="hover:bg-ink-800">
                      <td className="px-4 py-2">
                        <button className="flex items-center gap-2 text-left text-gray-100 hover:text-white max-w-[28rem]" onClick={() => open(e)} disabled={!e.is_dir}>
                          <span aria-hidden>{e.is_dir ? '📁' : '📄'}</span><span className="truncate">{e.name}</span>
                        </button>
                      </td>
                      <td className="px-2 py-2 text-gray-400 hidden sm:table-cell">{e.is_dir ? '—' : fmtBytes(e.size)}</td>
                      <td className="px-2 py-2 text-gray-500 hidden md:table-cell">{e.modified}</td>
                      <td className="px-2 py-2 text-right whitespace-nowrap">
                        {!e.is_dir && <a className="text-brand-300 hover:underline text-xs mr-3" href={filesApi.downloadUrl(id, join(path, e.name))} download>Muat turun</a>}
                        <button className="text-gray-400 hover:text-white text-xs mr-3" onClick={() => setRename(e)}>Nama semula</button>
                        <button className="text-gray-500 hover:text-red-400 text-xs" onClick={() => setDel(e)}>Padam</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      )}

      {mk && <NameModal title="Folder baharu" label="Nama folder" initial="" onClose={() => setMk(false)}
        onSubmit={async (name) => { setMk(false); await run('mk', () => filesApi.mkdir(id, join(path, name)), 'Folder dicipta.'); load() }} />}
      {rename && <NameModal title="Namakan semula" label="Nama baharu" initial={rename.name} onClose={() => setRename(null)}
        onSubmit={async (name) => { const r = rename; setRename(null); await run('rn', () => filesApi.rename(id, join(path, r.name), name), 'Dinamakan semula.'); load() }} />}
      {del && <ConfirmDialog danger title={`Padam ${del.is_dir ? 'folder' : 'fail'}?`} confirmLabel="Padam"
        message={<><span className="font-mono break-all">{join(path, del.name)}</span><br />{del.is_dir ? 'Folder dan semua kandungannya akan dipadam ' : 'Fail akan dipadam '}secara kekal daripada telefon.</>}
        onCancel={() => setDel(null)}
        onConfirm={async () => { const d = del; setDel(null); await run('rm', () => filesApi.remove(id, join(path, d.name)), 'Dipadam.'); load() }} />}
    </Page>
  )
}

function NameModal({ title, label, initial, onClose, onSubmit }: {
  title: string; label: string; initial: string; onClose: () => void; onSubmit: (v: string) => void
}) {
  const [v, setV] = useState(initial)
  const bad = !v.trim() || v.includes('/')
  return (
    <Modal title={title} onClose={onClose} footer={<><Button onClick={onClose}>Batal</Button><Button variant="primary" disabled={bad} onClick={() => onSubmit(v.trim())}>OK</Button></>}>
      <Field label={label} hint={v.includes('/') ? 'Nama tidak boleh mengandungi /' : undefined}>
        <input className={inputCls} value={v} autoFocus onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && !bad && onSubmit(v.trim())} />
      </Field>
    </Modal>
  )
}
