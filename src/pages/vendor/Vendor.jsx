import { useMemo, useState } from 'react'
import { Link, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BarChart3, Building2, CalendarDays, Clapperboard, Download, FileText, Film, Plus, Ticket, Users, Wallet } from 'lucide-react'
import { api, download } from '../../lib/api'
import { useAuth, useToast } from '../../context/providers'
import { useTitle } from '../../hooks'
import { BarChart, DataTable, PortalShell } from '../../components/portal'
import { Badge, Button, EmptyState, ErrorState, Input, Modal, PageSpinner, Pagination, Select, Stat, Textarea, statusTone } from '../../components/ui'
import { clsx, fmtDate, fmtDateTime, inr, ymd } from '../../lib/format'
import { minLen, required, validate } from '../../lib/validators'

const links = [
  ['/vendor', 'Dashboard', BarChart3, true], ['/vendor/theaters', 'Theaters & screens', Building2], ['/vendor/shows', 'Shows & pricing', CalendarDays],
  ['/vendor/bookings', 'Bookings', Ticket], ['/vendor/earnings', 'Earnings & payouts', Wallet], ['/vendor/reports', 'Sales reports', FileText], ['/vendor/movie-requests', 'Movie requests', Film], ['/vendor/staff', 'Staff', Users],
]

const MANAGER_LINKS = [['/vendor/shows', 'Shows & pricing', CalendarDays], ['/vendor/theaters', 'My theaters', Building2]]
const useIsManager = () => useAuth().user?.role === 'manager'

const useProfile = () => useQuery({ queryKey: ['vendor-profile-me'], queryFn: () => api.get('/vendor/profile') })
const useTheaters = () => useQuery({ queryKey: ['vendor-theaters'], queryFn: () => api.get('/vendor/theaters') })

function StatusBanner() {
  const { data: p } = useProfile()
  if (!p || p.status === 'approved') return null
  return (
    <div role="alert" className="mb-4 flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-sm text-amber-900"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
      <div>Your vendor account is <b>{p.status}</b>{p.rejection_reason && <>: {p.rejection_reason}</>}. {p.status === 'suspended' ? 'Your theaters are hidden from customers and changes are disabled.' : 'You can’t create theaters or shows until it is approved.'}</div></div>
  )
}

/* ------------------------------------------------------------------ dashboard */
function Dashboard() {
  useTitle('Vendor dashboard')
  const [days, setDays] = useState(30)
  const [tid, setTid] = useState('')
  const theaters = useTheaters()
  const a = useQuery({ queryKey: ['vendor-analytics', days, tid], queryFn: () => api.get('/vendor/analytics', { days, theater_id: tid || undefined }) })
  const e = useQuery({ queryKey: ['vendor-earnings'], queryFn: () => api.get('/vendor/earnings') })
  if (a.isLoading || e.isLoading) return <PageSpinner />
  if (a.isError) return <ErrorState error={a.error} retry={a.refetch} />
  const d = a.data, en = e.data
  return (
    <div className="space-y-5"><StatusBanner />
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex gap-2"><Select aria-label="Theater" value={tid} onChange={(x) => setTid(x.target.value)} className="w-52"><option value="">All theaters</option>{theaters.data?.filter((t) => t.approval_status === 'approved').map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
          <Select aria-label="Period" value={days} onChange={(x) => setDays(Number(x.target.value))} className="w-36"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></Select></div></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Net earnings" value={inr(d.net_paise)} sub={`Gross ${inr(d.gross_paise)} − commission ${inr(d.commission_paise)}`} /><Stat label="Bookings" value={d.bookings} sub={`${d.tickets} tickets`} />
        <Stat label="Occupancy" value={`${d.occupancy_pct}%`} sub="Shows already screened" /><Stat label="Withdrawable" value={inr(en.available_paise)} sub={`Commission rate ${en.commission_pct}%`} tone="text-emerald-600" /></div>
      <section className="card p-5"><h2 className="mb-3 font-bold">Net earnings by day</h2><BarChart title="Net earnings by day" data={d.daily.map((x) => ({ label: fmtDate(x.date, { day: 'numeric', month: 'short' }), value: x.net_paise / 100 }))} format={(v) => `₹${v.toLocaleString('en-IN')}`} /></section>
      <div className="grid gap-5 lg:grid-cols-2">
        <section><h2 className="mb-2 font-bold">Top movies</h2><DataTable caption="Top movies" rows={d.top_movies} empty="No sales in this period." columns={[{ header: 'Movie', key: 'title' }, { header: 'Bookings', key: 'bookings' }, { header: 'Net', render: (r) => inr(r.net_paise) }]} /></section>
        <section><h2 className="mb-2 font-bold">By theater</h2><DataTable caption="Theaters" rows={d.theaters} empty="No sales in this period." columns={[{ header: 'Theater', key: 'name' }, { header: 'Bookings', key: 'bookings' }, { header: 'Net', render: (r) => inr(r.net_paise) }]} /></section></div>
    </div>
  )
}

