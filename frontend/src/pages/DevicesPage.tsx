import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Page } from '../components/AppShell'
import { Button, Card, ConfirmDialog, EmptyState, Field, Meter, Modal, PageHeader, Pill, StatusChip, inputCls, stateOf, useAction, useToast } from '../components/ui'
import { useDevices } from '../hooks/useDevices'
import { managerApi, saveBlob, fmtBytes } from '../services/deviceApi'
import type { Device } from '../types'

type Filter = 'all' | 'online' | 'attention' | 'offline'

export default function DevicesPage() {
  const nav = useNavigate()
  const { devices, loading, error, refresh } = useDevices(4000)
  const { busy, run } = useAction()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [group, setGroup] = useState('')
  const [editing, setEditing] = useState<Device | null>(null)
  const [forgetting, setForgetting] = useState<Device | null>(null)

  const counts = useMemo(() => {
    const c = { online: 0, attention: 0, offline: 0 }
    devices.forEach((d) => {
      const s = stateOf(d)
      if (s === 'online') c.online++
      else if (s === 'unauthorized' || s === 'reconnecting') c.attention++
      else c.offline++
    })
    return c
  }, [devices])

  const groups = useMemo(() => [...new Set(devices.map((d) => d.group_name).filter(Boolean) as string[])].sort(), [devices])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return devices
      .filter((d) => {
        const s = stateOf(d)
        if (filter === 'online' && s !== 'online') return false
        if (filter === 'attention' && !(s === 'unauthorized' || s === 'reconnecting')) return false
        if (filter === 'offline' && !(s === 'offline' || s === 'absent')) return false
        if (group && d.group_name !== group) return false
        if (!q) return true
        return [d.device_name, d.model, d.adb_address, d.group_name, ...(d.tags ?? [])].join(' ').toLowerCase().includes(q)
      })
      .sort((a, b) => Number(b.is_online) - Number(a.is_online) || a.device_name.localeCompare(b.device_name))
  }, [devices, query, filter, group])

  const shot = (d: Device) =>
    run(`shot:${d.device_id}`, async () => saveBlob(await managerApi.screenshot(d.device_id), `${d.device_name}.png`), 'Tangkapan skrin disimpan.')

  return (
    <Page wide>
      <PageHeader
        title="Peranti"
        subtitle="Semua telefon Android anda — USB dan ADB WiFi — dalam satu tempat."
        actions={<>
          <Button onClick={() => refresh()}>Muat semula</Button>
          <Button variant="secondary" onClick={() => nav('/device-wall')}>Buka Device Wall</Button>
          <Button variant="primary" onClick={() => nav('/pairing')}>+ Tambah telefon</Button>
        </>}
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {([
          ['all', 'Semua', devices.length],
          ['online', 'Online', counts.online],
          ['attention', 'Perlu tindakan', counts.attention],
          ['offline', 'Offline', counts.offline],
        ] as [Filter, string, number][]).map(([k, label, n]) => (
          <button key={k} onClick={() => setFilter(k)} aria-pressed={filter === k}
            className={`text-left rounded-xl border px-4 py-3 transition-colors ${filter === k ? 'border-brand-500 bg-brand-600/10' : 'border-ink-700 bg-ink-850 hover:border-ink-500'}`}>
            <div className="text-2xl font-semibold text-white">{n}</div>
            <div className="text-xs text-gray-400">{label}</div>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mb-5">
        <input className={`${inputCls} sm:max-w-xs`} placeholder="Cari nama, model, tag, alamat…" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Cari peranti" />
        {groups.length > 0 && (
          <select className={`${inputCls} sm:max-w-[12rem]`} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Kumpulan">
            <option value="">Semua kumpulan</option>
            {groups.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        )}
      </div>

      {error && <p className="text-sm text-red-400 mb-4">Tidak dapat menghubungi backend: {error}</p>}
      {loading && <p className="text-sm text-gray-500">Memuatkan…</p>}

      {!loading && devices.length === 0 && (
        <Card>
          <EmptyState icon="📱" title="Belum ada telefon">
            Sambung telefon dengan kabel USB (USB debugging ON) atau pasangkan melalui WiFi.
            <div className="mt-4"><Link to="/pairing" className="text-brand-300 hover:underline">Buka Pairing Center →</Link></div>
          </EmptyState>
        </Card>
      )}
      {!loading && devices.length > 0 && shown.length === 0 && (
        <Card><EmptyState icon="🔎" title="Tiada peranti sepadan dengan penapis" /></Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((d) => (
          <DeviceCard key={d.device_id} d={d} busy={busy} run={run}
            onEdit={() => setEditing(d)} onForget={() => setForgetting(d)} onShot={() => shot(d)} afterAction={refresh} />
        ))}
      </div>

      {editing && <EditModal device={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refresh() }} />}
      {forgetting && (
        <ConfirmDialog danger title="Lupakan peranti?" confirmLabel="Lupakan"
          message={<>Rekod <b>{forgetting.device_name}</b> dalam Mirrorhub akan dipadam (nama, tag, kumpulan). Telefon tidak terjejas dan akan didaftar semula jika disambung lagi.</>}
          onCancel={() => setForgetting(null)}
          onConfirm={async () => {
            const id = forgetting.device_id
            setForgetting(null)
            await run(`forget:${id}`, () => managerApi.forget(id), 'Peranti dilupakan.')
            refresh()
          }} />
      )}
    </Page>
  )
}

function DeviceCard({ d, busy, run, onEdit, onForget, onShot, afterAction }: {
  d: Device
  busy: string | null
  run: ReturnType<typeof useAction>['run']
  onEdit: () => void
  onForget: () => void
  onShot: () => void
  afterAction: () => void
}) {
  const nav = useNavigate()
  const toast = useToast()
  const s = stateOf(d)
  const online = s === 'online'
  const isEmu = (d.transport as string) === 'emulator'
  const isWifi = !isEmu && (d.transport === 'wifi' || (d.adb_address ?? '').includes(':'))
  const total = d.storage_total_mb ?? 0
  const free = d.storage_free_mb ?? 0

  return (
    <Card className={`p-5 flex flex-col gap-4 ${online ? '' : 'opacity-90'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-white truncate" title={d.device_name}>{d.device_name}</h3>
          <p className="text-xs text-gray-400 truncate">
            {[d.manufacturer, d.model].filter(Boolean).join(' ') || 'Model tidak diketahui'}
            {d.android_version ? ` · Android ${d.android_version}` : ''}
          </p>
        </div>
        <StatusChip state={s} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Pill tone="brand">{isEmu ? 'Maya' : isWifi ? 'WiFi' : 'USB'}</Pill>
        {d.group_name && <Pill>{d.group_name}</Pill>}
        {(d.tags ?? []).map((t) => <Pill key={t}>#{t}</Pill>)}
      </div>

      {online ? (
        <div className="space-y-2.5 text-xs text-gray-400">
          <div className="flex items-center justify-between"><span>Bateri</span><span className="text-gray-200">{d.battery}%</span></div>
          <Meter value={d.battery} max={100} warnBelow={0.2} />
          {total > 0 && (<>
            <div className="flex items-center justify-between"><span>Storan bebas</span><span className="text-gray-200">{fmtBytes(free * 1048576)} / {fmtBytes(total * 1048576)}</span></div>
            <Meter value={free} max={total} />
          </>)}
        </div>
      ) : (
        <p className="text-xs text-amber-300/90 bg-amber-500/10 rounded-lg px-3 py-2 leading-relaxed">
          {d.last_error || (s === 'unauthorized' ? 'Benarkan dialog USB debugging pada telefon.' : 'Peranti tidak disambungkan.')}
        </p>
      )}

      {online && d.input_state === 'blocked' && (
        <p className="text-xs text-amber-300 bg-amber-500/10 rounded-lg px-3 py-2 leading-relaxed" role="alert">
          <b>Input disekat oleh telefon.</b> Skrin boleh dilihat tetapi ketik/taip tidak berfungsi. Xiaomi/Redmi/Poco: hidupkan
          &quot;USB debugging (Security settings)&quot; dalam Developer options.
        </p>
      )}

      <p className="font-mono text-[11px] text-gray-500 truncate" title={d.adb_address ?? ''}>{d.adb_address ?? '—'}</p>

      <div className="flex flex-wrap gap-2 mt-auto">
        {online && <Button variant="primary" size="sm" onClick={() => nav(`/device/${d.device_id}`)}>Buka & kawal</Button>}
        {online && <Button size="sm" busy={busy === `shot:${d.device_id}`} onClick={onShot}>Tangkap skrin</Button>}
        {online && <Button size="sm" onClick={() => nav(`/apps?device=${d.device_id}`)}>Apl</Button>}
        {online && <Button size="sm" onClick={() => nav(`/files?device=${d.device_id}`)}>Fail</Button>}
        {online && (
          <Button size="sm" variant="ghost" busy={busy === `refresh:${d.device_id}`}
            onClick={async () => { await run(`refresh:${d.device_id}`, () => managerApi.refresh(d.device_id), 'Maklumat dikemas kini.'); afterAction() }}>
            Segarkan
          </Button>
        )}
        {!online && isWifi && d.adb_address && (
          <Button size="sm" variant="primary" busy={busy === `rc:${d.device_id}`}
            onClick={async () => {
              const r = await run(`rc:${d.device_id}`, () => managerApi.reconnect(d.device_id))
              if (r) toast(r.ok ? 'ok' : 'error', r.message)
              afterAction()
            }}>
            Sambung semula
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>
        {!online && <Button size="sm" variant="ghost" onClick={onForget}>Lupakan</Button>}
      </div>
    </Card>
  )
}

function EditModal({ device, onClose, onSaved }: { device: Device; onClose: () => void; onSaved: () => void }) {
  const { busy, run } = useAction()
  const [name, setName] = useState(device.device_name)
  const [group, setGroup] = useState(device.group_name ?? '')
  const [tags, setTags] = useState((device.tags ?? []).join(', '))
  const [notes, setNotes] = useState(device.notes ?? '')

  const save = async () => {
    const r = await run('save', () => managerApi.patch(device.device_id, {
      device_name: name.trim(), group_name: group.trim(),
      tags: tags.split(',').map((t) => t.trim()).filter(Boolean), notes,
    }), 'Disimpan.')
    if (r) onSaved()
  }

  return (
    <Modal title="Edit peranti" onClose={onClose} footer={<>
      <Button onClick={onClose}>Batal</Button>
      <Button variant="primary" busy={busy === 'save'} disabled={!name.trim()} onClick={save}>Simpan</Button>
    </>}>
      <div className="space-y-4">
        <Field label="Nama paparan"><input className={inputCls} value={name} maxLength={128} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="Kumpulan" hint="Contoh: Rak A, Akaun TikTok 1"><input className={inputCls} value={group} maxLength={64} onChange={(e) => setGroup(e.target.value)} /></Field>
        <Field label="Tag" hint="Dipisahkan dengan koma"><input className={inputCls} value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
        <Field label="Nota"><textarea className={`${inputCls} h-20 resize-none`} value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} /></Field>
      </div>
    </Modal>
  )
}
