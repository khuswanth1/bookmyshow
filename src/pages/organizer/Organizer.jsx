import { useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BarChart3, CalendarPlus, MapPin, Plus, ScanLine, Ticket, Trash2 } from 'lucide-react'
import { api } from '../../lib/api'
import { useToast } from '../../context/providers'
import { useTitle } from '../../hooks'
import { PortalShell, BarChart, DataTable } from '../../components/portal'
import { Badge, Button, ErrorState, Input, Modal, PageSpinner, Pagination, Select, Stat, Textarea, statusTone } from '../../components/ui'
import { fmtDate, fmtDateTime, inr, SECTIONS } from '../../lib/format'
import { minLen, required, validate } from '../../lib/validators'

const links = [
  ['/organizer', 'Dashboard', BarChart3, true], ['/organizer/events', 'My events', Ticket], ['/organizer/events/new', 'Create event', CalendarPlus],
  ['/organizer/venues', 'Venues', MapPin], ['/organizer/bookings', 'Bookings', Ticket],
]

function Dashboard() {
  useTitle('Organizer dashboard')
  const [days, setDays] = useState(30)
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['org-analytics', days], queryFn: () => api.get('/organizer/analytics', { days }) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Sales overview</h1>
        <Select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></Select></div>
      <div className="grid gap-4 sm:grid-cols-3"><Stat label="Revenue" value={inr(data.revenue_paise)} sub="Ticket value after discounts" /><Stat label="Bookings" value={data.bookings} /><Stat label="Tickets sold" value={data.tickets} /></div>
      <section className="card p-5"><h2 className="mb-3 font-bold">Revenue by day</h2><BarChart title="Revenue by day" data={data.daily.map((d) => ({ label: fmtDate(d.date, { day: 'numeric', month: 'short' }), value: d.revenue_paise / 100 }))} format={(v) => `₹${v.toLocaleString('en-IN')}`} /></section>
      <section><h2 className="mb-3 font-bold">Top events by revenue</h2>
        <DataTable caption="Top events" rows={data.events} empty="Create your first event to see sales here." columns={[
          { header: 'Event', render: (e) => <Link className="font-semibold text-brand" to={`/organizer/events/${e.id}/edit`}>{e.title}</Link> },
          { header: 'Sold / capacity', render: (e) => <div className="w-40"><div className="h-2 overflow-hidden rounded bg-gray-200"><div className="h-full bg-brand" style={{ width: `${e.capacity ? (e.sold / e.capacity) * 100 : 0}%` }} /></div><span className="text-xs text-gray-500">{e.sold} / {e.capacity}</span></div> },
          { header: 'Revenue', render: (e) => inr(e.revenue_paise) }]} /></section>
    </div>
  )
}

function Events() {
  useTitle('My events')
  const [page, setPage] = useState(1)
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['org-events', page], queryFn: () => api.get('/organizer/events', { page, size: 10 }) })
  const cancel = useMutation({ mutationFn: (id) => api.post(`/organizer/events/${id}/cancel`), onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ['org-events'] }) }, onError: (e) => toast.error(e.message) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <div className="space-y-4"><div className="flex items-center justify-between"><h1 className="text-2xl font-bold">My events</h1><Link to="/organizer/events/new"><Button><Plus className="h-4 w-4" />New event</Button></Link></div>
      <DataTable caption="Events" rows={data.items} empty="No events yet." columns={[
        { header: 'Event', render: (e) => <><b>{e.title}</b><p className="text-xs text-gray-500">{e.category.name} · {e.city.name}</p></> },
        { header: 'When', render: (e) => fmtDateTime(e.starts_at) },
        { header: 'Tickets', render: (e) => e.ticket_types.map((t) => <p key={t.id} className="text-xs">{t.name}: {t.sold}/{t.total} · {inr(t.price_paise)}</p>) },
        { header: 'Status', render: (e) => <Badge tone={statusTone(e.status)}>{e.status}</Badge> },
        { header: '', render: (e) => <div className="flex gap-2"><Link to={`/organizer/events/${e.id}/edit`}><Button size="sm" variant="outline">Edit</Button></Link>
          <Link to={`/organizer/events/${e.id}/door`}><Button size="sm" variant="outline"><ScanLine className="h-4 w-4" />Door</Button></Link>
          {e.status !== 'cancelled' && <Button size="sm" variant="ghost" onClick={() => window.confirm('Cancel this event and refund all bookings?') && cancel.mutate(e.id)}>Cancel</Button>}</div> }]} />
      <Pagination page={data.page} pages={data.pages} onChange={setPage} /></div>
  )
}

