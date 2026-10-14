import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../../lib/api'
import { useToast } from '../../context/providers'
import { useDebounce, useTitle } from '../../hooks'
import { DataTable } from '../../components/portal'
import { Button, ErrorState, Input, Modal, PageSpinner, Pagination, Select, Textarea, Toggle } from '../../components/ui'
import { slugify } from './resources.jsx'

/** Extra option sources used by config `options: 'cities' | 'genres' | ...` */
const SOURCES = { cities: '/cities', genres: '/genres', languages: '/languages' }
function useOptions(source) {
  return useQuery({ queryKey: ['opt', source], enabled: !!source, queryFn: () => api.get(SOURCES[source]), staleTime: 300_000 })
}

function FieldInput({ f, value, onChange, error }) {
  const opts = useOptions(typeof f.options === 'string' ? f.options : null)
  const common = { label: f.label, error, hint: f.hint, id: `field-${f.key}`, name: f.key }
  switch (f.type) {
    case 'textarea': return <Textarea {...common} rows={3} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    case 'number': return <Input {...common} type="number" step="any" value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    case 'paise': return <Input {...common} type="number" min="0" step="0.01" value={value ?? ''} onChange={(e) => onChange(e.target.value)} hint={f.hint || 'Amount in ₹'} />
    case 'date': return <Input {...common} type="date" value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    case 'datetime': return <Input {...common} type="datetime-local" value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
    case 'color': return <Input {...common} type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)} />
    case 'checkbox': return <div className="pt-6"><Toggle checked={!!value} onChange={onChange} label={f.label} /></div>
    case 'select': {
      const list = Array.isArray(f.options) ? f.options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o)) : (opts.data || []).map((o) => ({ value: o.id, label: o.name }))
      return <Select {...common} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>{f.optional && <option value="">None</option>}{list.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</Select>
    }
    case 'multiselect':
      return (
        <fieldset><legend className="mb-1 text-sm font-medium">{f.label}</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1">{(opts.data || []).map((o) => (
            <label key={o.id} className="flex items-center gap-1.5 text-sm"><input type="checkbox" className="accent-[#f84464]" checked={(value || []).includes(o.id)}
              onChange={(e) => onChange(e.target.checked ? [...(value || []), o.id] : (value || []).filter((x) => x !== o.id))} />{o.name}</label>
          ))}</div></fieldset>
      )
    default: return <Input {...common} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
  }
}

const initialOf = (fields, rec) => {
  const out = {}
  for (const f of fields) {
    let v = rec ? (f.fromRecord ? f.fromRecord(rec) : rec[f.key]) : f.default
    if (v === undefined || v === null) v = f.type === 'checkbox' ? false : f.type === 'multiselect' ? [] : ''
    if (f.type === 'paise' && rec && v !== '') v = v / 100
    if (f.type === 'datetime' && v) { const d = new Date(v); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); v = d.toISOString().slice(0, 16) }
    if (f.type === 'tags') v = Array.isArray(v) ? v.join(', ') : v
    if (f.type === 'pairs') v = (v || []).map((p) => `${p.name} | ${p.role || ''}`).join('\n')
    out[f.key] = v
  }
  return out
}
const payloadOf = (fields, v) => {
  const out = {}
  for (const f of fields) {
    let x = v[f.key]
    if (f.type === 'number' || (f.type === 'select' && f.numeric)) {
      x = (x === '' || x == null) ? ((f.key === 'lat' || f.key === 'lng' || f.key === 'rating_avg') ? 0 : null) : Number(x)
    }
    else if (f.type === 'paise') x = x === '' || x == null ? null : Math.round(Number(x) * 100)
    else if (f.type === 'datetime') x = x ? new Date(x).toISOString() : null
    else if (f.type === 'date') x = x || null
    else if (f.type === 'tags') x = String(x).split(',').map((s) => s.trim()).filter(Boolean)
    else if (f.type === 'pairs') x = String(x).split('\n').map((l) => l.trim()).filter(Boolean).map((l) => { const [name, role] = l.split('|').map((s) => s.trim()); return { name, role: role || '' } })
    else if (x === '' && f.optional) x = null
    out[f.key] = x
  }
  return out
}

