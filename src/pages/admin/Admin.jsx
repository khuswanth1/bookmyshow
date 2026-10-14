import { useState } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, Building2, CalendarDays, Clapperboard, CreditCard, Film, Gift, Globe, LifeBuoy, ListChecks, MapPin, Megaphone, Percent, Plus, Store, Tag, Ticket, Tv, Users, Wallet } from 'lucide-react'
import { api } from '../../lib/api'
import { useToast } from '../../context/providers'
import { useTitle } from '../../hooks'
import { BarChart, DataTable, PortalShell } from '../../components/portal'
import { Badge, Button, ErrorState, Input, Modal, PageSpinner, Pagination, Select, Stat, Textarea, statusTone } from '../../components/ui'
import ResourceManager from './ResourceManager'
import { EventForm } from '../organizer/Organizer'
import { AuditLogs, Commissions, MarketDashboard, MovieRequestsAdmin, Payouts, ShowReview, Theaters as TheaterApprovals, VendorManagers, Vendors } from './Marketplace'
import { RESOURCES } from './resources.jsx'
import { fmtDate, fmtDateTime, inr } from '../../lib/format'

const links = [
  ['/admin', 'Dashboard & reports', BarChart3, true],
  ['/admin/vendors', 'Vendors', Store], ['/admin/vendor-managers', 'Vendor managers', Users], ['/admin/theaters', 'Theater approvals', Building2], ['/admin/show-review', 'Show review', CalendarDays], ['/admin/movie-requests', 'Movie requests', Film],
  ['/admin/payouts', 'Payouts', Wallet], ['/admin/commissions', 'Commissions & settings', Percent], ['/admin/audit-logs', 'Audit logs', ListChecks],
  ['/admin/movies', 'Movies', Film], ['/admin/venues', 'All cinemas & venues', Building2], ['/admin/screens', 'Screens & seats', Clapperboard], ['/admin/shows', 'Shows', CalendarDays],
  ['/admin/events', 'Events', Ticket], ['/admin/organizers', 'Organizers', Store], ['/admin/bookings', 'Bookings', ListChecks], ['/admin/payments', 'Payments', CreditCard],
  ['/admin/coupons', 'Coupons & offers', Percent], ['/admin/gift-cards', 'Gift cards', Gift], ['/admin/initiatives', 'Social initiatives', Megaphone],
  ['/admin/cities', 'Cities', MapPin], ['/admin/genres', 'Genres', Tag], ['/admin/languages', 'Languages', Globe], ['/admin/categories', 'Event categories', Tag],
  ['/admin/videos', 'Stream videos', Tv], ['/admin/users', 'Users', Users], ['/admin/support', 'Support', LifeBuoy], ['/admin/faqs', 'FAQs', LifeBuoy],
]

