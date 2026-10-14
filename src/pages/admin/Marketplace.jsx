import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Plus } from 'lucide-react'
import { api, download } from '../../lib/api'
import { useToast } from '../../context/providers'
import { useTitle } from '../../hooks'
import { BarChart, DataTable } from '../../components/portal'
import { Badge, Button, ErrorState, Input, Modal, PageSpinner, Pagination, Select, Stat, Textarea, Toggle, statusTone } from '../../components/ui'
import { fmtDate, fmtDateTime, inr } from '../../lib/format'

/** Ask for a mandatory reason (reject / suspend) */
function ReasonModal({ ask, onClose, onSubmit, busy }) {
  const [reason, setReason] = useState('')
  return (
    <Modal open={!!ask} onClose={onClose} title={ask?.title || ''}>
      <Textarea label="Reason (shown to the vendor and kept in the audit log)" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} data-autofocus />
      <div className="mt-4 flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Back</Button>
        <Button variant="danger" disabled={reason.trim().length < 3} loading={busy} onClick={() => { onSubmit(reason.trim()); setReason('') }}>Confirm</Button></div>
    </Modal>
  )
}

export function MarketDashboard() {
  useTitle('Admin dashboard')
  const [days, setDays] = useState(30)
  const r = useQuery({ queryKey: ['admin-market', days], queryFn: () => api.get('/admin/reports/marketplace', { days }) })
  const s = useQuery({ queryKey: ['admin-report', days], queryFn: () => api.get('/admin/reports/summary', { days }) })
  const toast = useToast()
  if (r.isLoading || s.isLoading) return <PageSpinner />
  if (r.isError) return <ErrorState error={r.error} retry={r.refetch} />
  const d = r.data, a = d.approvals
  const queue = [['Vendor applications', a.vendors_pending, '/admin/vendors'], ['Theaters to approve', a.theaters_pending, '/admin/theaters'], ['Shows to review', a.shows_pending, '/admin/show-review'],
    ['Movie requests', a.movie_requests_pending, '/admin/movie-requests'], ['Payout requests', a.payouts_pending, '/admin/payouts']]
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex flex-wrap gap-2"><Link to="/admin/movies?new=1"><Button size="sm"><Plus className="h-4 w-4" />Create movie</Button></Link><Link to="/admin/events/new"><Button size="sm"><Plus className="h-4 w-4" />Create event</Button></Link>
          <Button variant="outline" size="sm" onClick={() => download('/admin/reports/bookings.csv', { days }, 'bookings.csv').catch((e) => toast.error(e.message))}><Download className="h-4 w-4" />Bookings CSV</Button>
          <Select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></Select></div></div>
      <section aria-label="Approval queue" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {queue.map(([l, n, to]) => <Link key={l} to={to} className={`card p-4 transition hover:shadow-md ${n ? 'ring-2 ring-amber-400' : ''}`}><p className="text-xs font-medium uppercase text-gray-500">{l}</p><p className={`text-3xl font-bold ${n ? 'text-amber-600' : ''}`}>{n}</p></Link>)}</section>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Gross sales" value={inr(d.gross_paise)} sub={`${d.bookings} bookings`} /><Stat label="Platform commission" value={inr(d.commission_paise)} /><Stat label="Fees & GST collected" value={inr(d.fees_paise)} />
        <Stat label="Refunds" value={inr(d.refunded_paise)} sub={`${d.refunds} refunds · ${d.cancelled_bookings} cancellations`} /></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Approved vendors" value={d.totals.vendors} /><Stat label="Live theaters" value={d.totals.theaters} /><Stat label="Customers" value={d.totals.customers} /><Stat label="Payouts" value={inr(d.payouts_paid_paise)} sub={`${inr(d.payouts_pending_paise)} awaiting`} /></div>
      <section className="card p-5"><h2 className="mb-3 font-bold">Gross sales by day</h2><BarChart title="Gross sales by day" data={d.daily.map((x) => ({ label: fmtDate(x.date, { day: 'numeric', month: 'short' }), value: x.gross_paise / 100 }))} format={(v) => `₹${v.toLocaleString('en-IN')}`} /></section>
      <div className="grid gap-5 lg:grid-cols-2">
        <section><h2 className="mb-2 font-bold">Top movies</h2><DataTable caption="Top movies" rows={s.data.top_movies} empty="No movie sales yet." columns={[{ header: 'Movie', key: 'title' }, { header: 'Bookings', key: 'bookings' }, { header: 'Gross', render: (x) => inr(x.gross_paise) }]} /></section>
        <section><h2 className="mb-2 font-bold">Top cities</h2><DataTable caption="Top cities" rows={s.data.top_cities} empty="No sales yet." columns={[{ header: 'City', key: 'city' }, { header: 'Bookings', key: 'bookings' }, { header: 'Gross', render: (x) => inr(x.gross_paise) }]} /></section></div>
    </div>
  )
}

