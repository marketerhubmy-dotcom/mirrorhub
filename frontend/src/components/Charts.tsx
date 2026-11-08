import { useId, useMemo, useRef, useState } from 'react'

export interface Series { key: string; label: string; color: string; unit?: string; dashed?: boolean }

interface Row { t: number; [k: string]: number | null | undefined }

const W = 560
const H = 150
const PAD = { l: 34, r: 8, t: 8, b: 20 }

function fmtClock(t: number, span: number): string {
  const d = new Date(t * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return span > 3 * 3600 ? `${p(d.getHours())}:${p(d.getMinutes())}` : `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** Line chart with null gaps (N/A is a gap, never a fake zero), hover crosshair and a text fallback for screen readers. */
export function LineChart({ title, rows, series, yMax, yUnit = '', fixedMax, loading, empty }: {
  title: string; rows: Row[]; series: Series[]; yMax?: number; yUnit?: string; fixedMax?: boolean; loading?: boolean; empty?: string
}) {
  const id = useId()
  const [hover, setHover] = useState<number | null>(null)
  const ref = useRef<SVGSVGElement>(null)

  const geo = useMemo(() => {
    if (rows.length < 2) return null
    const t0 = rows[0].t, t1 = rows[rows.length - 1].t
    let max = yMax ?? 0
    if (!fixedMax) for (const r of rows) for (const s of series) { const v = r[s.key]; if (typeof v === 'number' && v > max) max = v }
    max = fixedMax && yMax ? yMax : niceMax(Math.max(max, yMax ? 0 : 1))
    const x = (t: number) => PAD.l + ((t - t0) / Math.max(1e-9, t1 - t0)) * (W - PAD.l - PAD.r)
    const y = (v: number) => PAD.t + (1 - Math.min(v, max) / max) * (H - PAD.t - PAD.b)
    const paths = series.map((s) => {
      let d = '', pen = false
      for (const r of rows) {
        const v = r[s.key]
        if (typeof v !== 'number') { pen = false; continue }
        d += `${pen ? 'L' : 'M'}${x(r.t).toFixed(1)},${y(v).toFixed(1)}`
        pen = true
      }
      return d
    })
    return { t0, t1, max, x, y, paths }
  }, [rows, series, yMax, fixedMax])

  const hasData = !!geo && series.some((s) => rows.some((r) => typeof r[s.key] === 'number'))
  const hv = hover !== null && geo ? rows[hover] : null

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!geo || !ref.current) return
    const box = ref.current.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W
    const t = geo.t0 + ((px - PAD.l) / (W - PAD.l - PAD.r)) * (geo.t1 - geo.t0)
    let lo = 0, hi = rows.length - 1
    while (lo < hi) { const m = (lo + hi) >> 1; if (rows[m].t < t) lo = m + 1; else hi = m }
    setHover(Math.max(0, Math.min(rows.length - 1, lo)))
  }

  return (
    <figure className="rounded-2xl border border-ink-700 bg-ink-850 p-4" aria-labelledby={`${id}-t`}>
      <figcaption className="flex items-center justify-between gap-3 mb-2">
        <span id={`${id}-t`} className="text-sm font-medium text-gray-200">{title}</span>
        <span className="flex flex-wrap gap-x-3 gap-y-1 justify-end">
          {series.map((s) => {
            const last = [...rows].reverse().find((r) => typeof r[s.key] === 'number')
            const v = hv ? hv[s.key] : last?.[s.key]
            return (
              <span key={s.key} className="flex items-center gap-1.5 text-[11px] text-gray-400">
                <i className="inline-block w-2.5 h-0.5 rounded" style={{ background: s.color }} />
                {s.label}
                <b className="text-gray-100 tabular-nums">{typeof v === 'number' ? `${round(v)}${s.unit ?? yUnit}` : 'N/A'}</b>
              </span>
            )
          })}
        </span>
      </figcaption>
      <div className="relative">
        {loading && <p className="absolute inset-0 grid place-items-center text-xs text-gray-500">Memuatkan…</p>}
        {!loading && !hasData && <p className="absolute inset-0 grid place-items-center text-xs text-gray-500 text-center px-6">{empty ?? 'Belum ada data untuk tempoh ini.'}</p>}
        <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" role="img" aria-label={`${title}: graf garis`}
          onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          {geo && [0, 0.5, 1].map((f) => {
            const yy = PAD.t + (1 - f) * (H - PAD.t - PAD.b)
            return (
              <g key={f}>
                <line x1={PAD.l} x2={W - PAD.r} y1={yy} y2={yy} stroke="currentColor" className="text-ink-700" strokeDasharray={f === 0 ? undefined : '3 4'} />
                <text x={PAD.l - 5} y={yy + 3} textAnchor="end" className="fill-gray-500" fontSize="9">{round(geo.max * f)}</text>
              </g>
            )
          })}
          {geo && [0, 0.5, 1].map((f) => (
            <text key={f} x={PAD.l + f * (W - PAD.l - PAD.r)} y={H - 5} textAnchor={f === 0 ? 'start' : f === 1 ? 'end' : 'middle'} className="fill-gray-500" fontSize="9">
              {fmtClock(geo.t0 + f * (geo.t1 - geo.t0), geo.t1 - geo.t0)}
            </text>
          ))}
          {geo && series.map((s, i) => (
            <path key={s.key} d={geo.paths[i]} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinejoin="round" strokeDasharray={s.dashed ? '4 3' : undefined} />
          ))}
          {geo && hv && (
            <g>
              <line x1={geo.x(hv.t)} x2={geo.x(hv.t)} y1={PAD.t} y2={H - PAD.b} stroke="currentColor" className="text-gray-500" />
              {series.map((s) => typeof hv[s.key] === 'number' && <circle key={s.key} cx={geo.x(hv.t)} cy={geo.y(hv[s.key] as number)} r="3" fill={s.color} />)}
              <text x={Math.min(Math.max(geo.x(hv.t), PAD.l + 24), W - 30)} y={PAD.t + 8} textAnchor="middle" className="fill-gray-300" fontSize="9">{fmtClock(hv.t, geo.t1 - geo.t0)}</text>
            </g>
          )}
        </svg>
      </div>
    </figure>
  )
}

function round(v: number): string {
  return Math.abs(v) >= 100 ? String(Math.round(v)) : (Math.round(v * 10) / 10).toString()
}

function niceMax(v: number): number {
  if (v <= 1) return 1
  const p = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p
}

/** Horizontal usage bar for cards. */
export function UsageBar({ pct, warnAt = 75, critAt = 90 }: { pct: number | null; warnAt?: number; critAt?: number }) {
  const v = pct ?? 0
  const color = v >= critAt ? 'bg-red-500' : v >= warnAt ? 'bg-amber-400' : 'bg-brand-500'
  return (
    <div className="h-1.5 rounded-full bg-ink-700 overflow-hidden" role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full transition-all duration-500 ${pct === null ? 'opacity-0' : color}`} style={{ width: `${Math.min(100, v)}%` }} />
    </div>
  )
}