export default function ResourceManager({ cfg }) {
  useTitle(`Admin: ${cfg.title}`)
  const qc = useQueryClient()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const dq = useDebounce(q, 300)
  const [editing, setEditing] = useState(null) // null | 'new' | record
  const [v, setV] = useState({})
  const [errs, setErrs] = useState({})
  const key = ['admin', cfg.path, page, dq]
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: key, queryFn: () => api.get(`/admin/${cfg.path}`, { page, size: 15, q: dq || undefined }), placeholderData: (p) => p })

  const handleClose = useCallback(() => setEditing(null), [])
  const open = useCallback((rec) => { setEditing(rec || 'new'); setV(initialOf(cfg.fields, rec || null)); setErrs({}) }, [cfg.fields])
  // /admin/<path>?new=1 (dashboard shortcut) opens the create form straight away
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    if (params.get('new') === '1') { open(); setParams({}, { replace: true }) }
  }, [params, open, setParams])
  const save = useMutation({
    mutationFn: (body) => (editing === 'new' ? api.post(`/admin/${cfg.path}`, body) : api.patch(`/admin/${cfg.path}/${editing.id}`, body)),
    onSuccess: () => { toast.success('Saved'); setEditing(null); qc.invalidateQueries({ queryKey: ['admin', cfg.path] }); qc.invalidateQueries({ queryKey: ['opt'] }) },
    onError: (e) => { setErrs(e.fieldErrors || {}); toast.error(Object.keys(e.fieldErrors || {}).length ? 'Please fix the highlighted fields' : e.message) },
  })
  const del = useMutation({
    mutationFn: (id) => api.del(`/admin/${cfg.path}/${id}`),
    onSuccess: () => { toast.success('Deleted'); qc.invalidateQueries({ queryKey: ['admin', cfg.path] }) }, onError: (e) => toast.error(e.message),
  })
  const submit = (e) => {
    e.preventDefault()
    const er = {}
    for (const f of cfg.fields) if (f.required && (v[f.key] === '' || v[f.key] == null)) er[f.key] = `${f.label} is required`
    setErrs(er)
    if (Object.keys(er).length) return
    save.mutate(payloadOf(cfg.fields, v))
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">{cfg.title}</h1>
        <div className="flex gap-2"><Input aria-label={`Search ${cfg.title}`} type="search" placeholder="Search…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="w-48" />
          <Button onClick={() => open()}><Plus className="h-4 w-4" />Add</Button></div></div>
      {isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? <PageSpinner /> : (
        <>
          <DataTable caption={cfg.title} rows={data.items} empty={`No ${cfg.title.toLowerCase()} found.`} columns={[
            ...cfg.columns.map((c) => (typeof c === 'string' ? { header: c, key: c } : c)),
            { header: '', render: (r) => <div className="flex gap-1"><Button size="sm" variant="ghost" aria-label="Edit" onClick={() => open(r)}><Pencil className="h-4 w-4" /></Button>
              <Button size="sm" variant="ghost" aria-label="Delete" onClick={() => window.confirm(`Delete this item?`) && del.mutate(r.id)}><Trash2 className="h-4 w-4 text-red-600" /></Button></div> }]} />
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
      <Modal open={!!editing} onClose={handleClose} title={editing === 'new' ? `Add ${cfg.singular}` : `Edit ${cfg.singular}`} wide>
        <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
          {cfg.fields.map((f) => (
            <div key={f.key} className={['textarea', 'multiselect', 'pairs'].includes(f.type) || f.wide ? 'sm:col-span-2' : ''}>
              <FieldInput
                f={f.type === 'pairs' ? { ...f, type: 'textarea', hint: 'One per line: Name | Role' } : f.type === 'tags' ? { ...f, type: 'text', hint: 'Comma separated' } : f}
                value={v[f.key]}
                error={errs[f.key]}
                onChange={(x) => {
                  setV((prev) => {
                    const next = { ...prev, [f.key]: x }
                    if (f.key === 'name' && cfg.fields.some((item) => item.key === 'slug') && editing === 'new') {
                      const prevSlug = prev.slug || ''
                      const prevExpected = slugify(prev.name || '')
                      if (!prevSlug || prevSlug === prevExpected) {
                        next.slug = slugify(x)
                      }
                    }
                    return next
                  })
                  setErrs((prev) => {
                    if (!prev[f.key] && !(f.key === 'name' && prev.slug)) return prev
                    const nextErrs = { ...prev, [f.key]: '' }
                    if (f.key === 'name' && nextErrs.slug) nextErrs.slug = ''
                    return nextErrs
                  })
                }}
              />
            </div>
          ))}
          <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" variant="outline" onClick={handleClose}>Cancel</Button><Button loading={save.isPending}>Save</Button></div>
        </form>
      </Modal>
    </div>
  )
}