function Dashboard() {
  useTitle('Admin dashboard')
  const [days, setDays] = useState(30)
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['admin-report', days], queryFn: () => api.get('/admin/reports/summary', { days }) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  const c = data.counts
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Dashboard</h1>
        <Select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></Select></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Gross sales" value={inr(data.gross_paise)} sub={`Fees & GST ${inr(data.fees_paise)}`} /><Stat label="Confirmed bookings" value={data.bookings} />
        <Stat label="Users" value={c.users} /><Stat label="Pending reviews" value={c.pending_events + c.pending_organizers} sub={`${c.pending_events} events · ${c.pending_organizers} organizers`} tone={(c.pending_events + c.pending_organizers) ? 'text-amber-600' : ''} /></div>
      <section className="card p-5"><h2 className="mb-3 font-bold">Gross sales by day</h2><BarChart title="Gross sales by day" data={data.daily.map((d) => ({ label: fmtDate(d.date, { day: 'numeric', month: 'short' }), value: d.gross_paise / 100 }))} format={(v) => `₹${v.toLocaleString('en-IN')}`} /></section>
      <div className="grid gap-5 lg:grid-cols-2">
        <section><h2 className="mb-2 font-bold">Top movies</h2><DataTable caption="Top movies" rows={data.top_movies} empty="No movie sales yet." columns={[{ header: 'Movie', key: 'title' }, { header: 'Bookings', key: 'bookings' }, { header: 'Gross', render: (r) => inr(r.gross_paise) }]} /></section>
        <section><h2 className="mb-2 font-bold">Top cities</h2><DataTable caption="Top cities" rows={data.top_cities} empty="No sales yet." columns={[{ header: 'City', key: 'city' }, { header: 'Bookings', key: 'bookings' }, { header: 'Gross', render: (r) => inr(r.gross_paise) }]} /></section>
        <section className="card p-5"><h2 className="mb-2 font-bold">Bookings by status</h2><ul className="space-y-1 text-sm">{Object.entries(data.by_status).map(([k, v]) => <li key={k} className="flex justify-between"><Badge tone={statusTone(k)}>{k}</Badge><b>{v}</b></li>)}{!Object.keys(data.by_status).length && <li className="text-gray-500">No bookings yet.</li>}</ul></section>
        <section className="card p-5"><h2 className="mb-2 font-bold">Payments by status</h2><ul className="space-y-1 text-sm">{Object.entries(data.payments_by_status).map(([k, v]) => <li key={k} className="flex justify-between"><Badge tone={statusTone(k)}>{k.replace(/_/g, ' ')}</Badge><b>{v}</b></li>)}{!Object.keys(data.payments_by_status).length && <li className="text-gray-500">No payments yet.</li>}</ul></section>
      </div>
    </div>
  )
}