export function Vendors() {
  useTitle('Admin: vendors')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const [page, setPage] = useState(1)
  const [ask, setAsk] = useState(null)
  const [pct, setPct] = useState(null) // {vendor}
  const [pctVal, setPctVal] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['admin-vendors', status, page], queryFn: () => api.get('/admin/vendors', { status: status || undefined, page, size: 12 }), placeholderData: (p) => p })
  const review = useMutation({
    mutationFn: ({ id, ...b }) => api.patch(`/admin/vendors/${id}`, b),
    onSuccess: () => { toast.success('Vendor updated'); setAsk(null); setPct(null); qc.invalidateQueries({ queryKey: ['admin-vendors'] }); qc.invalidateQueries({ queryKey: ['admin-market'] }) }, onError: (e) => toast.error(e.message),
  })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Theater vendors</h1>
      <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-44"><option value="">All</option>{['pending', 'approved', 'rejected', 'suspended'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Vendors" rows={data.items} empty="No vendors in this state." columns={[
        { header: 'Business', render: (v) => <><b>{v.business_name}</b><p className="text-xs text-gray-500">GST {v.gst_number || '–'} · PAN {v.pan_number || '–'}</p>{v.description && <p className="max-w-xs text-xs text-gray-500">{v.description}</p>}</> },
        { header: 'Owner', render: (v) => <>{v.user_name}<p className="text-xs text-gray-500">{v.user_email} · {v.contact_phone}</p></> }, { header: 'Applied', render: (v) => fmtDate(v.created_at) },
        { header: 'Theaters', key: 'theaters' }, { header: 'Commission', render: (v) => (v.commission_pct != null ? `${v.commission_pct}%` : 'default') },
        { header: 'Status', render: (v) => <><Badge tone={statusTone(v.status)}>{v.status}</Badge>{v.rejection_reason && <p className="mt-1 max-w-[12rem] text-xs text-gray-500">{v.rejection_reason}</p>}</> },
        { header: '', render: (v) => <div className="flex flex-wrap gap-1">
          {v.status !== 'approved' && <Button size="sm" onClick={() => review.mutate({ id: v.id, status: 'approved' })}>Approve</Button>}
          {v.status === 'pending' && <Button size="sm" variant="outline" onClick={() => setAsk({ title: `Reject ${v.business_name}`, id: v.id, status: 'rejected' })}>Reject</Button>}
          {v.status === 'approved' && <Button size="sm" variant="outline" onClick={() => setAsk({ title: `Suspend ${v.business_name}`, id: v.id, status: 'suspended' })}>Suspend</Button>}
          {v.status === 'approved' && <Button size="sm" variant="ghost" onClick={() => { setPct(v); setPctVal(v.commission_pct ?? '') }}>Commission</Button>}</div> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}
      <ReasonModal ask={ask} onClose={() => setAsk(null)} busy={review.isPending} onSubmit={(reason) => review.mutate({ id: ask.id, status: ask.status, reason })} />
      <Modal open={!!pct} onClose={() => setPct(null)} title={`Commission: ${pct?.business_name}`}>
        <Input label="Override commission %" type="number" min="0" max="60" step="0.5" value={pctVal} onChange={(e) => setPctVal(e.target.value)} hint="Applies to future bookings only. Set in Commissions & settings for the platform default." />
        <Button className="mt-4" loading={review.isPending} disabled={pctVal === ''} onClick={() => review.mutate({ id: pct.id, status: 'approved', commission_pct: Number(pctVal) })}>Save</Button></Modal>
    </div>
  )
}

