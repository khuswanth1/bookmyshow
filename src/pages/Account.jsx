import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CalendarCheck, CreditCard, Gift, Heart, LifeBuoy, Ticket, User } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, useCity, useToast } from '../context/providers'
import { useTitle } from '../hooks'
import { Badge, Button, EmptyState, ErrorState, Input, PageSpinner, Pagination, Poster, Select, Textarea, statusTone } from '../components/ui'
import { EventCard, MovieCard } from '../components/cards'
import { clsx, fmtDate, fmtDateTime, inr } from '../lib/format'
import { minLen, password as vPassword, phone as vPhone, validate, email as vEmail } from '../lib/validators'

const TABS = [
  ['bookings', 'My bookings', Ticket], ['payments', 'Payments', CreditCard], ['favorites', 'Favorites', Heart],
  ['gift-cards', 'Gift cards', Gift], ['notifications', 'Notifications', Bell], ['support', 'Support', LifeBuoy], ['profile', 'Profile', User],
]

function Bookings() {
  const [page, setPage] = useState(1)
  const [scope, setScope] = useState('all')
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['bookings', page, scope], queryFn: () => api.get('/bookings', { page, size: 10, scope }), placeholderData: (p) => p })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <>
      <div className="mb-4 flex gap-2">{[['all', 'All'], ['upcoming', 'Upcoming'], ['past', 'Past']].map(([k, l]) => <button key={k} onClick={() => { setScope(k); setPage(1) }} aria-pressed={scope === k} className={clsx('rounded-full px-3 py-1 text-sm font-medium', scope === k ? 'bg-brand text-white' : 'bg-white ring-1 ring-gray-200')}>{l}</button>)}</div>
      {data.items.length === 0 ? <EmptyState icon={Ticket} title="No bookings yet" action={<Link to="/movies"><Button>Browse movies</Button></Link>} /> : (
        <ul className="space-y-3">
          {data.items.map((b) => (
            <li key={b.id}><Link to={`/bookings/${b.id}`} className="card flex gap-4 p-4 transition hover:shadow-md">
              <Poster a={b.poster.a} b={b.poster.b} url={b.poster.url} title={b.title} className="w-16 shrink-0" />
              <div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-2"><h3 className="truncate font-semibold">{b.title}</h3><Badge tone={statusTone(b.status)}>{b.status}</Badge></div>
                <p className="text-sm text-gray-600">{fmtDateTime(b.starts_at)}</p><p className="truncate text-xs text-gray-500">{b.venue}</p>
                <p className="mt-1 text-xs text-gray-500"><span className="font-mono font-semibold">{b.code}</span> · {b.items.map((i) => i.label).join(', ')} · {inr(b.total_paise)}</p></div>
            </Link></li>
          ))}
        </ul>
      )}
      <Pagination page={data.page} pages={data.pages} onChange={setPage} />
    </>
  )
}

function Payments() {
  const [page, setPage] = useState(1)
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['payments', page], queryFn: () => api.get('/payments', { page, size: 10 }) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  if (!data.items.length) return <EmptyState icon={CreditCard} title="No payments yet" />
  return (
    <>
      <div className="card overflow-x-auto"><table className="w-full text-left text-sm">
        <caption className="sr-only">Payment history</caption>
        <thead className="bg-gray-50 text-xs uppercase text-gray-500"><tr>{['Date', 'For', 'Payment ID', 'Method', 'Amount', 'Status'].map((h) => <th key={h} scope="col" className="px-4 py-3">{h}</th>)}</tr></thead>
        <tbody className="divide-y">{data.items.map((p) => (
          <tr key={p.id}><td className="px-4 py-3 whitespace-nowrap">{fmtDate(p.created_at, { day: 'numeric', month: 'short', year: 'numeric' })}</td>
            <td className="px-4 py-3">{p.booking_code ? <Link className="font-mono text-brand" to={`/account/bookings`}>{p.booking_code}</Link> : 'Gift card'}</td>
            <td className="px-4 py-3 font-mono text-xs">{p.payment_id}</td><td className="px-4 py-3 capitalize">{p.method || '–'}</td>
            <td className="px-4 py-3 font-semibold">{inr(p.amount_paise)}{p.refund_paise > 0 && <span className="block text-xs font-normal text-sky-700">Refunded {inr(p.refund_paise)}</span>}</td>
            <td className="px-4 py-3"><Badge tone={statusTone(p.status)}>{p.status.replace(/_/g, ' ')}</Badge></td></tr>
        ))}</tbody></table></div>
      <Pagination page={data.page} pages={data.pages} onChange={setPage} />
    </>
  )
}

