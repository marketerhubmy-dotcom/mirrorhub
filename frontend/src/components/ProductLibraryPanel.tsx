import { useState, useEffect } from 'react'
import { productApi } from '../services/productApi'
import type { SavedProduct } from '../types/product'

interface EditState {
  name: string
  shop_name: string
  tiktok_product_name: string
  description: string
  target_audience: string
  default_video_objective: string
  default_video_style: string
  suggested_content_angles: string   // one per line
  key_benefits: string               // one per line
  target_audience_options: string    // one per line
}

function toEditState(p: SavedProduct): EditState {
  return {
    name: p.name,
    shop_name: p.shop_name,
    tiktok_product_name: p.tiktok_product_name,
    description: p.description,
    target_audience: p.target_audience,
    default_video_objective: p.default_video_objective,
    default_video_style: p.default_video_style,
    suggested_content_angles: p.suggested_content_angles.join('\n'),
    key_benefits: p.key_benefits.join('\n'),
    target_audience_options: p.target_audience_options.join('\n'),
  }
}

interface Props {
  selectedId: number | null
  onSelect: (product: SavedProduct) => void
  onAddNew: () => void
  refreshKey?: number
}

export default function ProductLibraryPanel({ selectedId, onSelect, onAddNew, refreshKey = 0 }: Props) {
  const [products, setProducts] = useState<SavedProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [editProduct, setEditProduct] = useState<SavedProduct | null>(null)
  const [editState, setEditState] = useState<EditState | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [refreshingId, setRefreshingId] = useState<number | null>(null)
  const [refreshMsg, setRefreshMsg] = useState('')

  const load = async () => {
    try {
      const list = await productApi.list()
      setProducts(list)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [refreshKey])

  const filtered = search.trim()
    ? products.filter(p =>
        p.name.toLowerCase().includes(search.toLowerCase()) ||
        (p.shop_name || '').toLowerCase().includes(search.toLowerCase())
      )
    : products

  const recent = products.slice(0, 5)

  const openEdit = (p: SavedProduct) => {
    setEditProduct(p)
    setEditState(toEditState(p))
  }

  const saveEdit = async () => {
    if (!editProduct || !editState) return
    setSavingEdit(true)
    try {
      const updated = await productApi.update(editProduct.id, {
        name: editState.name.trim(),
        shop_name: editState.shop_name,
        tiktok_product_name: editState.tiktok_product_name,
        description: editState.description,
        target_audience: editState.target_audience,
        default_video_objective: editState.default_video_objective,
        default_video_style: editState.default_video_style,
        suggested_content_angles: editState.suggested_content_angles.split('\n').map(s => s.trim()).filter(Boolean),
        key_benefits: editState.key_benefits.split('\n').map(s => s.trim()).filter(Boolean),
        target_audience_options: editState.target_audience_options.split('\n').map(s => s.trim()).filter(Boolean),
      })
      setProducts(prev => prev.map(p => (p.id === updated.id ? updated : p)))
      setEditProduct(null)
      setEditState(null)
    } catch (e) {
      alert('Gagal kemaskini: ' + (e as Error).message)
    } finally {
      setSavingEdit(false)
    }
  }

  const deleteProduct = async (id: number) => {
    setDeletingId(id)
    try {
      await productApi.delete(id)
      setProducts(prev => prev.filter(p => p.id !== id))
    } catch (e) {
      alert('Gagal hapus: ' + (e as Error).message)
    } finally {
      setDeletingId(null)
    }
  }

  const refreshProduct = async (p: SavedProduct) => {
    setRefreshingId(p.id)
    setRefreshMsg('')
    try {
      const result = await productApi.refresh(p.id)
      if (result.has_changes) {
        const changes = Object.entries(result.diff)
          .map(([f, v]) => `${f}: "${v.old}" → "${v.new}"`)
          .join('; ')
        setRefreshMsg(`Perubahan ditemui: ${changes}`)
      } else {
        setRefreshMsg('Tiada perubahan.')
      }
      await load()
    } catch (e) {
      setRefreshMsg('Refresh gagal: ' + (e as Error).message)
    } finally {
      setRefreshingId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-400 text-sm">
        Memuatkan library...
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Search + Add */}
      <div className="flex gap-2">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Cari produk..."
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none
            focus:ring-2 focus:ring-violet-500 bg-white"
        />
        <button
          onClick={onAddNew}
          className="px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg
            hover:bg-violet-700 shrink-0"
        >
          + Add New
        </button>
      </div>

      {refreshMsg && (
        <p className="text-xs text-indigo-700 bg-indigo-50 rounded-lg px-3 py-2">{refreshMsg}</p>
      )}

      {/* Empty state */}
      {products.length === 0 && (
        <div className="text-center py-16 space-y-3">
          <div className="text-5xl">🛍️</div>
          <p className="text-gray-600 font-medium">Library produk kosong</p>
          <p className="text-sm text-gray-400">
            Tambah produk pertama anda dari TikTok Shop,<br />
            teks, atau screenshot.
          </p>
          <button
            onClick={onAddNew}
            className="mt-2 px-5 py-2.5 bg-violet-600 text-white text-sm font-semibold
              rounded-xl hover:bg-violet-700"
          >
            + Tambah Produk Pertama
          </button>
        </div>
      )}

      {/* Recent - only when not searching and total > 5 */}
      {!search.trim() && products.length > 5 && (
        <div>
          <p className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">Terkini</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {recent.map(p => (
              <button
                key={p.id}
                onClick={() => onSelect(p)}
                className={`shrink-0 flex items-center gap-2 px-3 py-2 rounded-lg border text-left
                  transition-colors ${selectedId === p.id
                    ? 'bg-violet-50 border-violet-400 text-violet-700'
                    : 'bg-white border-gray-200 hover:border-gray-300 text-gray-700'
                  }`}
              >
                {p.image_filename ? (
                  <img
                    src={`/uploads/${p.image_filename}`}
                    className="w-8 h-8 rounded object-cover shrink-0"
                    alt=""
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                ) : (
                  <div className="w-8 h-8 rounded bg-violet-100 flex items-center justify-center
                    text-violet-500 text-xs shrink-0">🛍️</div>
                )}
                <span className="text-xs font-medium max-w-[100px] truncate">{p.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Product grid */}
      {filtered.length > 0 && (
        <div className="space-y-2">
          {!search.trim() && products.length > 5 && (
            <p className="text-xs font-bold text-gray-400 uppercase tracking-wide">Semua Produk</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {filtered.map(p => (
              <ProductCard
                key={p.id}
                product={p}
                selected={selectedId === p.id}
                deleting={deletingId === p.id}
                refreshing={refreshingId === p.id}
                onSelect={() => onSelect(p)}
                onEdit={() => openEdit(p)}
                onDelete={() => {
                  if (window.confirm(`Padam "${p.name}"?`)) deleteProduct(p.id)
                }}
                onRefresh={() => refreshProduct(p)}
              />
            ))}
          </div>
        </div>
      )}

      {search.trim() && filtered.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-8">
          Tiada produk sepadan dengan "{search}"
        </p>
      )}

      {/* Edit Modal */}
      {editProduct && editState && (
        <EditModal
          product={editProduct}
          state={editState}
          saving={savingEdit}
          onChange={patch => setEditState(prev => prev ? { ...prev, ...patch } : prev)}
          onSave={saveEdit}
          onClose={() => { setEditProduct(null); setEditState(null) }}
        />
      )}
    </div>
  )
}

// ── ProductCard ────────────────────────────────────────────────────────────────

function ProductCard({
  product: p, selected, deleting, refreshing,
  onSelect, onEdit, onDelete, onRefresh,
}: {
  product: SavedProduct
  selected: boolean
  deleting: boolean
  refreshing: boolean
  onSelect: () => void
  onEdit: () => void
  onDelete: () => void
  onRefresh: () => void
}) {
  return (
    <div className={`rounded-xl border p-3 transition-all ${
      selected ? 'border-violet-400 bg-violet-50' : 'border-gray-200 bg-white hover:border-gray-300'
    }`}>
      <div className="flex gap-3">
        {/* Image */}
        {p.image_filename ? (
          <img
            src={`/uploads/${p.image_filename}`}
            alt=""
            className="w-12 h-12 rounded-lg object-cover shrink-0 border border-gray-100"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="w-12 h-12 rounded-lg bg-violet-100 flex items-center justify-center
            text-violet-500 text-xl shrink-0">🛍️</div>
        )}

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-gray-900 text-sm truncate">{p.name}</p>
          {p.shop_name && (
            <p className="text-xs text-gray-400 truncate">{p.shop_name}</p>
          )}
          {p.tiktok_product_name && (
            <p className="text-xs text-indigo-600 truncate mt-0.5">
              🛍 {p.tiktok_product_name}
            </p>
          )}
          {p.suggested_content_angles.length > 0 && (
            <p className="text-xs text-gray-400 mt-0.5">
              {p.suggested_content_angles.length} angle{p.suggested_content_angles.length > 1 ? 's' : ''}
            </p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-1.5 mt-3">
        <button
          onClick={onSelect}
          className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
            selected
              ? 'bg-violet-600 text-white'
              : 'bg-violet-50 text-violet-700 hover:bg-violet-100 border border-violet-200'
          }`}
        >
          {selected ? '✓ Dipilih' : 'Pilih'}
        </button>
        <button
          onClick={onEdit}
          className="px-2.5 py-1.5 text-xs text-gray-500 hover:text-gray-700 rounded-lg
            hover:bg-gray-100 border border-gray-200"
          title="Edit"
        >
          ✏
        </button>
        {p.url.startsWith('http') && (
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="px-2.5 py-1.5 text-xs text-gray-500 hover:text-gray-700 rounded-lg
              hover:bg-gray-100 border border-gray-200 disabled:opacity-40"
            title="Refresh dari URL"
          >
            {refreshing ? '⏳' : '↻'}
          </button>
        )}
        <button
          onClick={onDelete}
          disabled={deleting}
          className="px-2.5 py-1.5 text-xs text-red-400 hover:text-red-600 rounded-lg
            hover:bg-red-50 border border-gray-200 disabled:opacity-40"
          title="Padam"
        >
          {deleting ? '⏳' : '✕'}
        </button>
      </div>
    </div>
  )
}

// ── EditModal ─────────────────────────────────────────────────────────────────

function EditModal({
  state, saving, onChange, onSave, onClose,
}: {
  product: SavedProduct
  state: EditState
  saving: boolean
  onChange: (patch: Partial<EditState>) => void
  onSave: () => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <p className="font-bold text-gray-900">Edit Produk</p>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-lg">✕</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <Field label="Nama Produk">
            <input
              value={state.name}
              onChange={e => onChange({ name: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Nama Kedai">
            <input
              value={state.shop_name}
              onChange={e => onChange({ shop_name: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Nama Produk TikTok Shop">
            <input
              value={state.tiktok_product_name}
              onChange={e => onChange({ tiktok_product_name: e.target.value })}
              className={inputCls}
              placeholder="Nama tepat untuk carian dalam TikTok Shop"
            />
          </Field>
          <Field label="Deskripsi">
            <textarea
              value={state.description}
              onChange={e => onChange({ description: e.target.value })}
              rows={3}
              className={inputCls + ' resize-none'}
            />
          </Field>
          <Field label="Target Audiens">
            <input
              value={state.target_audience}
              onChange={e => onChange({ target_audience: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Pilihan Audiens (satu per baris)">
            <textarea
              value={state.target_audience_options}
              onChange={e => onChange({ target_audience_options: e.target.value })}
              rows={3}
              className={inputCls + ' resize-none font-mono text-xs'}
              placeholder="Wanita 25-34&#10;Ibu muda&#10;Remaja 18-24"
            />
          </Field>
          <Field label="Video Objective Default">
            <input
              value={state.default_video_objective}
              onChange={e => onChange({ default_video_objective: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Gaya Visual Default">
            <input
              value={state.default_video_style}
              onChange={e => onChange({ default_video_style: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Content Angles (satu per baris)">
            <textarea
              value={state.suggested_content_angles}
              onChange={e => onChange({ suggested_content_angles: e.target.value })}
              rows={4}
              className={inputCls + ' resize-none font-mono text-xs'}
              placeholder="Cara guna produk step-by-step&#10;Perbandingan sebelum dan selepas"
            />
          </Field>
          <Field label="Faedah Utama (satu per baris)">
            <textarea
              value={state.key_benefits}
              onChange={e => onChange({ key_benefits: e.target.value })}
              rows={3}
              className={inputCls + ' resize-none font-mono text-xs'}
            />
          </Field>
        </div>

        {/* Footer */}
        <div className="flex gap-2 px-5 py-4 border-t border-gray-200">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600
              hover:bg-gray-50"
          >
            Batal
          </button>
          <button
            onClick={onSave}
            disabled={saving || !state.name.trim()}
            className="flex-1 py-2.5 bg-violet-600 text-white rounded-xl text-sm font-semibold
              hover:bg-violet-700 disabled:opacity-40"
          >
            {saving ? 'Menyimpan...' : 'Simpan'}
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-500 mb-1">{label}</p>
      {children}
    </div>
  )
}

const inputCls = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-violet-500 bg-white'