export function Theaters() {
  useTitle('Admin: theaters')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [ask, setAsk] = useState(null)
  const { data, isLoading } = useQuery({ queryKey: ['admin-theaters', status, page, q], queryFn: () => api.get('/admin/theaters', { status: status || undefined, page, size: 12, q: q || undefined }), placeholderData: (p) => p })
  const review = useMutation({
    mutationFn: ({ id, ...b }) => api.patch(`/admin/theaters/${id}/review`, b),
    onSuccess: () => { toast.success('Theater updated'); setAsk(null); qc.invalidateQueries({ queryKey: ['admin-theaters'] }); qc.invalidateQueries({ queryKey: ['admin-market'] }) }, onError: (e) => toast.error(e.message),
  })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Theater approvals</h1>
      <div className="flex gap-2"><Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-44"><option value="">All</option>{['pending', 'approved', 'rejected', 'suspended'].map((s) => <option key={s}>{s}</option>)}</Select>
        <Input aria-label="Search" type="search" placeholder="Theater name" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} className="w-56" /></div>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Theaters" rows={data.items} empty="Nothing to review." columns={[
        { header: 'Theater', render: (t) => <><b>{t.name}</b><p className="text-xs text-gray-500">{t.address}, {t.city.name}</p></> }, { header: 'Vendor', render: (t) => t.vendor_name || <span className="text-gray-400">Platform-owned</span> },
        { header: 'Screens', key: 'screens_count' }, { header: 'Submitted', render: (t) => (t.submitted_at ? fmtDate(t.submitted_at) : '–') },
        { header: 'Status', render: (t) => <><Badge tone={statusTone(t.approval_status)}>{t.approval_status}</Badge>{t.rejection_reason && <p className="mt-1 max-w-[12rem] text-xs text-gray-500">{t.rejection_reason}</p>}</> },
        { header: '', render: (t) => <div className="flex gap-1">{t.approval_status !== 'approved' && <Button size="sm" onClick={() => review.mutate({ id: t.id, status: 'approved' })}>Approve</Button>}
          {t.approval_status === 'pending' && <Button size="sm" variant="outline" onClick={() => setAsk({ title: `Reject ${t.name}`, id: t.id, status: 'rejected' })}>Reject</Button>}
          {t.approval_status === 'approved' && <Button size="sm" variant="outline" onClick={() => setAsk({ title: `Suspend ${t.name}`, id: t.id, status: 'suspended' })}>Suspend</Button>}</div> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}
      <ReasonModal ask={ask} onClose={() => setAsk(null)} busy={review.isPending} onSubmit={(reason) => review.mutate({ id: ask.id, status: ask.status, reason })} />
    </div>
  )
}

export function ShowReview() {
  useTitle('Admin: show review')
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['admin-pending-shows'], queryFn: () => api.get('/admin/shows/pending') })
  const review = useMutation({
    mutationFn: (b) => api.post('/admin/shows/review', b),
    onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ['admin-pending-shows'] }); qc.invalidateQueries({ queryKey: ['admin-market'] }) }, onError: (e) => toast.error(e.message),
  })
  if (isLoading) return <PageSpinner />
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Show listing review</h1>
      <p className="text-sm text-gray-500">Only needed when “Require admin review of new shows” is on in Commissions & settings. Pending shows are hidden from customers.</p>
      <DataTable caption="Pending shows" rows={data.map((g, i) => ({ ...g, id: i }))} empty="No shows waiting for review." columns={[
        { header: 'Theater', key: 'theater' }, { header: 'Movie', key: 'movie' }, { header: 'Shows', key: 'shows' }, { header: 'From', render: (g) => fmtDateTime(g.first) }, { header: 'To', render: (g) => fmtDateTime(g.last) },
        { header: '', render: (g) => <div className="flex gap-1"><Button size="sm" onClick={() => review.mutate({ show_ids: g.show_ids, status: 'approved' })}>Approve</Button>
          <Button size="sm" variant="outline" onClick={() => window.confirm('Reject and cancel these shows?') && review.mutate({ show_ids: g.show_ids, status: 'rejected' })}>Reject</Button></div> }]} /></div>
  )
}