function Favorites() {
  const { data, isLoading } = useQuery({ queryKey: ['favorites'], queryFn: () => api.get('/favorites') })
  if (isLoading) return <PageSpinner />
  if (!data.movies.length && !data.events.length) return <EmptyState icon={Heart} title="No favorites yet" text="Tap the heart on any movie or event to save it here." />
  return (
    <div className="space-y-6">
      {data.movies.length > 0 && <div><h3 className="mb-3 font-bold">Movies</h3><div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">{data.movies.map((m) => <MovieCard key={m.id} movie={m} className="!w-full" />)}</div></div>}
      {data.events.length > 0 && <div><h3 className="mb-3 font-bold">Events</h3><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{data.events.map((e) => <EventCard key={e.id} event={e} />)}</div></div>}
    </div>
  )
}

function GiftCards() {
  const { data, isLoading } = useQuery({ queryKey: ['gift-cards-mine'], queryFn: () => api.get('/gift-cards/mine') })
  if (isLoading) return <PageSpinner />
  return (
    <>
      <div className="mb-4 flex justify-end"><Link to="/gift-cards"><Button><Gift className="h-4 w-4" />Buy a gift card</Button></Link></div>
      {data.length === 0 ? <EmptyState icon={Gift} title="No gift cards yet" /> : (
        <ul className="grid gap-3 sm:grid-cols-2">{data.map((g) => (
          <li key={g.id} className="rounded-xl bg-gradient-to-br from-night to-brand p-5 text-white shadow">
            <p className="text-xs uppercase tracking-wider text-white/70">Gift card</p><p className="mt-1 font-mono text-lg font-bold tracking-wider">{g.code}</p>
            <p className="mt-3 text-2xl font-extrabold">{inr(g.balance_paise)} <span className="text-sm font-normal text-white/70">of {inr(g.initial_paise)}</span></p>
            <p className="mt-1 text-xs text-white/70">For {g.recipient_name} · {g.status}{g.expires_at && ` · expires ${fmtDate(g.expires_at, { day: 'numeric', month: 'short', year: 'numeric' })}`}</p>
          </li>))}</ul>
      )}
    </>
  )
}

function Notifications() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['notifications', 'list', page], queryFn: () => api.get('/notifications', { page, size: 15 }) })
  const read = useMutation({ mutationFn: () => api.post('/notifications/read-all'), onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }) })
  useEffect(() => { if (data?.items.some((n) => !n.is_read)) { const t = setTimeout(() => read.mutate(), 1500); return () => clearTimeout(t) } }, [data]) // eslint-disable-line
  if (isLoading) return <PageSpinner />
  if (!data.items.length) return <EmptyState icon={Bell} title="You're all caught up" />
  return (
    <>
      <ul className="space-y-2">{data.items.map((n) => (
        <li key={n.id} className={clsx('card p-4', !n.is_read && 'border-l-4 border-brand')}><div className="flex justify-between gap-2"><h3 className="font-semibold">{n.title}</h3><time className="shrink-0 text-xs text-gray-400">{fmtDateTime(n.created_at)}</time></div><p className="text-sm text-gray-600">{n.body}</p></li>
      ))}</ul>
      <Pagination page={data.page} pages={data.pages} onChange={setPage} />
    </>
  )
}

