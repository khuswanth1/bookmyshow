import { useState } from 'react'
import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { Button, Chip, Modal } from './ui'

/** Multi-select chips group backed by a list of ids in the URL */
export function ChipGroup({ title, options, selected, onChange, single }) {
  const [open, setOpen] = useState(true)
  const toggle = (id) => {
    const sid = String(id)
    if (single) return onChange(selected[0] === sid ? [] : [sid])
    onChange(selected.includes(sid) ? selected.filter((x) => x !== sid) : [...selected, sid])
  }
  return (
    <fieldset className="border-b border-gray-200 py-3 last:border-0">
      <legend className="sr-only">{title}</legend>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between text-sm font-bold">
        {title}<ChevronDown className={`h-4 w-4 transition ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <div className="mt-2.5 flex flex-wrap gap-2">
          {options.map((o) => <Chip key={o.id} active={selected.includes(String(o.id))} onClick={() => toggle(o.id)}>{o.name}</Chip>)}
        </div>
      )}
    </fieldset>
  )
}

/** Desktop sidebar + mobile "Filters" bottom sheet */
export function FilterShell({ children, activeCount = 0, onClear }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <aside className="card hidden h-fit w-72 shrink-0 p-4 lg:block" aria-label="Filters">
        <div className="mb-1 flex items-center justify-between"><h2 className="font-bold">Filters</h2>
          {activeCount > 0 && <button onClick={onClear} className="text-sm font-semibold text-brand hover:underline">Clear all</button>}</div>
        {children}
      </aside>
      <div className="lg:hidden">
        <Button variant="outline" onClick={() => setOpen(true)}><SlidersHorizontal className="h-4 w-4" />Filters{activeCount > 0 && ` (${activeCount})`}</Button>
        <Modal open={open} onClose={() => setOpen(false)} title="Filters">
          {children}
          <div className="sticky bottom-0 mt-4 flex gap-2 bg-white pt-3">
            <Button variant="outline" className="flex-1" onClick={onClear}>Clear</Button>
            <Button className="flex-1" onClick={() => setOpen(false)}>Show results</Button>
          </div>
        </Modal>
      </div>
    </>
  )
}

export function useUrlFilters(params, setParams) {
  const get = (k) => params.getAll(k)
  const one = (k, d = '') => params.get(k) ?? d
  const set = (k, v) => {
    const next = new URLSearchParams(params)
    next.delete(k)
    ;(Array.isArray(v) ? v : [v]).forEach((x) => { if (x !== '' && x != null && x !== false) next.append(k, x) })
    next.delete('page')
    setParams(next, { replace: true })
  }
  const page = Number(params.get('page') || 1)
  const setPage = (p) => { const n = new URLSearchParams(params); n.set('page', p); setParams(n, { replace: true }); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  return { get, one, set, page, setPage }
}