export function MovieRequestsAdmin() {
  useTitle('Admin: movie requests')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const [note, setNote] = useState({})
  const { data, isLoading } = useQuery({ queryKey: ['admin-movie-requests', status], queryFn: () => api.get('/admin/movie-requests', { status: status || undefined, size: 50 }) })
  const review = useMutation({
    mutationFn: ({ id, ...b }) => api.patch(`/admin/movie-requests/${id}`, b),
    onSuccess: () => { toast.success('Request reviewed'); qc.invalidateQueries({ queryKey: ['admin-movie-requests'] }); qc.invalidateQueries({ queryKey: ['admin-market'] }); qc.invalidateQueries({ queryKey: ['admin', 'movies'] }) }, onError: (e) => toast.error(e.message),
  })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Movie requests</h1>
      <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-44"><option value="">All</option>{['pending', 'approved', 'rejected'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <DataTable caption="Movie requests" rows={data.items} empty="No requests." columns={[
        { header: 'Movie', render: (r) => <><b>{r.title}</b><p className="text-xs text-gray-500">{r.certificate} · {r.duration_min} min · {r.languages || '–'} · {r.release_date ? fmtDate(r.release_date) : 'date TBD'}</p>{r.synopsis && <p className="max-w-sm text-xs text-gray-500">{r.synopsis}</p>}{r.notes && <p className="max-w-sm text-xs italic text-gray-500">“{r.notes}”</p>}</> },
        { header: 'Vendor', key: 'vendor_name' }, { header: 'Status', render: (r) => <Badge tone={statusTone(r.status)}>{r.status}</Badge> },
        { header: '', render: (r) => r.status === 'pending' ? <div className="flex min-w-56 flex-col gap-2"><Input aria-label="Note to vendor" placeholder="Note to vendor (optional)" value={note[r.id] || ''} onChange={(e) => setNote({ ...note, [r.id]: e.target.value })} />
          <div className="flex gap-1"><Button size="sm" onClick={() => review.mutate({ id: r.id, status: 'approved', admin_note: note[r.id] || null })}>Approve & add movie</Button><Button size="sm" variant="outline" onClick={() => review.mutate({ id: r.id, status: 'rejected', admin_note: note[r.id] || null })}>Reject</Button></div></div> : r.admin_note }]} />}</div>
  )
}

export function Payouts() {
  useTitle('Admin: payouts')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('requested')
  const [page, setPage] = useState(1)
  const [proc, setProc] = useState(null)
  const [ref, setRef] = useState('')
  const [note, setNote] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['admin-payouts', status, page], queryFn: () => api.get('/admin/payouts', { status: status || undefined, page, size: 12 }), placeholderData: (p) => p })
  const m = useMutation({
    mutationFn: (b) => api.patch(`/admin/payouts/${proc.p.id}`, b),
    onSuccess: () => { toast.success('Payout updated'); setProc(null); setRef(''); setNote(''); qc.invalidateQueries({ queryKey: ['admin-payouts'] }); qc.invalidateQueries({ queryKey: ['admin-market'] }) }, onError: (e) => toast.error(e.message),
  })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Vendor payouts</h1>
      <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-44"><option value="">All</option>{['requested', 'paid', 'rejected'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Payouts" rows={data.items} empty="No payouts." columns={[
        { header: 'Requested', render: (p) => fmtDateTime(p.created_at) }, { header: 'Vendor', key: 'vendor_name' }, { header: 'Amount', render: (p) => <b>{inr(p.amount_paise)}</b> },
        { header: 'Status', render: (p) => <Badge tone={p.status === 'paid' ? 'green' : p.status === 'rejected' ? 'red' : 'amber'}>{p.status}</Badge> }, { header: 'Reference', render: (p) => p.reference || '–' },
        { header: '', render: (p) => p.status === 'requested' && <div className="flex gap-1"><Button size="sm" onClick={() => setProc({ p, status: 'paid' })}>Mark paid</Button><Button size="sm" variant="outline" onClick={() => setProc({ p, status: 'rejected' })}>Reject</Button></div> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}
      <Modal open={!!proc} onClose={() => setProc(null)} title={proc?.status === 'paid' ? `Pay ${inr(proc?.p.amount_paise)} to ${proc?.p.vendor_name}` : 'Reject payout'}>
        {proc?.status === 'paid' && <Input label="Bank / UTR reference" value={ref} onChange={(e) => setRef(e.target.value)} hint="Transfer the money from your bank first, then record the reference here." />}
        <Textarea label="Note to vendor (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        <Button className="mt-4" loading={m.isPending} disabled={proc?.status === 'paid' && ref.trim().length < 3} onClick={() => m.mutate({ status: proc.status, reference: ref.trim() || null, note: note || null })}>{proc?.status === 'paid' ? 'Confirm payment' : 'Reject payout'}</Button></Modal>
    </div>
  )
}