export function SupportForm({ defaults = {}, onDone }) {
  const { user } = useAuth()
  const toast = useToast()
  const [v, setV] = useState({ email: user?.email || '', subject: '', message: '', booking_code: '', ...defaults })
  const [errs, setErrs] = useState({})
  const m = useMutation({ mutationFn: (b) => api.post('/support/tickets', b), onSuccess: () => { toast.success('Message sent. We will get back to you soon.'); setV((x) => ({ ...x, subject: '', message: '', booking_code: '' })); onDone?.() }, onError: (e) => setErrs(e.fieldErrors?.email || e.fieldErrors?.message ? e.fieldErrors : { form: e.message }) })
  const set = (k) => (e) => { setV({ ...v, [k]: e.target.value }); setErrs({ ...errs, [k]: '' }) }
  const submit = (e) => {
    e.preventDefault()
    const er = validate({ email: [vEmail], subject: [minLen(3, 'Subject')], message: [minLen(10, 'Message')] }, v)
    setErrs(er)
    if (!Object.keys(er).length) m.mutate({ ...v, booking_code: v.booking_code || null })
  }
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {errs.form && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{errs.form}</p>}
      <Input label="Your email" type="email" value={v.email} onChange={set('email')} error={errs.email} />
      <div className="grid gap-4 sm:grid-cols-2"><Input label="Subject" value={v.subject} onChange={set('subject')} error={errs.subject} /><Input label="Booking ID (optional)" value={v.booking_code} onChange={set('booking_code')} /></div>
      <Textarea label="How can we help?" value={v.message} onChange={set('message')} error={errs.message} maxLength={4000} />
      <Button loading={m.isPending}>Send message</Button>
    </form>
  )
}

const CAL_MESSAGES = {
  connected: ['success', 'Google Calendar connected. Your confirmed bookings will be added automatically.'],
  denied: ['error', 'Calendar access was not granted, so nothing was connected.'],
  expired: ['error', 'That connection link expired. Please try connecting again.'],
  error: ['error', 'Google Calendar could not be connected. Please try again.'],
}

function CalendarCard() {
  const qc = useQueryClient()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const { data, isLoading } = useQuery({ queryKey: ['calendar'], queryFn: () => api.get('/calendar/status') })
  useEffect(() => {
    const r = params.get('calendar')
    if (!r) return
    const [kind, msg] = CAL_MESSAGES[r] || CAL_MESSAGES.error
    toast[kind](msg)
    qc.invalidateQueries({ queryKey: ['calendar'] })
    params.delete('calendar'); setParams(params, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const connect = useMutation({ mutationFn: () => api.post('/calendar/connect'), onSuccess: (r) => { window.location.href = r.url }, onError: (e) => toast.error(e.message) })
  const disconnect = useMutation({ mutationFn: () => api.delete('/calendar'), onSuccess: () => { toast.success('Google Calendar disconnected'); qc.invalidateQueries({ queryKey: ['calendar'] }) }, onError: (e) => toast.error(e.message) })
  if (isLoading || !data) return null
  return (
    <section className="card flex flex-wrap items-center justify-between gap-3 p-5" aria-label="Google Calendar">
      <div className="flex items-start gap-3"><CalendarCheck className="mt-0.5 h-5 w-5 text-brand" aria-hidden="true" />
        <div><h3 className="font-bold">Google Calendar</h3>
          <p className="text-sm text-gray-600">{!data.available ? 'Not available on this server yet.' : data.connected ? 'Connected. Every confirmed booking is added to your calendar with a reminder 2 hours before, and you get a notification when it is done.'
            : data.needs_reconnect ? 'Access was lost or revoked. Reconnect to keep adding your bookings.' : 'Add confirmed bookings to your Google Calendar automatically. We only ask permission to create and remove events we add.'}</p></div></div>
      {data.available && (data.connected
        ? <Button variant="outline" size="sm" loading={disconnect.isPending} onClick={() => window.confirm('Disconnect Google Calendar? Events already added stay on your calendar.') && disconnect.mutate()}>Disconnect</Button>
        : <Button size="sm" loading={connect.isPending} onClick={() => connect.mutate()}>{data.needs_reconnect ? 'Reconnect' : 'Connect Google Calendar'}</Button>)}
    </section>
  )
}

function VerifyEmail() {
  const { user, updateUser } = useAuth()
  const toast = useToast()
  const [sent, setSent] = useState(null)
  const [code, setCode] = useState('')
  const send = useMutation({ mutationFn: () => api.post('/users/me/email/send-code'), onSuccess: (r) => { setSent(r); toast.success('Code sent') }, onError: (e) => toast.error(e.message) })
  const verify = useMutation({ mutationFn: () => api.post('/users/me/email/verify', { code }), onSuccess: (u) => { updateUser(u); toast.success('Email verified') }, onError: (e) => toast.error(e.message) })
  if (user.email_verified) return <p className="flex items-center gap-2 text-sm text-emerald-700"><Badge tone="green">Email verified</Badge></p>
  return (
    <div className="rounded-xl bg-amber-50 p-4 text-sm" role="region" aria-label="Verify your email">
      <p className="font-semibold text-amber-900">Verify your email</p>
      <p className="mt-1 text-amber-800">Confirm {user.email} so we can reach you about your bookings and you can recover your account.</p>
      {!sent ? <Button className="mt-3" size="sm" loading={send.isPending} onClick={() => send.mutate()}>Email me a code</Button> : (
        <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); verify.mutate() }}>
          <Input label="6-digit code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} className="w-40" />
          <Button size="sm" loading={verify.isPending} disabled={code.length !== 6}>Verify</Button>
          <Button size="sm" type="button" variant="ghost" loading={send.isPending} onClick={() => send.mutate()}>Resend</Button>
          {sent.dev_code && <p className="w-full text-xs text-amber-900">Development mode (no mail server configured): your code is <b>{sent.dev_code}</b></p>}
        </form>)}
    </div>
  )
}