const emptyEvent = { title: '', description: '', section: 'events', category_id: '', language_id: '', city_id: '', venue_id: '', venue_name: '', address: '', lat: '', lng: '', starts_at: '', ends_at: '', age_limit: 'All ages', performers: '', color_a: '#111827', color_b: '#7c3aed', image_url: '', tickets: [{ name: 'General', price: '500', total: '100', max: '10' }] }
const toLocal = (iso) => { if (!iso) return ''; const d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16) }

export function EventForm({ backTo = '/organizer/events' }) {
  const { id } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  useTitle(id ? 'Edit event' : 'Create event')
  const cities = useQuery({ queryKey: ['cities'], queryFn: () => api.get('/cities') })
  const langs = useQuery({ queryKey: ['languages'], queryFn: () => api.get('/languages') })
  const venues = useQuery({ queryKey: ['org-venues'], queryFn: () => api.get('/organizer/venues') })
  const [v, setV] = useState(emptyEvent)
  const [errs, setErrs] = useState({})
  const cats = useQuery({ queryKey: ['categories', v.section], queryFn: () => api.get('/categories', { section: v.section }) })
  const existing = useQuery({
    queryKey: ['org-event', id], enabled: !!id,
    queryFn: async () => {
      const list = await api.get('/organizer/events', { size: 100 })
      const e = list.items.find((x) => String(x.id) === id)
      if (!e) throw new Error('Event not found')
      setV({ ...emptyEvent, ...e, language_id: e.language?.id || '', category_id: e.category.id, city_id: e.city.id, venue_id: e.venue_id || '', lat: e.lat ?? '', lng: e.lng ?? '', starts_at: toLocal(e.starts_at), ends_at: toLocal(e.ends_at), performers: (e.performers || []).join(', '), image_url: e.image_url || '',
        tickets: e.ticket_types.map((t) => ({ id: t.id, name: t.name, price: String(t.price_paise / 100), total: String(t.total), max: String(t.max_per_booking), sold: t.sold + t.held })) })
      return e
    },
  })
  const set = (k) => (e) => { setV({ ...v, [k]: e.target.value }); setErrs({ ...errs, [k]: '' }) }
  const setT = (i, k, val) => setV({ ...v, tickets: v.tickets.map((t, j) => (j === i ? { ...t, [k]: val } : t)) })

  const save = useMutation({
    mutationFn: (body) => (id ? api.put(`/organizer/events/${id}`, body) : api.post('/organizer/events', body)),
    onSuccess: (e) => { toast.success(id ? 'Event updated' : e.status === 'pending' ? 'Event submitted for review' : 'Event published'); qc.invalidateQueries({ queryKey: ['org-events'] }); qc.invalidateQueries({ queryKey: ['admin', 'events'] }); nav(backTo) },
    onError: (e) => { setErrs(e.fieldErrors); toast.error(e.message) },
  })
  const submit = (e) => {
    e.preventDefault()
    const er = validate({ title: [minLen(3, 'Title')], category_id: [required('Category')], city_id: [required('City')], starts_at: [required('Start time')], venue_name: [(x, all) => (all.venue_id || x.trim() ? '' : 'Venue name is required')] }, v)
    v.tickets.forEach((t, i) => { if (!t.name.trim()) er[`t${i}`] = 'Name every ticket type'; else if (!(Number(t.total) >= 1)) er[`t${i}`] = 'Quantity must be at least 1'; else if (!(Number(t.price) >= 0)) er[`t${i}`] = 'Price must be 0 or more' })
    if (v.ends_at && v.ends_at <= v.starts_at) er.ends_at = 'End must be after start'
    setErrs(er)
    if (Object.keys(er).length) return
    save.mutate({
      title: v.title.trim(), description: v.description, section: v.section, category_id: Number(v.category_id), language_id: v.language_id ? Number(v.language_id) : null,
      city_id: Number(v.city_id), venue_id: v.venue_id ? Number(v.venue_id) : null, venue_name: v.venue_name, address: v.address, lat: v.lat === '' ? null : Number(v.lat), lng: v.lng === '' ? null : Number(v.lng),
      starts_at: new Date(v.starts_at).toISOString(), ends_at: v.ends_at ? new Date(v.ends_at).toISOString() : null, image_url: v.image_url || null, color_a: v.color_a, color_b: v.color_b,
      age_limit: v.age_limit, performers: v.performers.split(',').map((x) => x.trim()).filter(Boolean),
      ticket_types: v.tickets.map((t) => ({ ...(t.id ? { id: t.id } : {}), name: t.name.trim(), price_paise: Math.round(Number(t.price) * 100), total: Number(t.total), max_per_booking: Number(t.max) || 10, description: '' })),
    })
  }
  if (id && existing.isLoading) return <PageSpinner />
  if (id && existing.isError) return <ErrorState error={existing.error} />
  return (
    <form onSubmit={submit} noValidate className="space-y-5"><h1 className="text-2xl font-bold">{id ? 'Edit event' : 'Create event'}</h1>
      {id && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Editing an approved event sends it back for admin review.</p>}
      <section className="card space-y-4 p-5"><h2 className="font-bold">Basics</h2>
        <Input label="Title" value={v.title} onChange={set('title')} error={errs.title} />
        <Textarea label="Description" value={v.description} onChange={set('description')} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Select label="Section" value={v.section} onChange={(e) => setV({ ...v, section: e.target.value, category_id: '' })}>{Object.entries(SECTIONS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}</Select>
          <Select label="Category" value={v.category_id} onChange={set('category_id')} error={errs.category_id}><option value="">Select…</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Select label="Language" value={v.language_id} onChange={set('language_id')}><option value="">Not applicable</option>{langs.data?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select></div>
        <div className="grid gap-4 sm:grid-cols-3"><Input label="Starts" type="datetime-local" value={v.starts_at} onChange={set('starts_at')} error={errs.starts_at} /><Input label="Ends (optional)" type="datetime-local" value={v.ends_at} onChange={set('ends_at')} error={errs.ends_at} />
          <Select label="Age limit" value={v.age_limit} onChange={set('age_limit')}>{['All ages', '5+', '12+', '16+', '18+', '21+'].map((a) => <option key={a}>{a}</option>)}</Select></div>
        <Input label="Performers / hosts (comma separated)" value={v.performers} onChange={set('performers')} />
        <div className="grid gap-4 sm:grid-cols-3"><Input label="Image URL (optional, must be licensed)" value={v.image_url} onChange={set('image_url')} /><Input label="Gradient colour A" type="color" value={v.color_a} onChange={set('color_a')} /><Input label="Gradient colour B" type="color" value={v.color_b} onChange={set('color_b')} /></div></section>
      <section className="card space-y-4 p-5"><h2 className="font-bold">Location</h2>
        <div className="grid gap-4 sm:grid-cols-2"><Select label="City" value={v.city_id} onChange={set('city_id')} error={errs.city_id}><option value="">Select…</option>{cities.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Select label="Saved venue" value={v.venue_id} onChange={set('venue_id')}><option value="">Enter manually</option>{venues.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select></div>
        {!v.venue_id && <><Input label="Venue name" value={v.venue_name} onChange={set('venue_name')} error={errs.venue_name} /><Input label="Address" value={v.address} onChange={set('address')} />
          <div className="grid grid-cols-2 gap-4"><Input label="Latitude" type="number" step="any" value={v.lat} onChange={set('lat')} /><Input label="Longitude" type="number" step="any" value={v.lng} onChange={set('lng')} /></div></>}</section>
      <section className="card space-y-3 p-5"><div className="flex items-center justify-between"><h2 className="font-bold">Ticket inventory & pricing</h2><Button type="button" size="sm" variant="outline" onClick={() => setV({ ...v, tickets: [...v.tickets, { name: '', price: '', total: '', max: '10' }] })}><Plus className="h-4 w-4" />Add type</Button></div>
        {v.tickets.map((t, i) => (
          <div key={i} className="grid items-start gap-3 sm:grid-cols-[1fr_8rem_8rem_8rem_auto]">
            <Input label={i === 0 ? 'Name' : undefined} aria-label="Ticket name" value={t.name} onChange={(e) => setT(i, 'name', e.target.value)} error={errs[`t${i}`]} />
            <Input label={i === 0 ? 'Price (₹)' : undefined} aria-label="Price in rupees" type="number" min="0" value={t.price} onChange={(e) => setT(i, 'price', e.target.value)} />
            <Input label={i === 0 ? 'Quantity' : undefined} aria-label="Quantity" type="number" min={t.sold || 1} value={t.total} onChange={(e) => setT(i, 'total', e.target.value)} hint={t.sold ? `${t.sold} sold/held` : undefined} />
            <Input label={i === 0 ? 'Max / booking' : undefined} aria-label="Max per booking" type="number" min="1" max="20" value={t.max} onChange={(e) => setT(i, 'max', e.target.value)} />
            <Button type="button" variant="ghost" aria-label="Remove ticket type" disabled={v.tickets.length === 1 || t.sold > 0} className={i === 0 ? 'mt-6' : ''} onClick={() => setV({ ...v, tickets: v.tickets.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
          </div>))}</section>
      <div className="flex gap-3"><Button size="lg" loading={save.isPending}>{id ? 'Save changes' : 'Submit event'}</Button><Button type="button" variant="outline" size="lg" onClick={() => nav(backTo)}>Cancel</Button></div>
    </form>
  )
}

function Venues() {
  useTitle('Venues')
  const qc = useQueryClient()
  const toast = useToast()
  const cities = useQuery({ queryKey: ['cities'], queryFn: () => api.get('/cities') })
  const { data, isLoading } = useQuery({ queryKey: ['org-venues'], queryFn: () => api.get('/organizer/venues') })
  const [open, setOpen] = useState(false)
  const blank = { name: '', city_id: '', address: '', lat: '', lng: '', amenities: '' }
  const [v, setV] = useState(blank)
  const [errs, setErrs] = useState({})
  const create = useMutation({
    mutationFn: (b) => api.post('/organizer/venues', b),
    onSuccess: () => { toast.success('Venue added'); setOpen(false); setV(blank); qc.invalidateQueries({ queryKey: ['org-venues'] }) }, onError: (e) => setErrs(e.fieldErrors),
  })
  const del = useMutation({ mutationFn: (id) => api.del(`/organizer/venues/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['org-venues'] }), onError: (e) => toast.error(e.message) })
  const submit = (e) => {
    e.preventDefault()
    const er = validate({ name: [required('Name')], city_id: [required('City')], address: [required('Address')] }, v)
    setErrs(er)
    if (!Object.keys(er).length) create.mutate({ name: v.name, type: 'venue', city_id: Number(v.city_id), address: v.address, lat: v.lat === '' ? null : Number(v.lat), lng: v.lng === '' ? null : Number(v.lng), amenities: v.amenities.split(',').map((x) => x.trim()).filter(Boolean) })
  }
  if (isLoading) return <PageSpinner />
  return (
    <div className="space-y-4"><div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Venues</h1><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add venue</Button></div>
      <DataTable caption="Venues" rows={data} empty="No venues yet. Add one to reuse it across events." columns={[{ header: 'Name', render: (x) => <b>{x.name}</b> }, { header: 'City', render: (x) => x.city.name }, { header: 'Address', key: 'address' },
        { header: 'Amenities', render: (x) => x.amenities.join(', ') }, { header: '', render: (x) => <Button size="sm" variant="ghost" onClick={() => window.confirm('Delete this venue?') && del.mutate(x.id)}>Delete</Button> }]} />
      <Modal open={open} onClose={() => setOpen(false)} title="Add venue"><form onSubmit={submit} noValidate className="space-y-4">
        <Input label="Name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} error={errs.name} />
        <Select label="City" value={v.city_id} onChange={(e) => setV({ ...v, city_id: e.target.value })} error={errs.city_id}><option value="">Select…</option>{cities.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Input label="Address" value={v.address} onChange={(e) => setV({ ...v, address: e.target.value })} error={errs.address} />
        <div className="grid grid-cols-2 gap-4"><Input label="Latitude" type="number" step="any" value={v.lat} onChange={(e) => setV({ ...v, lat: e.target.value })} /><Input label="Longitude" type="number" step="any" value={v.lng} onChange={(e) => setV({ ...v, lng: e.target.value })} /></div>
        <Input label="Amenities (comma separated)" value={v.amenities} onChange={(e) => setV({ ...v, amenities: e.target.value })} />
        <Button loading={create.isPending}>Save venue</Button></form></Modal></div>
  )
}

function Bookings() {
  useTitle('Event bookings')
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['org-bookings', page], queryFn: () => api.get('/organizer/bookings', { page, size: 15 }) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Bookings</h1>
      <DataTable caption="Bookings for my events" rows={data.items} empty="No bookings yet." columns={[
        { header: 'Code', render: (b) => <span className="font-mono font-semibold">{b.code}</span> }, { header: 'Event', key: 'title' }, { header: 'Tickets', render: (b) => b.items.map((i) => `${i.label} × ${i.quantity}`).join(', ') },
        { header: 'Amount', render: (b) => inr(b.total_paise) }, { header: 'Status', render: (b) => <Badge tone={statusTone(b.status)}>{b.status}</Badge> }, { header: 'Booked', render: (b) => fmtDateTime(b.created_at) }]} />
      <Pagination page={data.page} pages={data.pages} onChange={setPage} /></div>
  )
}

function Door() {
  const { id } = useParams()
  useTitle('Door & attendees')
  const qc = useQueryClient()
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [q, setQ] = useState('')
  const [arrived, setArrived] = useState('')
  const [page, setPage] = useState(1)
  const staff = useQuery({ queryKey: ['org-staff', id], queryFn: () => api.get(`/organizer/events/${id}/staff`) })
  const att = useQuery({ queryKey: ['org-attendees', id, q, arrived, page], placeholderData: (p) => p, refetchInterval: 10000,
    queryFn: () => api.get(`/organizer/events/${id}/attendees`, { q: q || undefined, arrived: arrived === '' ? undefined : arrived, page, size: 15 }) })
  const assign = useMutation({ mutationFn: () => api.post(`/organizer/events/${id}/staff`, { email: email.trim() }), onSuccess: (r) => { qc.setQueryData(['org-staff', id], r); setEmail(''); toast.success('Staff assigned') }, onError: (e) => toast.error(e.message) })
  const remove = useMutation({ mutationFn: (sid) => api.delete(`/organizer/events/${id}/staff/${sid}`), onSuccess: (r) => qc.setQueryData(['org-staff', id], r), onError: (e) => toast.error(e.message) })
  if (att.isError) return <ErrorState error={att.error} retry={att.refetch} />
  const sum = att.data?.summary
  return (
    <div className="space-y-5">
      <div><Link to="/organizer/events" className="text-sm font-semibold text-brand">← My events</Link><h1 className="text-2xl font-bold">Door & attendees</h1></div>
      <div className="grid gap-4 sm:grid-cols-3"><Stat label="Tickets sold" value={sum?.tickets_sold ?? '…'} /><Stat label="Admitted" value={sum?.tickets_admitted ?? '…'} sub="live, refreshes every 10s" /><Stat label="Bookings arrived" value={sum ? `${sum.bookings_arrived} / ${sum.bookings}` : '…'} /></div>
      <section className="card space-y-3 p-5"><h2 className="font-bold">Check-in staff</h2>
        <p className="text-sm text-gray-500">Only the accounts you assign here can scan tickets for this event. Staff accounts are created by the platform admin.</p>
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); email.trim() && assign.mutate() }}>
          <Input label="Staff email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-72" /><Button loading={assign.isPending}>Assign</Button></form>
        <ul className="divide-y text-sm">{(staff.data || []).map((s) => <li key={s.id} className="flex items-center justify-between py-2"><span><b>{s.name}</b> <span className="text-gray-500">{s.email}</span></span>
          <Button size="sm" variant="ghost" onClick={() => window.confirm(`Remove ${s.name} from this event?`) && remove.mutate(s.id)}><Trash2 className="h-4 w-4" /><span className="sr-only">Remove {s.name}</span></Button></li>)}
          {staff.data?.length === 0 && <li className="py-2 text-gray-500">No staff assigned yet.</li>}</ul></section>
      <section className="space-y-3"><h2 className="font-bold">Attendees</h2>
        <div className="flex flex-wrap gap-2"><Input aria-label="Search attendees" type="search" placeholder="Name, email or booking code" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="w-72" />
          <Select aria-label="Arrival" value={arrived} onChange={(e) => { setArrived(e.target.value); setPage(1) }} className="w-40"><option value="">Everyone</option><option value="true">Arrived</option><option value="false">Not yet</option></Select></div>
        {att.isLoading ? <PageSpinner /> : <><DataTable caption="Attendees" rows={att.data.items} empty="No confirmed bookings match." columns={[
          { header: 'Booking', render: (a) => <b>{a.code}</b> }, { header: 'Attendee', render: (a) => <>{a.name}<p className="text-xs text-gray-500">{a.email}</p></> },
          { header: 'Tickets', render: (a) => a.items.map((i) => <p key={i} className="text-xs">{i}</p>) },
          { header: 'Entry', render: (a) => a.checked_in_at ? <Badge tone="green">In · {fmtDateTime(a.checked_in_at)}</Badge> : <Badge>Not yet</Badge> }]} />
          <Pagination page={att.data.page} pages={att.data.pages} onChange={setPage} /></>}</section>
    </div>
  )
}

export default function Organizer() {
  return (
    <PortalShell title="Organizer portal" links={links}>
      <Routes>
        <Route index element={<Dashboard />} /><Route path="events" element={<Events />} />
        <Route path="events/new" element={<EventForm />} /><Route path="events/:id/edit" element={<EventForm />} /><Route path="events/:id/door" element={<Door />} />
        <Route path="venues" element={<Venues />} /><Route path="bookings" element={<Bookings />} /><Route path="*" element={<Navigate to="/organizer" replace />} />
      </Routes>
    </PortalShell>
  )
}