/* ------------------------------------------------------------------ theaters */
function TheaterForm({ open, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const cities = useQuery({ queryKey: ['cities'], queryFn: () => api.get('/cities') })
  const blank = { name: '', chain: '', city_id: '', address: '', lat: '', lng: '', amenities: '' }
  const [v, setV] = useState(blank)
  const [errs, setErrs] = useState({})
  const m = useMutation({
    mutationFn: (b) => api.post('/vendor/theaters', b),
    onSuccess: () => { toast.success('Submitted for admin approval'); setV(blank); onClose(); qc.invalidateQueries({ queryKey: ['vendor-theaters'] }) },
    onError: (e) => { setErrs(e.fieldErrors); if (!Object.keys(e.fieldErrors).length) toast.error(e.message) },
  })
  const submit = (e) => {
    e.preventDefault()
    const er = validate({ name: [minLen(2, 'Name')], city_id: [required('City')], address: [minLen(3, 'Address')] }, v)
    setErrs(er)
    if (!Object.keys(er).length) m.mutate({ name: v.name.trim(), chain: v.chain || null, city_id: Number(v.city_id), address: v.address.trim(), lat: v.lat === '' ? null : Number(v.lat), lng: v.lng === '' ? null : Number(v.lng), amenities: v.amenities.split(',').map((x) => x.trim()).filter(Boolean) })
  }
  const set = (k) => (e) => { setV({ ...v, [k]: e.target.value }); setErrs({ ...errs, [k]: '' }) }
  return (
    <Modal open={open} onClose={onClose} title="Submit a theater for approval"><form onSubmit={submit} noValidate className="space-y-4">
      <Input label="Theater name" value={v.name} onChange={set('name')} error={errs.name} />
      <div className="grid gap-4 sm:grid-cols-2"><Select label="City" value={v.city_id} onChange={set('city_id')} error={errs.city_id}><option value="">Select…</option>{cities.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select><Input label="Brand / chain (optional)" value={v.chain} onChange={set('chain')} /></div>
      <Input label="Address" value={v.address} onChange={set('address')} error={errs.address} />
      <div className="grid grid-cols-2 gap-4"><Input label="Latitude" type="number" step="any" value={v.lat} onChange={set('lat')} error={errs.lat} /><Input label="Longitude" type="number" step="any" value={v.lng} onChange={set('lng')} error={errs.lng} /></div>
      <Input label="Amenities (comma separated)" value={v.amenities} onChange={set('amenities')} placeholder="Dolby Atmos, Recliners, Parking" />
      <p className="text-xs text-gray-500">The theater stays hidden from customers until the super admin approves it.</p>
      <Button loading={m.isPending}>Submit for approval</Button></form></Modal>
  )
}

function Theaters() {
  useTitle('Theaters')
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, isError, error, refetch } = useTheaters()
  const isManager = useIsManager()
  const [open, setOpen] = useState(false)
  const resub = useMutation({ mutationFn: (id) => api.post(`/vendor/theaters/${id}/resubmit`), onSuccess: () => { toast.success('Resubmitted'); qc.invalidateQueries({ queryKey: ['vendor-theaters'] }) }, onError: (e) => toast.error(e.message) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <div className="space-y-4"><StatusBanner />
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">{isManager ? 'My theaters' : 'Theaters'}</h1>{!isManager && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add theater</Button>}</div>
      {data.length === 0 ? <EmptyState icon={Building2} title="No theaters yet" text="Submit your first theater. Once approved you can add screens and shows." /> : (
        <ul className="grid gap-4 md:grid-cols-2">{data.map((t) => (
          <li key={t.id} className="card p-4"><div className="flex items-start justify-between gap-2"><div><h2 className="font-bold">{t.name}</h2><p className="text-sm text-gray-500">{t.address}, {t.city.name}</p></div><Badge tone={statusTone(t.approval_status)}>{t.approval_status}</Badge></div>
            {t.rejection_reason && <p className="mt-2 rounded-lg bg-red-50 p-2 text-sm text-red-700">{t.approval_status === 'suspended' ? 'Suspended' : 'Rejected'}: {t.rejection_reason}</p>}
            {t.approval_status === 'pending' && <p className="mt-2 text-sm text-amber-700">Awaiting admin approval since {fmtDate(t.submitted_at)}.</p>}
            <div className="mt-3 flex items-center gap-2 text-sm text-gray-600"><Clapperboard className="h-4 w-4" />{t.screens_count} screen{t.screens_count === 1 ? '' : 's'}</div>
            <div className="mt-3 flex gap-2">{t.approval_status === 'approved' && <Link to={`/vendor/theaters/${t.id}`}><Button size="sm">{isManager ? 'Seats & screens' : 'Manage screens'}</Button></Link>}
              {t.approval_status === 'rejected' && !isManager && <Button size="sm" variant="outline" loading={resub.isPending} onClick={() => resub.mutate(t.id)}>Resubmit</Button>}</div></li>
        ))}</ul>)}
      <TheaterForm open={open} onClose={() => setOpen(false)} />
    </div>
  )
}

/* ------------------------------------------------------------------ screens + seat editor */
const blankRow = (i, prev) => ({ label: String.fromCharCode(65 + i), category: prev?.category || 'Silver', seats: prev?.seats || 10, aisles: prev?.aisles || '5' })

function ScreenForm({ theaterId, screen, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [v, setV] = useState(() => screen
    ? { name: screen.name, status: screen.status, rows: screen.layout.rows.map((r) => ({ ...r, aisles: (r.aisles || []).join(',') })) }
    : { name: '', status: 'active', rows: [{ label: 'A', category: 'Platinum', seats: 8, aisles: '4' }, { label: 'B', category: 'Gold', seats: 12, aisles: '4,8' }, { label: 'C', category: 'Silver', seats: 12, aisles: '4,8' }] })
  const m = useMutation({
    mutationFn: (b) => (screen ? api.put(`/vendor/screens/${screen.id}`, b) : api.post(`/vendor/theaters/${theaterId}/screens`, b)),
    onSuccess: () => { toast.success('Screen saved'); onClose(); qc.invalidateQueries({ queryKey: ['vendor-screens'] }) }, onError: (e) => toast.error(e.message),
  })
  const setRow = (i, k, val) => setV({ ...v, rows: v.rows.map((r, j) => (j === i ? { ...r, [k]: val } : r)) })
  const total = v.rows.reduce((a, r) => a + (Number(r.seats) || 0), 0)
  const submit = (e) => {
    e.preventDefault()
    if (!v.name.trim()) return toast.error('Screen name is required')
    if (v.rows.some((r) => !r.label.trim() || !r.category.trim() || !(Number(r.seats) >= 1))) return toast.error('Every row needs a label, category and seat count')
    m.mutate({ name: v.name.trim(), status: v.status, layout: { rows: v.rows.map((r) => ({ label: r.label.trim(), category: r.category.trim(), seats: Number(r.seats), aisles: String(r.aisles).split(',').map((x) => Number(x.trim())).filter(Boolean) })) } })
  }
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2"><Input label="Screen name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} /><Select label="Status" value={v.status} onChange={(e) => setV({ ...v, status: e.target.value })}><option value="active">Active</option><option value="maintenance">Under maintenance (no new shows)</option></Select></div>
      <p className="text-xs text-gray-500">Seat categories are free text (e.g. Silver, Gold, Platinum). Seats that are booked or held in a show can't be removed or moved to another category. Aisle gaps are placed after the listed seat numbers.</p>
      {v.rows.map((r, i) => (
        <div key={i} className="grid items-end gap-2 sm:grid-cols-[4rem_1fr_6rem_8rem_auto]">
          <Input label={i === 0 ? 'Row' : undefined} aria-label="Row label" maxLength={3} value={r.label} onChange={(e) => setRow(i, 'label', e.target.value.toUpperCase())} />
          <Input label={i === 0 ? 'Category' : undefined} aria-label="Category" list="seat-cats" value={r.category} onChange={(e) => setRow(i, 'category', e.target.value)} />
          <Input label={i === 0 ? 'Seats' : undefined} aria-label="Seats" type="number" min="1" max="40" value={r.seats} onChange={(e) => setRow(i, 'seats', e.target.value)} />
          <Input label={i === 0 ? 'Aisles after' : undefined} aria-label="Aisles after seat numbers" placeholder="4,8" value={r.aisles} onChange={(e) => setRow(i, 'aisles', e.target.value)} />
          <Button type="button" variant="ghost" aria-label="Remove row" disabled={v.rows.length === 1} onClick={() => setV({ ...v, rows: v.rows.filter((_, j) => j !== i) })}>✕</Button></div>))}
      <datalist id="seat-cats"><option>Silver</option><option>Gold</option><option>Platinum</option><option>Recliner</option></datalist>
      <div className="flex items-center justify-between"><Button type="button" size="sm" variant="outline" onClick={() => setV({ ...v, rows: [...v.rows, blankRow(v.rows.length, v.rows.at(-1))] })}>+ Add row</Button><span className="text-sm text-gray-500">{total} seats</span></div>
      <div className="flex justify-end"><Button loading={m.isPending}>Save screen</Button></div></form>
  )
}

/** Click seats to select; used for maintenance blocking (screen level) and per-show blocking */
function SeatGrid({ seats, selected, onToggle, stateOf }) {
  const rows = useMemo(() => { const m = new Map(); for (const s of seats) { if (!m.has(s.row)) m.set(s.row, []); m.get(s.row).push(s) } return [...m.entries()] }, [seats])
  const tone = { available: 'bg-white ring-1 ring-emerald-500 text-emerald-700', blocked: 'bg-red-200 text-red-800 ring-1 ring-red-300', booked: 'bg-gray-300 text-gray-500 cursor-not-allowed', locked: 'bg-amber-200 text-amber-800 cursor-not-allowed', selected: 'bg-indigo-600 text-white' }
  return (
    <div className="overflow-x-auto"><div className="mx-auto flex w-max flex-col gap-1.5">
      {rows.map(([label, list]) => (
        <div key={label} role="group" aria-label={`Row ${label}`} className="flex items-center gap-1.5"><span className="w-5 text-xs font-semibold text-gray-400">{label}</span>
          {list.map((s) => { const st = selected.has(s.id) ? 'selected' : stateOf(s); return (
            <button key={s.id} type="button" disabled={st === 'booked' || st === 'locked'} onClick={() => onToggle(s)} aria-pressed={selected.has(s.id)}
              aria-label={`Row ${s.row} seat ${s.number}, ${s.category}, ${st}`} title={`${s.category}${s.block_reason ? ` · ${s.block_reason}` : ''}`}
              className={clsx('h-7 w-7 rounded-t text-[10px] font-semibold', tone[st])}>{s.number}</button>) })}</div>))}
      <ul className="mt-3 flex flex-wrap justify-center gap-4 text-xs text-gray-500" aria-label="Legend">{[['available', 'Available'], ['blocked', 'Blocked'], ['booked', 'Booked'], ['selected', 'Selected']].map(([k, l]) => <li key={k} className="flex items-center gap-1.5"><span className={clsx('h-3.5 w-3.5 rounded-t', tone[k])} />{l}</li>)}</ul>
    </div></div>
  )
}

function SeatEditor({ screen, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['vendor-seats', screen.id], queryFn: () => api.get(`/vendor/screens/${screen.id}/seats`) })
  const [sel, setSel] = useState(new Set())
  const [reason, setReason] = useState('Maintenance')
  const m = useMutation({
    mutationFn: (blocked) => api.post(`/vendor/screens/${screen.id}/seats/block`, { seat_ids: [...sel], blocked, reason: blocked ? reason : null }),
    onSuccess: (r) => { toast.success(r.message); setSel(new Set()); qc.invalidateQueries({ queryKey: ['vendor-seats', screen.id] }); qc.invalidateQueries({ queryKey: ['vendor-screens'] }) }, onError: (e) => toast.error(e.message),
  })
  if (isLoading) return <PageSpinner />
  const toggle = (s) => setSel((p) => { const n = new Set(p); n.has(s.id) ? n.delete(s.id) : n.add(s.id); return n })
  return (
    <div className="space-y-4"><p className="text-sm text-gray-600">Select seats, then block them (broken seat, maintenance) or unblock. Blocking applies immediately to every upcoming show. Customers see them as unavailable.</p>
      <SeatGrid seats={data} selected={sel} onToggle={toggle} stateOf={(s) => (s.is_blocked ? 'blocked' : 'available')} />
      <div className="flex flex-wrap items-end gap-3"><Input label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} className="w-56" />
        <Button disabled={!sel.size} loading={m.isPending} variant="danger" onClick={() => m.mutate(true)}>Block {sel.size || ''} selected</Button>
        <Button disabled={!sel.size} loading={m.isPending} variant="outline" onClick={() => m.mutate(false)}>Unblock selected</Button></div></div>
  )
}