export function Commissions() {
  useTitle('Admin: commissions & settings')
  const qc = useQueryClient()
  const toast = useToast()
  const [days, setDays] = useState(30)
  const c = useQuery({ queryKey: ['admin-commissions', days], queryFn: () => api.get('/admin/commissions', { days }) })
  const st = useQuery({ queryKey: ['admin-settings'], queryFn: () => api.get('/admin/settings') })
  const [f, setF] = useState(null)
  const cur = f || st.data
  const save = useMutation({
    mutationFn: () => api.put('/admin/settings', { commission_pct: Number(cur.commission_pct), require_show_approval: !!cur.require_show_approval, payout_hold_days: Number(cur.payout_hold_days), min_payout_paise: Math.round(Number(cur.min_payout_paise)) }),
    onSuccess: () => { toast.success('Settings saved'); setF(null); qc.invalidateQueries({ queryKey: ['admin-settings'] }); qc.invalidateQueries({ queryKey: ['admin-commissions'] }) }, onError: (e) => toast.error(e.message),
  })
  if (c.isLoading || st.isLoading) return <PageSpinner />
  return (
    <div className="space-y-5"><h1 className="text-2xl font-bold">Commissions & platform settings</h1>
      <form onSubmit={(e) => { e.preventDefault(); save.mutate() }} className="card space-y-4 p-5"><h2 className="font-bold">Platform settings</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Input label="Default commission (%)" type="number" min="0" max="60" step="0.5" value={cur.commission_pct} onChange={(e) => setF({ ...cur, commission_pct: e.target.value })} hint="Taken from net ticket value at vendor theaters" />
          <Input label="Payout hold (days after show)" type="number" min="0" max="60" value={cur.payout_hold_days} onChange={(e) => setF({ ...cur, payout_hold_days: e.target.value })} />
          <Input label="Minimum payout (paise)" type="number" min="0" value={cur.min_payout_paise} onChange={(e) => setF({ ...cur, min_payout_paise: e.target.value })} hint={`= ${inr(Number(cur.min_payout_paise))}`} /></div>
        <Toggle checked={cur.require_show_approval} onChange={(v) => setF({ ...cur, require_show_approval: v })} label="Require admin review of new vendor shows before they go public" />
        <div><Button loading={save.isPending} disabled={!f}>Save settings</Button></div></form>
      <div className="flex items-center justify-between"><h2 className="font-bold">Commission by vendor</h2><Select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={365}>Last year</option></Select></div>
      <DataTable caption="Commissions" rows={c.data.vendors.map((v) => ({ ...v, id: v.vendor_id }))} empty="No vendors yet." columns={[{ header: 'Vendor', key: 'vendor' }, { header: 'Rate', render: (v) => `${v.commission_pct}%` }, { header: 'Bookings', key: 'bookings' },
        { header: 'Gross', render: (v) => inr(v.gross_paise) }, { header: 'Platform commission', render: (v) => <b>{inr(v.commission_paise)}</b> }, { header: 'Vendor share', render: (v) => inr(v.vendor_share_paise) }, { header: 'Paid out', render: (v) => inr(v.paid_out_paise) }]} />
      <p className="text-sm text-gray-500">Total commission in period: <b>{inr(c.data.total_commission_paise)}</b></p></div>
  )
}