function TicketThread({ id, first }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [body, setBody] = useState('')
  const { data } = useQuery({ queryKey: ['ticket', id], queryFn: () => api.get(`/support/tickets/${id}`) })
  const reply = useMutation({ mutationFn: () => api.post(`/support/tickets/${id}/messages`, { body }), onSuccess: () => { setBody(''); qc.invalidateQueries({ queryKey: ['ticket', id] }); qc.invalidateQueries({ queryKey: ['tickets'] }) }, onError: (e) => toast.error(e.message) })
  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <p className="rounded-lg bg-gray-50 p-3 text-sm"><b>You:</b> {first}</p>
      {data?.messages.map((m) => <p key={m.id} className={clsx('rounded-lg p-3 text-sm', m.author_role === 'customer' ? 'bg-gray-50' : 'bg-emerald-50 text-emerald-900')}><b>{m.author_role === 'customer' ? 'You' : 'Support'}:</b> {m.body}</p>)}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); body.trim() && reply.mutate() }}>
        <Input aria-label="Reply" placeholder="Write a reply…" value={body} onChange={(e) => setBody(e.target.value)} className="flex-1" maxLength={4000} /><Button size="sm" loading={reply.isPending} disabled={!body.trim()}>Send</Button></form>
    </div>
  )
}

function Support() {
  const [open, setOpen] = useState(null)
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['tickets'], queryFn: () => api.get('/support/tickets') })
  return (
    <div className="space-y-6">
      <div className="card p-5"><h3 className="mb-3 font-bold">Contact support</h3><SupportForm onDone={() => qc.invalidateQueries({ queryKey: ['tickets'] })} /></div>
      <div><h3 className="mb-3 font-bold">Your tickets</h3>
        {!data?.length ? <p className="text-sm text-gray-500">No support tickets yet.</p> : <ul className="space-y-3">{data.map((t) => (
          <li key={t.id} className="card p-4"><div className="flex items-center justify-between gap-2"><b>{t.subject}</b><Badge tone={statusTone(t.status)}>{t.status.replace('_', ' ')}</Badge></div>
            {open === t.id ? <TicketThread id={t.id} first={t.message} /> : <><p className="mt-1 line-clamp-2 text-sm text-gray-600">{t.message}</p>{t.admin_reply && <p className="mt-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900"><b>Support:</b> {t.admin_reply}</p>}</>}
            <button className="mt-2 text-xs font-semibold text-brand" aria-expanded={open === t.id} onClick={() => setOpen(open === t.id ? null : t.id)}>{open === t.id ? 'Hide conversation' : 'View conversation / reply'}</button></li>))}</ul>}
      </div>
    </div>
  )
}