function TheaterDetail() {
  const { id } = useParams()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState(null) // {screen?}
  const [seatsFor, setSeatsFor] = useState(null)
  const isManager = useIsManager()
  const theaters = useTheaters()
  const t = theaters.data?.find((x) => String(x.id) === id)
  useTitle(t ? `${t.name}: screens` : 'Screens')
  const screens = useQuery({ queryKey: ['vendor-screens', id], queryFn: () => api.get(`/vendor/theaters/${id}/screens`) })
  const del = useMutation({ mutationFn: (sid) => api.del(`/vendor/screens/${sid}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['vendor-screens'] }), onError: (e) => toast.error(e.message) })
  if (screens.isLoading || theaters.isLoading) return <PageSpinner />
  if (!t) return <ErrorState error={{ message: 'Theater not found' }} />
  return (
    <div className="space-y-4"><Link to="/vendor/theaters" className="text-sm font-semibold text-brand">‹ All theaters</Link>
      <div className="flex flex-wrap items-center justify-between gap-2"><div><h1 className="text-2xl font-bold">{t.name}</h1><p className="text-sm text-gray-500">{t.address}, {t.city.name}</p></div>{!isManager && <Button onClick={() => setForm({})}><Plus className="h-4 w-4" />Add screen</Button>}</div>
      <DataTable caption="Screens" rows={screens.data} empty="No screens yet. Add one to start scheduling shows." columns={[
        { header: 'Screen', render: (s) => <b>{s.name}</b> }, { header: 'Layout', render: (s) => s.layout.rows.map((r) => `${r.label}:${r.seats} ${r.category}`).join(' · ') },
        { header: 'Seats', render: (s) => <>{s.seats}{s.blocked > 0 && <span className="ml-1 text-xs text-red-600">({s.blocked} blocked)</span>}</> }, { header: 'Upcoming shows', key: 'upcoming_shows' },
        { header: 'Status', render: (s) => <Badge tone={s.status === 'active' ? 'green' : 'amber'}>{s.status}</Badge> },
        { header: '', render: (s) => <div className="flex gap-1"><Button size="sm" variant="outline" onClick={() => setSeatsFor(s)}>Seats</Button>{!isManager && <><Button size="sm" variant="outline" onClick={() => setForm({ screen: s })}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => window.confirm('Delete this screen?') && del.mutate(s.id)}>Delete</Button></>}</div> }]} />
      <Modal open={!!form} onClose={() => setForm(null)} title={form?.screen ? 'Edit screen' : 'Add screen'} wide>{form && <ScreenForm theaterId={id} screen={form.screen} onClose={() => setForm(null)} />}</Modal>
      <Modal open={!!seatsFor} onClose={() => setSeatsFor(null)} title={`${seatsFor?.name}: seats`} wide>{seatsFor && <SeatEditor screen={seatsFor} />}</Modal>
    </div>
  )
}

/* ------------------------------------------------------------------ shows */
function ShowSeatsModal({ show, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['vendor-show-seats', show.id], queryFn: () => api.get(`/vendor/shows/${show.id}/seats`), refetchInterval: 10000 })
  const [sel, setSel] = useState(new Set())
  const m = useMutation({
    mutationFn: (blocked) => api.post(`/vendor/shows/${show.id}/seats/block`, { show_seat_ids: [...sel], blocked }),
    onSuccess: (r) => { toast.success(r.message); setSel(new Set()); qc.invalidateQueries({ queryKey: ['vendor-show-seats', show.id] }); qc.invalidateQueries({ queryKey: ['vendor-shows'] }) }, onError: (e) => toast.error(e.message),
  })
  if (isLoading) return <PageSpinner />
  const seats = data.seats.map((s) => ({ ...s, block_reason: null }))
  const toggle = (s) => setSel((p) => { const n = new Set(p); n.has(s.id) ? n.delete(s.id) : n.add(s.id); return n })
  return (
    <div className="space-y-4"><p className="text-sm text-gray-600">Live occupancy for this show. Block individual seats (held or sold seats can't be touched).</p>
      <SeatGrid seats={seats} selected={sel} onToggle={toggle} stateOf={(s) => s.status} />
      <div className="flex gap-3"><Button variant="danger" disabled={!sel.size} loading={m.isPending} onClick={() => m.mutate(true)}>Block selected</Button><Button variant="outline" disabled={!sel.size} onClick={() => m.mutate(false)}>Unblock selected</Button></div></div>
  )
}

function PricesModal({ show, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [p, setP] = useState(Object.fromEntries(Object.entries(show.prices).map(([k, v]) => [k, v / 100])))
  const m = useMutation({ mutationFn: () => api.patch(`/vendor/shows/${show.id}/prices`, { prices: Object.fromEntries(Object.entries(p).map(([k, v]) => [k, Math.round(Number(v) * 100)])) }), onSuccess: (r) => { toast.success(r.message); onClose(); qc.invalidateQueries({ queryKey: ['vendor-shows'] }) }, onError: (e) => toast.error(e.message) })
  return <div className="space-y-4"><p className="text-sm text-gray-600">New prices apply to unsold seats only; seats already booked keep their price.</p>
    <div className="grid gap-4 sm:grid-cols-3">{Object.keys(p).map((k) => <Input key={k} label={`${k} (₹)`} type="number" min="1" value={p[k]} onChange={(e) => setP({ ...p, [k]: e.target.value })} />)}</div><Button loading={m.isPending} onClick={() => m.mutate()}>Update prices</Button></div>
}

function Scheduler() {
  const toast = useToast()
  const qc = useQueryClient()
  const theaters = useTheaters()
  const approved = theaters.data?.filter((t) => t.approval_status === 'approved') || []
  const movies = useQuery({ queryKey: ['movies-all'], queryFn: () => api.get('/movies', { size: 100, sort: 'title' }) })
  const langs = useQuery({ queryKey: ['languages'], queryFn: () => api.get('/languages') })
  const today = ymd(new Date())
  const [v, setV] = useState({ theater: '', screen_id: '', movie_id: '', language_id: '', format: '2D', from: today, to: today, times: '10:00, 14:00, 18:00, 21:30' })
  const [pr, setPr] = useState({})
  const screens = useQuery({ queryKey: ['vendor-screens', v.theater], enabled: !!v.theater, queryFn: () => api.get(`/vendor/theaters/${v.theater}/screens`) })
  const screen = screens.data?.find((s) => String(s.id) === v.screen_id)
  const cats = screen ? [...new Set(screen.layout.rows.map((r) => r.category))] : []
  const m = useMutation({
    mutationFn: (b) => api.post('/vendor/shows/bulk', b),
    onSuccess: (r) => {
      const why = Object.entries(r.skipped.reduce((a, s) => ({ ...a, [s.reason]: (a[s.reason] || 0) + 1 }), {})).map(([k, n]) => `${n} ${k}`).join(', ')
      toast[r.created ? 'success' : 'info'](`Created ${r.created} show(s)${r.approval_status === 'pending' ? ' (awaiting admin review)' : ''}${r.skipped.length ? `; skipped ${r.skipped.length} (${why})` : ''}`)
      qc.invalidateQueries({ queryKey: ['vendor-shows'] })
    },
    onError: (e) => toast.error(e.message),
  })
  const submit = (e) => {
    e.preventDefault()
    if (!v.screen_id || !v.movie_id || !v.language_id) return toast.error('Choose theater, screen, movie and language')
    if (cats.some((c) => !(Number(pr[c]) > 0))) return toast.error('Enter a price for every seat category')
    const dates = []
    for (let d = new Date(`${v.from}T00:00:00`); d <= new Date(`${v.to}T00:00:00`) && dates.length < 31; d.setDate(d.getDate() + 1)) dates.push(ymd(d))
    if (!dates.length) return toast.error('Pick a valid date range')
    m.mutate({ movie_id: Number(v.movie_id), screen_id: Number(v.screen_id), language_id: Number(v.language_id), format: v.format, dates, times: v.times.split(',').map((x) => x.trim()).filter(Boolean), prices: Object.fromEntries(cats.map((c) => [c, Math.round(Number(pr[c]) * 100)])) })
  }
  return (
    <form onSubmit={submit} className="card space-y-4 p-5"><h2 className="font-bold">Schedule shows</h2>
      <div className="grid gap-4 sm:grid-cols-2"><Select label="Theater" value={v.theater} onChange={(e) => setV({ ...v, theater: e.target.value, screen_id: '' })}><option value="">Select…</option>{approved.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
        <Select label="Screen" value={v.screen_id} onChange={(e) => setV({ ...v, screen_id: e.target.value })}><option value="">Select…</option>{screens.data?.filter((s) => s.status === 'active').map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
        <Select label="Movie" value={v.movie_id} onChange={(e) => setV({ ...v, movie_id: e.target.value })}><option value="">Select…</option>{movies.data?.items.map((m2) => <option key={m2.id} value={m2.id}>{m2.title}</option>)}</Select>
        <Select label="Language" value={v.language_id} onChange={(e) => setV({ ...v, language_id: e.target.value })}><option value="">Select…</option>{langs.data?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></div>
      <div className="grid gap-4 sm:grid-cols-4"><Input label="From" type="date" min={today} value={v.from} onChange={(e) => setV({ ...v, from: e.target.value, to: e.target.value > v.to ? e.target.value : v.to })} /><Input label="To" type="date" min={v.from} value={v.to} onChange={(e) => setV({ ...v, to: e.target.value })} />
        <Input label="Times (IST, 24h)" value={v.times} onChange={(e) => setV({ ...v, times: e.target.value })} className="sm:col-span-1" /><Select label="Format" value={v.format} onChange={(e) => setV({ ...v, format: e.target.value })}>{['2D', '3D', 'IMAX 2D', '4DX'].map((f) => <option key={f}>{f}</option>)}</Select></div>
      {cats.length > 0 && <div className="grid gap-4 sm:grid-cols-4">{cats.map((c) => <Input key={c} label={`${c} price (₹)`} type="number" min="1" value={pr[c] || ''} onChange={(e) => setPr({ ...pr, [c]: e.target.value })} />)}</div>}
      <p className="text-xs text-gray-500">Missing a movie? <Link to="/vendor/movie-requests" className="font-semibold text-brand">Request it</Link>. Overlapping shows on a screen are skipped.</p>
      <Button loading={m.isPending}>Create shows</Button></form>
  )
}

function Shows() {
  useTitle('Shows')
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState('upcoming')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null) // {kind, show}
  const isManager = useIsManager()
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['vendor-shows', tab, page], queryFn: () => api.get('/vendor/shows', { upcoming: tab === 'upcoming', page, size: 12 }), placeholderData: (p) => p })
  const cancel = useMutation({ mutationFn: (id) => api.post(`/vendor/shows/${id}/cancel`, {}), onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ['vendor-shows'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-5"><StatusBanner /><h1 className="text-2xl font-bold">Shows & pricing</h1><Scheduler />
      <div className="flex gap-2">{['upcoming', 'past'].map((t) => <button key={t} onClick={() => { setTab(t); setPage(1) }} aria-pressed={tab === t} className={clsx('rounded-full px-4 py-1.5 text-sm font-medium capitalize', tab === t ? 'bg-brand text-white' : 'bg-white ring-1 ring-gray-200')}>{t}</button>)}</div>
      {isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? <PageSpinner /> : (
        <>
          <DataTable caption="Shows" rows={data.items} empty="No shows." columns={[
            { header: 'When', render: (s) => fmtDateTime(s.starts_at) }, { header: 'Movie', render: (s) => <><b>{s.movie_title}</b><p className="text-xs text-gray-500">{s.language_name} · {s.format}</p></> },
            { header: 'Screen', render: (s) => <>{s.theater_name}<p className="text-xs text-gray-500">{s.screen_name}</p></> },
            { header: 'Occupancy', render: (s) => { const pct = s.total ? Math.round((s.booked / s.total) * 100) : 0; return <div className="w-36"><div className="h-2 overflow-hidden rounded bg-gray-200"><div className="h-full bg-brand" style={{ width: `${pct}%` }} /></div><span className="text-xs text-gray-500">{s.booked}/{s.total} ({pct}%){s.blocked > 0 && ` · ${s.blocked} blocked`}</span></div> } },
            ...(isManager ? [] : [{ header: 'Revenue', render: (s) => inr(s.revenue_paise) }]), { header: 'Prices', render: (s) => Object.entries(s.prices).map(([k, p]) => `${k} ${inr(p)}`).join(' · ') },
            { header: 'Status', render: (s) => <div className="flex flex-col gap-1"><Badge tone={statusTone(s.status)}>{s.status}</Badge>{s.approval_status !== 'approved' && <Badge tone={statusTone(s.approval_status)}>review: {s.approval_status}</Badge>}</div> },
            { header: '', render: (s) => s.status === 'active' && tab === 'upcoming' && <div className="flex flex-wrap gap-1"><Button size="sm" variant="outline" onClick={() => setModal({ kind: 'seats', show: s })}>Seats</Button><Button size="sm" variant="outline" onClick={() => setModal({ kind: 'prices', show: s })}>Prices</Button>
              {!isManager && <Button size="sm" variant="ghost" onClick={() => window.confirm(`Cancel this show and refund its ${s.booked} booking seat(s)?`) && cancel.mutate(s.id)}>Cancel</Button>}</div> }]} />
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>)}
      <Modal open={modal?.kind === 'seats'} onClose={() => setModal(null)} title="Show seats" wide>{modal?.kind === 'seats' && <ShowSeatsModal show={modal.show} onClose={() => setModal(null)} />}</Modal>
      <Modal open={modal?.kind === 'prices'} onClose={() => setModal(null)} title="Ticket prices">{modal?.kind === 'prices' && <PricesModal show={modal.show} onClose={() => setModal(null)} />}</Modal>
    </div>
  )
}

/* ------------------------------------------------------------------ bookings */
function Bookings() {
  useTitle('Bookings')
  const qc = useQueryClient()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [cancelFor, setCancelFor] = useState(null)
  const [reason, setReason] = useState('')
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['vendor-bookings', page, status], queryFn: () => api.get('/vendor/bookings', { page, size: 15, status: status || undefined }), placeholderData: (p) => p })
  const cancel = useMutation({ mutationFn: () => api.post(`/vendor/bookings/${cancelFor.id}/cancel`, { reason }), onSuccess: () => { toast.success('Cancelled and refunded'); setCancelFor(null); setReason(''); qc.invalidateQueries({ queryKey: ['vendor-bookings'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-4"><div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Bookings</h1><Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-40"><option value="">All</option><option value="confirmed">Confirmed</option><option value="cancelled">Cancelled</option></Select></div>
      {isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? <PageSpinner /> : <>
        <DataTable caption="Bookings" rows={data.items} empty="No bookings yet." columns={[
          { header: 'Booking', render: (b) => <><span className="font-mono font-semibold">{b.code}</span><p className="text-xs text-gray-500">{b.customer_name}</p></> }, { header: 'Show', render: (b) => <>{b.title}<p className="text-xs text-gray-500">{b.theater} · {fmtDateTime(b.starts_at)}</p></> },
          { header: 'Seats', render: (b) => b.items.map((i) => i.label.split(' ·')[0]).join(', ') }, { header: 'Gross', render: (b) => inr(b.subtotal_paise - b.discount_paise) },
          { header: 'Commission', render: (b) => inr(b.commission_paise) }, { header: 'Your share', render: (b) => <b>{inr(b.vendor_share_paise)}</b> }, { header: 'Status', render: (b) => <Badge tone={statusTone(b.status)}>{b.status}</Badge> },
          { header: '', render: (b) => b.status === 'confirmed' && <Button size="sm" variant="outline" onClick={() => setCancelFor(b)}>Cancel & refund</Button> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}
      <Modal open={!!cancelFor} onClose={() => setCancelFor(null)} title={`Cancel ${cancelFor?.code}?`}><p className="text-sm text-gray-600">The customer is refunded the ticket value immediately and the seats are released.</p>
        <Textarea label="Reason (kept in the audit log)" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /><div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={() => setCancelFor(null)}>Keep</Button><Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>Cancel booking</Button></div></Modal>
    </div>
  )
}

/* ------------------------------------------------------------------ earnings & payouts */
function Earnings() {
  useTitle('Earnings & payouts')
  const qc = useQueryClient()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [amt, setAmt] = useState('')
  const e = useQuery({ queryKey: ['vendor-earnings'], queryFn: () => api.get('/vendor/earnings') })
  const p = useQuery({ queryKey: ['vendor-payouts', page], queryFn: () => api.get('/vendor/payouts', { page, size: 10 }) })
  const req = useMutation({
    mutationFn: () => api.post('/vendor/payouts', amt ? { amount_paise: Math.round(Number(amt) * 100) } : {}),
    onSuccess: () => { toast.success('Payout requested'); setAmt(''); qc.invalidateQueries({ queryKey: ['vendor-earnings'] }); qc.invalidateQueries({ queryKey: ['vendor-payouts'] }) }, onError: (er) => toast.error(er.message),
  })
  if (e.isLoading) return <PageSpinner />
  const d = e.data
  return (
    <div className="space-y-5"><StatusBanner /><h1 className="text-2xl font-bold">Earnings & payouts</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Stat label="Gross ticket sales" value={inr(d.gross_paise)} /><Stat label={`Commission (${d.commission_pct}%)`} value={inr(d.commission_paise)} /><Stat label="Net earnings" value={inr(d.net_paise)} /><Stat label="Paid out" value={inr(d.paid_out_paise)} sub={d.pending_payout_paise ? `${inr(d.pending_payout_paise)} pending` : undefined} /></div>
      <section className="card p-5"><h2 className="font-bold">Withdraw</h2>
        <p className="mt-1 text-sm text-gray-600">Available now: <b className="text-emerald-600">{inr(d.available_paise)}</b>. Earnings from shows that haven't started yet ({inr(d.upcoming_paise)}) become withdrawable {d.hold_days > 0 ? `${d.hold_days} day(s) after` : 'once'} the show starts. Minimum payout {inr(d.min_payout_paise)}.</p>
        <form onSubmit={(ev) => { ev.preventDefault(); req.mutate() }} className="mt-3 flex flex-wrap items-end gap-3"><Input label="Amount (₹, blank = everything)" type="number" min="0" step="0.01" value={amt} onChange={(ev) => setAmt(ev.target.value)} className="w-64" /><Button loading={req.isPending} disabled={d.available_paise < d.min_payout_paise}>Request payout</Button></form></section>
      <section><h2 className="mb-2 font-bold">Payout history</h2>
        {p.isLoading ? <PageSpinner /> : <><DataTable caption="Payouts" rows={p.data.items} empty="No payouts yet." columns={[{ header: 'Requested', render: (x) => fmtDateTime(x.created_at) }, { header: 'Amount', render: (x) => <b>{inr(x.amount_paise)}</b> }, { header: 'Status', render: (x) => <Badge tone={x.status === 'paid' ? 'green' : x.status === 'rejected' ? 'red' : 'amber'}>{x.status}</Badge> },
          { header: 'Bank reference', render: (x) => x.reference || '–' }, { header: 'Processed', render: (x) => (x.processed_at ? fmtDateTime(x.processed_at) : '–') }, { header: 'Note', render: (x) => x.note || '' }]} /><Pagination page={p.data.page} pages={p.data.pages} onChange={setPage} /></>}</section>
    </div>
  )
}

/* ------------------------------------------------------------------ reports */
function Reports() {
  useTitle('Sales reports')
  const toast = useToast()
  const [r, setR] = useState({ date_from: ymd(new Date(Date.now() - 30 * 864e5)), date_to: ymd(new Date()) })
  const q = useQuery({ queryKey: ['vendor-report', r], queryFn: () => api.get('/vendor/reports/sales', r) })
  const dl = async () => { try { await download('/vendor/reports/sales', { ...r, format: 'csv' }, `sales-${r.date_from}-to-${r.date_to}.csv`) } catch (e) { toast.error(e.message) } }
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Sales reports</h1>
      <div className="flex flex-wrap items-end gap-3"><Input label="From" type="date" value={r.date_from} onChange={(e) => setR({ ...r, date_from: e.target.value })} /><Input label="To" type="date" value={r.date_to} onChange={(e) => setR({ ...r, date_to: e.target.value })} /><Button variant="outline" onClick={dl}><Download className="h-4 w-4" />Download CSV</Button></div>
      {q.isLoading ? <PageSpinner /> : q.isError ? <ErrorState error={q.error} retry={q.refetch} /> : <>
        <div className="grid gap-4 sm:grid-cols-3"><Stat label="Gross" value={`₹${q.data.totals.gross.toLocaleString('en-IN')}`} /><Stat label="Commission" value={`₹${q.data.totals.commission.toLocaleString('en-IN')}`} /><Stat label="Net" value={`₹${q.data.totals.net.toLocaleString('en-IN')}`} /></div>
        <DataTable caption="Sales" rows={q.data.rows} empty="No sales in this range." columns={[{ header: 'Booked', render: (x) => fmtDateTime(x.booked_at) }, { header: 'ID', render: (x) => <span className="font-mono">{x.booking_id}</span> }, { header: 'Theater', render: (x) => `${x.theater} · ${x.screen}` },
          { header: 'Movie', key: 'movie' }, { header: 'Show', render: (x) => fmtDateTime(x.show_time) }, { header: 'Seats', key: 'seats' }, { header: 'Gross', render: (x) => `₹${x.gross}` }, { header: 'Net', render: (x) => `₹${x.net}` }]} /></>}
    </div>
  )
}

/* ------------------------------------------------------------------ movie requests */
function MovieRequests() {
  useTitle('Movie requests')
  const qc = useQueryClient()
  const toast = useToast()
  const list = useQuery({ queryKey: ['vendor-movie-requests'], queryFn: () => api.get('/vendor/movie-requests') })
  const [v, setV] = useState({ title: '', synopsis: '', duration_min: 120, certificate: 'UA', release_date: '', languages: '', notes: '' })
  const m = useMutation({
    mutationFn: () => api.post('/vendor/movie-requests', { ...v, duration_min: Number(v.duration_min), release_date: v.release_date || null, notes: v.notes || null }),
    onSuccess: () => { toast.success('Request sent to the platform admin'); setV({ ...v, title: '', synopsis: '', notes: '' }); qc.invalidateQueries({ queryKey: ['vendor-movie-requests'] }) }, onError: (e) => toast.error(e.message),
  })
  return (
    <div className="space-y-5"><h1 className="text-2xl font-bold">Movie requests</h1>
      <form onSubmit={(e) => { e.preventDefault(); if (!v.title.trim()) return toast.error('Title is required'); m.mutate() }} className="card space-y-4 p-5"><h2 className="font-bold">Request a movie</h2>
        <div className="grid gap-4 sm:grid-cols-2"><Input label="Title" value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} /><Input label="Languages" placeholder="Hindi, Tamil" value={v.languages} onChange={(e) => setV({ ...v, languages: e.target.value })} /></div>
        <div className="grid gap-4 sm:grid-cols-3"><Input label="Duration (min)" type="number" value={v.duration_min} onChange={(e) => setV({ ...v, duration_min: e.target.value })} /><Select label="Certificate" value={v.certificate} onChange={(e) => setV({ ...v, certificate: e.target.value })}>{['U', 'UA', 'A'].map((c) => <option key={c}>{c}</option>)}</Select><Input label="Release date" type="date" value={v.release_date} onChange={(e) => setV({ ...v, release_date: e.target.value })} /></div>
        <Textarea label="Synopsis" rows={2} value={v.synopsis} onChange={(e) => setV({ ...v, synopsis: e.target.value })} /><Textarea label="Notes for the admin (distributor, print availability…)" rows={2} value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />
        <Button loading={m.isPending}>Send request</Button></form>
      <DataTable caption="Requests" rows={list.data || []} empty="No requests yet." columns={[{ header: 'Movie', render: (r) => <b>{r.title}</b> }, { header: 'Requested', render: (r) => fmtDate(r.created_at) }, { header: 'Status', render: (r) => <Badge tone={statusTone(r.status)}>{r.status}</Badge> }, { header: 'Admin note', render: (r) => r.admin_note || '' }]} />
    </div>
  )
}

/* ------------------------------------------------------------------ staff (theater managers) */
function Staff() {
  useTitle('Staff')
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['vendor-staff'], queryFn: () => api.get('/vendor/staff') })
  const theaters = useTheaters()
  const approved = (theaters.data || []).filter((t) => t.approval_status === 'approved')
  const [open, setOpen] = useState(false)
  const [edit, setEdit] = useState(null)
  const blank = { name: '', email: '', password: '', theater_ids: [] }
  const [f, setF] = useState(blank)
  const [errs, setErrs] = useState({})
  const done = () => qc.invalidateQueries({ queryKey: ['vendor-staff'] })
  const create = useMutation({ mutationFn: () => api.post('/vendor/staff', f), onSuccess: () => { toast.success('Manager submitted. An admin must approve the account before they can sign in.'); setOpen(false); setF(blank); done() }, onError: (e) => setErrs(Object.keys(e.fieldErrors || {}).length ? e.fieldErrors : { form: e.message }) })
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.patch(`/vendor/staff/${id}`, b), onSuccess: () => { setEdit(null); done() }, onError: (e) => toast.error(e.message) })
  const toggle = (ids, id) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id])
  const picker = (ids, set) => (
    <fieldset className="space-y-1"><legend className="mb-1 text-sm font-medium">Theaters this person may manage</legend>
      {approved.length === 0 && <p className="text-sm text-gray-500">You have no approved theaters yet.</p>}
      {approved.map((t) => <label key={t.id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ids.includes(t.id)} onChange={() => set(toggle(ids, t.id))} />{t.name} <span className="text-gray-400">· {t.city.name}</span></label>)}</fieldset>)
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <div className="space-y-4"><StatusBanner />
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Theater managers</h1><Button onClick={() => { setErrs({}); setOpen(true) }}><Plus className="h-4 w-4" />Add manager</Button></div>
      <p className="text-sm text-gray-600">Managers can schedule shows, change prices and block seats at the theaters you choose. They cannot see earnings, payouts, bookings or reports, cancel shows, or manage staff. New accounts need admin approval before they can sign in.</p>
      <DataTable caption="Managers" rows={data} empty="No managers yet." columns={[
        { header: 'Manager', render: (m) => <><b>{m.name}</b><p className="text-xs text-gray-500">{m.email}</p></> },
        { header: 'Theaters', render: (m) => m.theater_names.join(', ') || '–' },
        { header: 'Status', render: (m) => <><Badge tone={statusTone(m.status === 'active' ? 'approved' : m.status)}>{m.status === 'pending' ? 'awaiting admin approval' : m.status}</Badge>{m.rejection_reason && <p className="mt-1 max-w-[14rem] text-xs text-gray-500">{m.rejection_reason}</p>}</> },
        { header: '', render: (m) => (m.status === 'active' || m.status === 'disabled') && <div className="flex gap-1"><Button size="sm" variant="outline" onClick={() => setEdit({ id: m.id, name: m.name, theater_ids: m.theater_ids })}>Theaters</Button>
          <Button size="sm" variant="ghost" onClick={() => patch.mutate({ id: m.id, disabled: m.status === 'active' })}>{m.status === 'active' ? 'Disable' : 'Enable'}</Button></div> }]} />
      <Modal open={open} onClose={() => setOpen(false)} title="Add theater manager">
        <form className="space-y-3" noValidate onSubmit={(e) => { e.preventDefault(); setErrs({}); create.mutate() }}>
          {errs.form && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{errs.form}</p>}
          <Input label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} error={errs.name} />
          <Input label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} error={errs.email} />
          <Input label="Temporary password" type="password" autoComplete="new-password" hint="At least 8 characters. Share it securely; they should change it after signing in." value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} error={errs.password} />
          {picker(f.theater_ids, (ids) => setF({ ...f, theater_ids: ids }))}{errs.theater_ids && <p role="alert" className="text-xs text-red-600">{errs.theater_ids}</p>}
          <Button loading={create.isPending} disabled={!f.theater_ids.length}>Submit for approval</Button>
        </form>
      </Modal>
      <Modal open={!!edit} onClose={() => setEdit(null)} title={`Theaters for ${edit?.name || ''}`}>{edit && (
        <div className="space-y-3">{picker(edit.theater_ids, (ids) => setEdit({ ...edit, theater_ids: ids }))}
          <Button loading={patch.isPending} disabled={!edit.theater_ids.length} onClick={() => patch.mutate({ id: edit.id, theater_ids: edit.theater_ids })}>Save</Button></div>)}</Modal>
    </div>
  )
}

export default function Vendor() {
  const isManager = useIsManager()
  if (isManager) {
    return (
      <PortalShell title="Theater manager" links={MANAGER_LINKS}>
        <Routes>
          <Route path="shows" element={<Shows />} /><Route path="theaters" element={<Theaters />} /><Route path="theaters/:id" element={<TheaterDetail />} />
          <Route path="*" element={<Navigate to="/vendor/shows" replace />} />
        </Routes>
      </PortalShell>
    )
  }
  return (
    <PortalShell title="Theater vendor" links={links}>
      <Routes>
        <Route index element={<Dashboard />} /><Route path="theaters" element={<Theaters />} /><Route path="theaters/:id" element={<TheaterDetail />} />
        <Route path="shows" element={<Shows />} /><Route path="bookings" element={<Bookings />} /><Route path="earnings" element={<Earnings />} />
        <Route path="staff" element={<Staff />} /><Route path="reports" element={<Reports />} /><Route path="movie-requests" element={<MovieRequests />} /><Route path="*" element={<Navigate to="/vendor" replace />} />
      </Routes>
    </PortalShell>
  )
}