export function AuditLogs() {
  useTitle('Admin: audit logs')
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const { data, isLoading } = useQuery({ queryKey: ['admin-audit', page, action, actor], queryFn: () => api.get('/admin/audit-logs', { page, size: 20, action: action || undefined, actor: actor || undefined }), placeholderData: (p) => p })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Audit logs</h1><p className="text-sm text-gray-500">Append-only record of approvals, financial actions, role changes and settings changes.</p>
      <div className="flex flex-wrap gap-2"><Input aria-label="Action prefix" placeholder="Action, e.g. vendor. or payout." value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }} className="w-60" /><Input aria-label="Actor email" placeholder="Actor email" value={actor} onChange={(e) => { setActor(e.target.value); setPage(1) }} className="w-60" /></div>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Audit log" rows={data.items} empty="No entries." columns={[
        { header: 'When', render: (l) => fmtDateTime(l.created_at) }, { header: 'Actor', render: (l) => <>{l.actor_email || 'system'}<p className="text-xs text-gray-500">{l.actor_role || ''} {l.ip && `· ${l.ip}`}</p></> },
        { header: 'Action', render: (l) => <span className="font-mono text-xs font-semibold">{l.action}</span> }, { header: 'Entity', render: (l) => (l.entity_type ? `${l.entity_type}${l.entity_id ? ` #${l.entity_id}` : ''}` : '–') },
        { header: 'Details', render: (l) => <code className="block max-w-sm truncate text-xs text-gray-500" title={JSON.stringify(l.meta)}>{l.meta ? JSON.stringify(l.meta) : ''}</code> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}</div>
  )
}


export function VendorManagers() {
  useTitle('Admin: vendor managers')
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const [page, setPage] = useState(1)
  const [ask, setAsk] = useState(null)
  const { data, isLoading } = useQuery({ queryKey: ['admin-vendor-staff', status, page], queryFn: () => api.get('/admin/vendor-staff', { status: status || undefined, page, size: 12 }), placeholderData: (p) => p })
  const review = useMutation({ mutationFn: ({ id, ...b }) => api.patch(`/admin/vendor-staff/${id}`, b), onSuccess: () => { toast.success('Updated'); setAsk(null); qc.invalidateQueries({ queryKey: ['admin-vendor-staff'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="space-y-4"><h1 className="text-2xl font-bold">Vendor managers</h1>
      <p className="text-sm text-gray-600">Managers are created by vendors and can only sign in after you approve them. They are limited to the theaters their vendor assigned.</p>
      <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="w-44"><option value="">All</option>{['pending', 'active', 'rejected', 'disabled'].map((s) => <option key={s}>{s}</option>)}</Select>
      {isLoading ? <PageSpinner /> : <><DataTable caption="Vendor managers" rows={data.items} empty="Nothing in this state." columns={[
        { header: 'Manager', render: (m) => <><b>{m.name}</b><p className="text-xs text-gray-500">{m.email}</p></> }, { header: 'Vendor', key: 'vendor' },
        { header: 'Theaters', render: (m) => m.theater_names.join(', ') }, { header: 'Requested', render: (m) => fmtDate(m.created_at) },
        { header: 'Status', render: (m) => <><Badge tone={statusTone(m.status === 'active' ? 'approved' : m.status)}>{m.status}</Badge>{m.rejection_reason && <p className="mt-1 max-w-[12rem] text-xs text-gray-500">{m.rejection_reason}</p>}</> },
        { header: '', render: (m) => m.status === 'pending' && <div className="flex gap-1"><Button size="sm" onClick={() => review.mutate({ id: m.id, status: 'approved' })}>Approve</Button>
          <Button size="sm" variant="outline" onClick={() => setAsk({ title: `Reject ${m.name}`, id: m.id, status: 'rejected' })}>Reject</Button></div> }]} />
        <Pagination page={data.page} pages={data.pages} onChange={setPage} /></>}
      <ReasonModal ask={ask} onClose={() => setAsk(null)} busy={review.isPending} onSubmit={(reason) => review.mutate({ id: ask.id, status: ask.status, reason })} />
    </div>
  )
}