function Profile() {
  const { user, updateUser } = useAuth()
  const { cities } = useCity()
  const toast = useToast()
  const [v, setV] = useState({ name: user.name, phone: user.phone || '', city_id: user.city_id || '' })
  const [errs, setErrs] = useState({})
  const m = useMutation({ mutationFn: (b) => api.patch('/users/me', b), onSuccess: (u) => { updateUser(u); toast.success('Profile updated') }, onError: (e) => setErrs(e.fieldErrors) })
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [pwErr, setPwErr] = useState({})
  const pm = useMutation({ mutationFn: (b) => api.post('/users/me/password', b), onSuccess: () => { toast.success('Password updated'); setPw({ current_password: '', new_password: '' }) }, onError: (e) => setPwErr({ form: e.message }) })
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4 lg:col-span-2"><VerifyEmail /><CalendarCard /></div>
      <form className="card space-y-4 p-5" noValidate onSubmit={(e) => { e.preventDefault(); const er = validate({ name: [minLen(2, 'Name')], phone: [vPhone] }, v); setErrs(er); if (!Object.keys(er).length) m.mutate({ name: v.name, phone: v.phone || null, city_id: v.city_id ? Number(v.city_id) : null }) }}>
        <h3 className="font-bold">Profile</h3>
        <Input label="Email" value={user.email} disabled />
        <Input label="Name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} error={errs.name} />
        <Input label="Mobile number" value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} error={errs.phone} placeholder="+919876543210" />
        <Select label="Home city" value={v.city_id} onChange={(e) => setV({ ...v, city_id: e.target.value })}><option value="">Not set</option>{cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Button loading={m.isPending}>Save changes</Button>
      </form>
      <form className="card space-y-4 p-5" noValidate onSubmit={(e) => { e.preventDefault(); const er = validate({ new_password: [vPassword] }, pw); setPwErr(er); if (!Object.keys(er).length) pm.mutate(pw) }}>
        <h3 className="font-bold">Password</h3>
        {pwErr.form && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{pwErr.form}</p>}
        <Input label="Current password" type="password" autoComplete="current-password" hint="Leave empty if you signed up with Google" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
        <Input label="New password" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} error={pwErr.new_password} />
        <Button variant="dark" loading={pm.isPending}>Update password</Button>
      </form>
    </div>
  )
}

export default function Account() {
  const { tab = 'bookings' } = useParams()
  const nav = useNavigate()
  const { user } = useAuth()
  useTitle('My account')
  const body = { bookings: <Bookings />, payments: <Payments />, favorites: <Favorites />, 'gift-cards': <GiftCards />, notifications: <Notifications />, support: <Support />, profile: <Profile /> }[tab]
  return (
    <div className="container-x py-6">
      <div className="mb-5 flex items-center gap-4"><span className="grid h-14 w-14 place-items-center rounded-full bg-night text-2xl font-bold text-white">{user.name[0]?.toUpperCase()}</span><div><h1 className="text-2xl font-bold">Hi, {user.name.split(' ')[0]}</h1><p className="text-sm text-gray-500">{user.email}</p></div></div>
      <div className="grid gap-6 md:grid-cols-[14rem_1fr]">
        <nav aria-label="Account sections" className="card flex gap-1 overflow-x-auto p-2 md:flex-col md:overflow-visible">
          {TABS.map(([id, label, Icon]) => (
            <button key={id} onClick={() => nav(`/account/${id}`)} aria-current={tab === id ? 'page' : undefined}
              className={clsx('flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium', tab === id ? 'bg-brand/10 text-brand' : 'hover:bg-gray-100')}><Icon className="h-4 w-4" />{label}</button>
          ))}
          <Link to="/stream?tab=watchlist" className="flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium hover:bg-gray-100">▶ Watchlist</Link>
        </nav>
        <section aria-label={tab} className="min-w-0">{body || <EmptyState title="Not found" />}</section>
      </div>
    </div>
  )
}
