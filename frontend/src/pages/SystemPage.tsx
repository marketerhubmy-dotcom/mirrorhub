import { useCallback, useEffect, useState } from 'react'
import { Page } from '../components/AppShell'
import { Button, Card, ConfirmDialog, PageHeader, Pill, useAction } from '../components/ui'
import { fmtBytes, systemApi2, type BackupInfo, type DiagCheck } from '../services/deviceApi'

const TONE: Record<string, string> = {
  PASS: 'text-emerald-400', WARN: 'text-amber-300', FAIL: 'text-red-400', INFO: 'text-sky-300',
}

export default function SystemPage() {
  const { busy, run } = useAction()
  const [diag, setDiag] = useState<{ overall: string; checks: DiagCheck[] } | null>(null)
  const [data, setData] = useState<{ data_dir: string; database: string; backups: BackupInfo[] } | null>(null)
  const [restore, setRestore] = useState<string | null>(null)
  const [staged, setStaged] = useState('')

  const loadData = useCallback(async () => { const r = await run('data', () => systemApi2.data()); if (r) setData(r) }, [run])
  const runDiag = useCallback(async () => { const r = await run('diag', () => systemApi2.diagnostics()); if (r) setDiag(r) }, [run])
  useEffect(() => { runDiag(); loadData() }, [runDiag, loadData])

  return (
    <Page>
      <PageHeader title="Sistem" subtitle="Diagnostik persekitaran, lokasi data pengguna, backup dan pemulihan." />

      <Card className="p-5 mb-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-white">Diagnostik</h2>
            {diag && <Pill tone={diag.overall === 'PASS' ? 'brand' : 'warn'}>{diag.overall}</Pill>}
          </div>
          <Button busy={busy === 'diag'} onClick={runDiag}>Jalankan semula</Button>
        </div>
        <div className="divide-y divide-ink-700">
          {diag?.checks.map((c) => (
            <div key={c.id} className="py-2.5 grid grid-cols-[4.5rem_1fr] gap-x-3">
              <span className={`text-xs font-bold ${TONE[c.status]}`}>{c.status}</span>
              <div className="min-w-0">
                <p className="text-sm text-gray-100">{c.title}</p>
                {c.detail && <p className="text-xs text-gray-400 break-all">{c.detail}</p>}
                {c.hint && c.status !== 'PASS' && <p className="text-xs text-amber-300/90 mt-0.5">→ {c.hint}</p>}
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-3">Diagnostik mengesahkan persekitaran sahaja. Ia tidak membuktikan setiap model telefon berfungsi — lihat checklist pengesahan perkakasan dalam dokumentasi.</p>
      </Card>

      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-white">Data & backup</h2>
          <Button variant="primary" busy={busy === 'bk'} onClick={async () => { await run('bk', () => systemApi2.backup(), (r) => `Backup dicipta: ${r.name}`); loadData() }}>Cipta backup</Button>
        </div>
        {data && (
          <div className="text-xs text-gray-400 space-y-1 mb-4">
            <p>Folder data: <span className="font-mono text-gray-300 break-all">{data.data_dir}</span></p>
            <p>Pangkalan data: <span className="font-mono text-gray-300 break-all">{data.database}</span></p>
          </div>
        )}
        {staged && <p className="text-sm text-amber-300 bg-amber-500/10 rounded-lg px-3 py-2 mb-3">{staged}</p>}
        {data?.backups.length === 0 && <p className="text-sm text-gray-500">Belum ada backup.</p>}
        <div className="divide-y divide-ink-700">
          {data?.backups.map((b) => (
            <div key={b.name} className="flex flex-wrap items-center gap-3 py-2.5">
              <span className="font-mono text-xs text-gray-200 break-all mr-auto">{b.name}</span>
              <span className="text-xs text-gray-500">{fmtBytes(b.size)} · {b.created.replace('T', ' ')}</span>
              <Button size="sm" onClick={() => setRestore(b.name)}>Pulihkan…</Button>
            </div>
          ))}
        </div>
      </Card>

      {restore && (
        <ConfirmDialog danger title="Pulihkan daripada backup?" confirmLabel="Jadualkan pemulihan"
          message={<>Pangkalan data akan digantikan dengan <span className="font-mono break-all">{restore}</span> apabila Mirrorhub dibuka semula.
            Backup keselamatan bagi keadaan semasa dicipta secara automatik sebelum penggantian, jadi ia boleh dikembalikan.</>}
          onCancel={() => setRestore(null)}
          onConfirm={async () => {
            const n = restore; setRestore(null)
            const r = await run('rs', () => systemApi2.restore(n))
            if (r) setStaged(r.message)
          }} />
      )}
    </Page>
  )
}