function Screens() {
  useTitle('Admin: screens')
  const qc = useQueryClient()
  const toast = useToast()
  const [venueId, setVenueId] = useState('')
  const venues = useQuery({ queryKey: ['admin', 'venues', 'all'], queryFn: () => api.get('/admin/venues', { size: 100 }) })
  const screens = useQuery({ queryKey: ['admin', 'screens', venueId], enabled: !!venueId, queryFn: () => api.get('/admin/screens', { venue_id: venueId, size: 50 }) })
  const blank = { name: '', rows: [{ label: 'A', category: 'Silver', seats: 10, aisles: '5' }] }
  const [form, setForm] = useState(null)
  const [editId, setEditId] = useState(null)
  const save = useMutation({
    mutationFn: (b) => (editId ? api.put(`/admin/screens/${editId}`, b) : api.post('/admin/screens', b)),
    onSuccess: () => { toast.success('Screen saved'); setForm(null); qc.invalidateQueries({ queryKey: ['admin', 'screens'] }) }, onError: (e) => toast.error(e.message),
  })
  const del = useMutation({ mutationFn: (id) => api.del(`/admin/screens/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'screens'] }), onError: (e) => toast.error(e.message) })
  const submit = (e) => {
    e.preventDefault()
    if (!form.name.trim()) return toast.error('Screen name is required')
    save.mutate({ venue_id: Number(venueId), name: form.name.trim(), layout: { rows: form.rows.map((r) => ({ label: r.label.trim(), category: r.category.trim(), seats: Number(r.seats), aisles: String(r.aisles).split(',').map((x) => Number(x.trim())).filter(Boolean) })) } })
  }
  const setRow = (i, k, v) => setForm({ ...form, rows: form.rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)) })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Screens & seat layouts</h1>
      <Select label="Cinema / venue" value={venueId} onChange={(e) => setVenueId(e.target.value)} className="max-w-md"><option value="">Select…</option>{venues.data?.items.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</Select>
      {venueId && (screens.isLoading ? <PageSpinner /> : (
        <>
          <Button onClick={() => { setEditId(null); setForm(blank) }}><Plus className="h-4 w-4" />Add screen</Button>
          <DataTable caption="Screens" rows={screens.data.items} empty="No screens yet." columns={[{ header: 'Name', key: 'name' }, { header: 'Rows', render: (s) => s.layout.rows?.map((r) => `${r.label}(${r.seats} ${r.category})`).join(', ') },
            { header: 'Seats', render: (s) => s.layout.rows?.reduce((a, r) => a + r.seats, 0) },
            { header: '', render: (s) => <div className="flex gap-1"><Button size="sm" variant="outline" onClick={() => { setEditId(s.id); setForm({ name: s.name, rows: s.layout.rows.map((r) => ({ ...r, aisles: (r.aisles || []).join(',') })) }) }}>Edit</Button><Button size="sm" variant="ghost" onClick={() => window.confirm('Delete screen?') && del.mutate(s.id)}>Delete</Button></div> }]} />
        </>
      ))}
      <Modal open={!!form} onClose={() => setForm(null)} title={editId ? 'Edit screen' : 'Add screen'} wide>
        {form && <form onSubmit={submit} className="space-y-4"><Input label="Screen name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <p className="text-xs text-gray-500">Seats that are booked or held in a show can't be removed or moved to another category; everything else can change. Each row: label, seat category (must match show price keys), seat count, aisle gaps after these seat numbers.</p>
          {form.rows.map((r, i) => (
            <div key={i} className="grid items-end gap-2 sm:grid-cols-[4rem_1fr_6rem_8rem_auto]">
              <Input label={i === 0 ? 'Row' : undefined} aria-label="Row label" value={r.label} maxLength={3} onChange={(e) => setRow(i, 'label', e.target.value.toUpperCase())} />
              <Input label={i === 0 ? 'Category' : undefined} aria-label="Category" value={r.category} onChange={(e) => setRow(i, 'category', e.target.value)} />
              <Input label={i === 0 ? 'Seats' : undefined} aria-label="Seats" type="number" min="1" max="40" value={r.seats} onChange={(e) => setRow(i, 'seats', e.target.value)} />
              <Input label={i === 0 ? 'Aisles after' : undefined} aria-label="Aisles after seats" placeholder="4,8" value={r.aisles} onChange={(e) => setRow(i, 'aisles', e.target.value)} />
              <Button type="button" variant="ghost" aria-label="Remove row" onClick={() => setForm({ ...form, rows: form.rows.filter((_, j) => j !== i) })} disabled={form.rows.length === 1}>✕</Button>
            </div>))}
          <Button type="button" size="sm" variant="outline" onClick={() => setForm({ ...form, rows: [...form.rows, { label: String.fromCharCode(65 + form.rows.length), category: form.rows.at(-1).category, seats: form.rows.at(-1).seats, aisles: form.rows.at(-1).aisles }] })}>+ Add row</Button>
          <div className="flex justify-end"><Button loading={save.isPending}>Save screen</Button></div></form>}
      </Modal></div>
  )
}

function Shows() {
  useTitle('Admin: shows')
  const qc = useQueryClient()
  const toast = useToast()
  const movies = useQuery({ queryKey: ['admin', 'movies', 'all'], queryFn: () => api.get('/admin/movies', { size: 100 }) })
  const venues = useQuery({ queryKey: ['admin', 'venues', 'all'], queryFn: () => api.get('/admin/venues', { size: 100 }) })
  const langs = useQuery({ queryKey: ['opt', 'languages'], queryFn: () => api.get('/languages') })
  const [venueId, setVenueId] = useState('')
  const screens = useQuery({ queryKey: ['admin', 'screens', venueId], enabled: !!venueId, queryFn: () => api.get('/admin/screens', { venue_id: venueId, size: 50 }) })
  const [v, setV] = useState({ movie_id: '', screen_id: '', language_id: '', format: '2D', dates: '', times: '10:00, 14:00, 18:00, 21:30', prices: '' })
  const [page, setPage] = useState(1)
  const list = useQuery({ queryKey: ['admin', 'shows', page], queryFn: () => api.get('/admin/shows', { page, size: 15 }) })
  const screen = screens.data?.items.find((s) => String(s.id) === v.screen_id)
  const cats = screen ? [...new Set(screen.layout.rows.map((r) => r.category))] : []
  const [pr, setPr] = useState({})
  const create = useMutation({
    mutationFn: (b) => api.post('/admin/shows/bulk', b),
    onSuccess: (r) => { toast[r.created ? 'success' : 'info'](`Created ${r.created} shows${r.skipped.length ? `, skipped ${r.skipped.length} (${r.skipped[0].reason})` : ''}`); qc.invalidateQueries({ queryKey: ['admin', 'shows'] }) }, onError: (e) => toast.error(e.message),
  })
  const cancel = useMutation({ mutationFn: (id) => api.post(`/admin/shows/${id}/cancel`), onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ['admin', 'shows'] }) }, onError: (e) => toast.error(e.message) })
  const submit = (e) => {
    e.preventDefault()
    const dates = v.dates.split(',').map((x) => x.trim()).filter(Boolean)
    if (!v.movie_id || !v.screen_id || !v.language_id || !dates.length) return toast.error('Pick a movie, screen, language and at least one date (YYYY-MM-DD)')
    if (cats.some((c) => !(Number(pr[c]) > 0))) return toast.error('Enter a price for every seat category')
    create.mutate({ movie_id: Number(v.movie_id), screen_id: Number(v.screen_id), language_id: Number(v.language_id), format: v.format, dates, times: v.times.split(',').map((x) => x.trim()).filter(Boolean), prices: Object.fromEntries(cats.map((c) => [c, Math.round(Number(pr[c]) * 100)])) })
  }
  const today = new Date().toISOString().slice(0, 10)
  return (
    <div className="space-y-5"><h1 className="text-2xl font-bold">Schedule shows</h1>
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="grid gap-4 sm:grid-cols-2"><Select label="Movie" value={v.movie_id} onChange={(e) => setV({ ...v, movie_id: e.target.value })}><option value="">Select…</option>{movies.data?.items.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}</Select>
          <Select label="Language" value={v.language_id} onChange={(e) => setV({ ...v, language_id: e.target.value })}><option value="">Select…</option>{langs.data?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select>
          <Select label="Cinema" value={venueId} onChange={(e) => { setVenueId(e.target.value); setV({ ...v, screen_id: '' }) }}><option value="">Select…</option>{venues.data?.items.filter((x) => x.type === 'cinema').map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select>
          <Select label="Screen" value={v.screen_id} onChange={(e) => setV({ ...v, screen_id: e.target.value })}><option value="">Select…</option>{screens.data?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></div>
        <div className="grid gap-4 sm:grid-cols-3"><Input label="Dates (comma separated)" placeholder={`${today}, ...`} value={v.dates} onChange={(e) => setV({ ...v, dates: e.target.value })} /><Input label="Times (local, 24h)" value={v.times} onChange={(e) => setV({ ...v, times: e.target.value })} />
          <Select label="Format" value={v.format} onChange={(e) => setV({ ...v, format: e.target.value })}>{['2D', '3D', 'IMAX 2D', '4DX'].map((f) => <option key={f}>{f}</option>)}</Select></div>
        {cats.length > 0 && <div className="grid gap-4 sm:grid-cols-4">{cats.map((c) => <Input key={c} label={`${c} price (₹)`} type="number" min="1" value={pr[c] || ''} onChange={(e) => setPr({ ...pr, [c]: e.target.value })} />)}</div>}
        <p className="text-xs text-gray-500">Times are interpreted in IST (UTC+5:30). Overlapping shows on the same screen are skipped.</p>
        <Button loading={create.isPending}>Create shows</Button></form>
      <section><h2 className="mb-2 font-bold">Upcoming shows</h2>
        {list.isLoading ? <PageSpinner /> : <><DataTable caption="Upcoming shows" rows={list.data?.items || []} columns={[{ header: 'ID', key: 'id' }, { header: 'Starts', render: (s) => fmtDateTime(s.starts_at) }, { header: 'Movie', render: (s) => movies.data?.items.find((m) => m.id === s.movie_id)?.title || s.movie_id },
          { header: 'Format', key: 'format' }, { header: 'Prices', render: (s) => Object.entries(s.prices).map(([k, p]) => `${k} ${inr(p)}`).join(' · ') }, { header: 'Status', render: (s) => <Badge tone={statusTone(s.status)}>{s.status}</Badge> },
          { header: '', render: (s) => s.status === 'active' && <Button size="sm" variant="ghost" onClick={() => window.confirm('Cancel this show and refund all its bookings?') && cancel.mutate(s.id)}>Cancel</Button> }]} />
          <Pagination page={list.data.page} pages={list.data.pages} onChange={setPage} /></>}</section></div>
  )
}

function Events() {
  useTitle('Admin: events')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'events', status, page], queryFn: () => api.get('/admin/events', { status: status || undefined, page, size: 12 }) })
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.patch(`/admin/events/${id}`, b), onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin', 'events'] }); qc.invalidateQueries({ queryKey: ['admin-report'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-4"><div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Events</h1><Link to="/admin/events/new"><Button><Plus className="h-4 w-4" />Create event</Button></Link></div>
      <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-44"><option value="">All</option>{['pending', 'approved', 'rejected', 'cancelled'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Events" rows={data.items} empty="Nothing to review." columns={[
        { header: 'Event', render: (e) => <><b>{e.title}</b><p className="text-xs text-gray-500">{e.section} · {e.category.name} · {e.city.name}</p></> }, { header: 'When', render: (e) => fmtDateTime(e.starts_at) },
        { header: 'Tickets', render: (e) => `${e.ticket_types.reduce((a, t) => a + t.sold, 0)}/${e.ticket_types.reduce((a, t) => a + t.total, 0)}` }, { header: 'Status', render: (e) => <Badge tone={statusTone(e.status)}>{e.status}</Badge> },
        { header: 'Flags', render: (e) => <div className="flex flex-col gap-1 text-xs"><label><input type="checkbox" checked={e.is_featured} onChange={(x) => patch.mutate({ id: e.id, is_featured: x.target.checked })} /> Featured</label><label><input type="checkbox" checked={e.is_exclusive} onChange={(x) => patch.mutate({ id: e.id, is_exclusive: x.target.checked })} /> Exclusive</label></div> },
        { header: '', render: (e) => <div className="flex gap-1">{e.status !== 'approved' && <Button size="sm" onClick={() => patch.mutate({ id: e.id, status: 'approved' })}>Approve</Button>}{e.status === 'pending' && <Button size="sm" variant="outline" onClick={() => patch.mutate({ id: e.id, status: 'rejected' })}>Reject</Button>}</div> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}</div>
  )
}

function Organizers() {
  useTitle('Admin: organizers')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'organizers', status], queryFn: () => api.get('/admin/organizers', { status: status || undefined, size: 50 }) })
  const review = useMutation({ mutationFn: ({ id, status: s }) => api.patch(`/admin/organizers/${id}`, { status: s }), onSuccess: () => { toast.success('Updated'); qc.invalidateQueries({ queryKey: ['admin', 'organizers'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Organizer applications</h1>
      <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-44"><option value="">All</option>{['pending', 'approved', 'rejected'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <DataTable caption="Organizers" rows={data.items} empty="No applications." columns={[{ header: 'Company', render: (o) => <><b>{o.company_name}</b><p className="text-xs text-gray-500">{o.description}</p></> }, { header: 'Contact', render: (o) => <>{o.user_name}<p className="text-xs text-gray-500">{o.user_email} · {o.contact_phone}</p></> },
        { header: 'Applied', render: (o) => fmtDate(o.created_at) }, { header: 'Status', render: (o) => <Badge tone={statusTone(o.status)}>{o.status}</Badge> },
        { header: '', render: (o) => <div className="flex gap-1">{o.status !== 'approved' && <Button size="sm" onClick={() => review.mutate({ id: o.id, status: 'approved' })}>Approve</Button>}{o.status !== 'rejected' && <Button size="sm" variant="outline" onClick={() => review.mutate({ id: o.id, status: 'rejected' })}>Reject</Button>}</div> }]} />}</div>
  )
}

function UsersPage() {
  useTitle('Admin: users')
  const qc = useQueryClient()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'users', q, role, page], queryFn: () => api.get('/admin/users', { q: q || undefined, role: role || undefined, page, size: 15 }), placeholderData: (p) => p })
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.patch(`/admin/users/${id}`, b), onSuccess: () => { toast.success('Updated'); qc.invalidateQueries({ queryKey: ['admin', 'users'] }) }, onError: (e) => toast.error(e.message) })
  const [staffOpen, setStaffOpen] = useState(false)
  const [sf, setSf] = useState({ name: '', email: '', password: '', role: 'checkin' })
  const [sfErr, setSfErr] = useState({})
  const createStaff = useMutation({ mutationFn: () => api.post('/admin/staff', sf), onSuccess: () => { toast.success('Staff account created'); setStaffOpen(false); setSf({ name: '', email: '', password: '', role: 'checkin' }); qc.invalidateQueries({ queryKey: ['admin', 'users'] }) }, onError: (e) => setSfErr(Object.keys(e.fieldErrors || {}).length ? e.fieldErrors : { form: e.message }) })
  return (
    <div className="space-y-4"><div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Users</h1><Button onClick={() => { setSfErr({}); setStaffOpen(true) }}><Plus className="h-4 w-4" />Add staff</Button></div>
      <Modal open={staffOpen} onClose={() => setStaffOpen(false)} title="Create staff account">
        <form className="space-y-3" noValidate onSubmit={(e) => { e.preventDefault(); setSfErr({}); createStaff.mutate() }}>
          {sfErr.form && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{sfErr.form}</p>}
          <Select label="Role" value={sf.role} onChange={(e) => setSf({ ...sf, role: e.target.value })}><option value="checkin">Check-in staff (scans tickets at the door)</option><option value="support">Support agent (handles tickets)</option></Select>
          <Input label="Name" value={sf.name} onChange={(e) => setSf({ ...sf, name: e.target.value })} error={sfErr.name} />
          <Input label="Email" type="email" value={sf.email} onChange={(e) => setSf({ ...sf, email: e.target.value })} error={sfErr.email} />
          <Input label="Temporary password" type="password" autoComplete="new-password" hint="At least 8 characters. The person can change it after signing in." value={sf.password} onChange={(e) => setSf({ ...sf, password: e.target.value })} error={sfErr.password} />
          <Button loading={createStaff.isPending}>Create account</Button>
        </form>
      </Modal>
      <div className="flex gap-2"><Input aria-label="Search users" type="search" placeholder="Name or email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="w-64" />
        <Select aria-label="Role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }} className="w-36"><option value="">All roles</option>{['user', 'organizer', 'vendor', 'checkin', 'support', 'admin'].map((r) => <option key={r}>{r}</option>)}</Select></div>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Users" rows={data.items} columns={[{ header: 'Name', render: (u) => <><b>{u.name}</b><p className="text-xs text-gray-500">{u.email}</p></> }, { header: 'Joined', render: (u) => fmtDate(u.created_at) },
        { header: 'Role', render: (u) => <Select aria-label={`Role for ${u.name}`} value={u.role} onChange={(e) => patch.mutate({ id: u.id, role: e.target.value })}>{['user', 'organizer', 'vendor', 'checkin', 'support', 'admin'].map((r) => <option key={r}>{r}</option>)}</Select> },
        { header: 'Status', render: (u) => <Button size="sm" variant={u.is_active ? 'outline' : 'danger'} onClick={() => patch.mutate({ id: u.id, is_active: !u.is_active })}>{u.is_active ? 'Active' : 'Disabled'}</Button> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}</div>
  )
}

function Bookings() {
  useTitle('Admin: bookings')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('')
  const [kind, setKind] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'bookings', status, kind, q, page], queryFn: () => api.get('/admin/bookings', { status: status || undefined, kind: kind || undefined, q: q || undefined, page, size: 15 }), placeholderData: (p) => p })
  const cancel = useMutation({ mutationFn: (id) => api.post(`/bookings/${id}/cancel`), onSuccess: () => { toast.success('Cancelled & refunded'); qc.invalidateQueries({ queryKey: ['admin', 'bookings'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Bookings</h1>
      <div className="flex flex-wrap gap-2"><Input aria-label="Search" type="search" placeholder="Booking ID or email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="w-60" />
        <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-40"><option value="">Any status</option>{['pending', 'confirmed', 'cancelled', 'expired', 'failed'].map((s) => <option key={s}>{s}</option>)}</Select>
        <Select aria-label="Kind" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1) }} className="w-36"><option value="">Any type</option><option value="movie">Movie</option><option value="event">Event</option></Select></div>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Bookings" rows={data.items} columns={[{ header: 'Code', render: (b) => <span className="font-mono font-semibold">{b.code}</span> }, { header: 'Title', render: (b) => <>{b.title}<p className="text-xs text-gray-500">{fmtDateTime(b.starts_at)}</p></> },
        { header: 'Items', render: (b) => b.items.map((i) => i.label).join(', ') }, { header: 'Total', render: (b) => inr(b.total_paise) }, { header: 'Status', render: (b) => <Badge tone={statusTone(b.status)}>{b.status}</Badge> },
        { header: '', render: (b) => b.status === 'confirmed' && <Button size="sm" variant="outline" onClick={() => window.confirm(`Cancel ${b.code} and refund?`) && cancel.mutate(b.id)}>Cancel & refund</Button> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}</div>
  )
}

function Payments() {
  useTitle('Admin: payments')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'payments', status, q, page], queryFn: () => api.get('/admin/payments', { status: status || undefined, q: q || undefined, page, size: 15 }), placeholderData: (p) => p })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Payments</h1>
      <div className="flex gap-2"><Input aria-label="Search" type="search" placeholder="Order or payment ID" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="w-60" />
        <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-48"><option value="">Any status</option>{['created', 'paid', 'failed', 'expired', 'refunded', 'partially_refunded', 'paid_needs_refund'].map((s) => <option key={s}>{s}</option>)}</Select></div>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Payments" rows={data.items} columns={[{ header: 'Date', render: (p) => fmtDateTime(p.created_at) }, { header: 'Order', render: (p) => <span className="font-mono text-xs">{p.order_id}</span> }, { header: 'Payment', render: (p) => <span className="font-mono text-xs">{p.payment_id || '–'}</span> },
        { header: 'For', render: (p) => p.booking_code || p.purpose }, { header: 'Amount', render: (p) => inr(p.amount_paise) }, { header: 'Refunded', render: (p) => (p.refund_paise ? inr(p.refund_paise) : '–') }, { header: 'Status', render: (p) => <Badge tone={p.status === 'paid_needs_refund' ? 'red' : statusTone(p.status)}>{p.status.replace(/_/g, ' ')}</Badge> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}</div>
  )
}

function GiftCardsAdmin() {
  useTitle('Admin: gift cards')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'gift-cards', page], queryFn: () => api.get('/admin/gift-cards', { page, size: 15 }) })
  if (isLoading) return <PageSpinner />
  return <div className="space-y-4"><h1 className="text-2xl font-bold">Gift cards</h1><DataTable caption="Gift cards" rows={data.items} columns={[{ header: 'Code', render: (g) => <span className="font-mono">{g.code || '(unpaid)'}</span> }, { header: 'Recipient', render: (g) => `${g.recipient_name} <${g.recipient_email}>` }, { header: 'Value', render: (g) => inr(g.initial_paise) }, { header: 'Balance', render: (g) => inr(g.balance_paise) }, { header: 'Status', render: (g) => <Badge tone={statusTone(g.status)}>{g.status}</Badge> }]} /><Pagination page={data.page} pages={data.pages} onChange={setPage} /></div>
}

function Support() {
  useTitle('Admin: support')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('open')
  const [reply, setReply] = useState(null)
  const [text, setText] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'support', status], queryFn: () => api.get('/admin/support', { status: status || undefined, size: 30 }) })
  const patch = useMutation({ mutationFn: ({ id, ...b }) => api.patch(`/admin/support/${id}`, b), onSuccess: () => { toast.success('Updated'); setReply(null); setText(''); qc.invalidateQueries({ queryKey: ['admin', 'support'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Customer support</h1>
      <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-44"><option value="">All</option>{['open', 'in_progress', 'resolved'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <DataTable caption="Tickets" rows={data.items} empty="No tickets 🎉" columns={[{ header: 'From', render: (t) => <>{t.email}<p className="text-xs text-gray-500">{fmtDateTime(t.created_at)}{t.booking_code && ` · ${t.booking_code}`}</p></> }, { header: 'Ticket', render: (t) => <><b>{t.subject}</b><p className="max-w-md text-gray-600">{t.message}</p>{t.admin_reply && <p className="mt-1 rounded bg-emerald-50 p-2 text-emerald-900">↳ {t.admin_reply}</p>}</> },
        { header: 'Status', render: (t) => <Badge tone={statusTone(t.status)}>{t.status.replace('_', ' ')}</Badge> }, { header: '', render: (t) => <div className="flex gap-1"><Button size="sm" onClick={() => { setReply(t); setText(t.admin_reply || '') }}>Reply</Button>{t.status !== 'resolved' && <Button size="sm" variant="outline" onClick={() => patch.mutate({ id: t.id, status: 'resolved' })}>Resolve</Button>}</div> }]} />}
      <Modal open={!!reply} onClose={() => setReply(null)} title={`Reply: ${reply?.subject}`}><Textarea label="Your reply" value={text} onChange={(e) => setText(e.target.value)} /><Button className="mt-3" loading={patch.isPending} disabled={!text.trim()} onClick={() => patch.mutate({ id: reply.id, admin_reply: text, status: 'in_progress' })}>Send reply</Button></Modal></div>
  )
}

export default function Admin() {
  return (
    <PortalShell title="Admin panel" links={links}>
      <Routes>
        <Route index element={<MarketDashboard />} />
        <Route path="vendors" element={<Vendors />} /><Route path="vendor-managers" element={<VendorManagers />} /><Route path="theaters" element={<TheaterApprovals />} /><Route path="show-review" element={<ShowReview />} /><Route path="movie-requests" element={<MovieRequestsAdmin />} />
        <Route path="payouts" element={<Payouts />} /><Route path="commissions" element={<Commissions />} /><Route path="audit-logs" element={<AuditLogs />} />
        {Object.values(RESOURCES).map((cfg) => <Route key={cfg.path} path={cfg.path} element={<ResourceManager key={cfg.path} cfg={cfg} />} />)}
        <Route path="screens" element={<Screens />} /><Route path="shows" element={<Shows />} /><Route path="events" element={<Events />} /><Route path="events/new" element={<EventForm backTo="/admin/events" />} /><Route path="organizers" element={<Organizers />} />
        <Route path="users" element={<UsersPage />} /><Route path="bookings" element={<Bookings />} /><Route path="payments" element={<Payments />} /><Route path="gift-cards" element={<GiftCardsAdmin />} /><Route path="support" element={<Support />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </PortalShell>
  )
}
