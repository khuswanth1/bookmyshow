import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LifeBuoy, Search, Send, StickyNote, UserCheck } from 'lucide-react'
import { api } from '../../lib/api'
import { useToast } from '../../context/providers'
import { useDebounce, useTitle } from '../../hooks'
import { Badge, Button, EmptyState, ErrorState, Input, Modal, PageSpinner, Pagination, Select, Stat, Textarea, statusTone } from '../../components/ui'
import { fmtDateTime, inr } from '../../lib/format'

const QUEUES = [['active', 'Active'], ['mine', 'Mine'], ['unassigned', 'Unassigned'], ['escalated', 'Escalated'], ['resolved', 'Resolved']]
const PRIORITY_TONE = { urgent: 'red', high: 'amber', normal: 'gray', low: 'gray' }
const label = (s) => s.replace('_', ' ')

function queueParams(queue) {
  if (queue === 'mine') return { assigned: 'me', status: 'active' }
  if (queue === 'unassigned') return { assigned: 'unassigned', status: 'active' }
  return { status: queue }
}

function BookingCard({ b }) {
  return (
    <div className="rounded-xl bg-gray-50 p-3 text-sm">
      <div className="flex items-center justify-between"><b>{b.code}</b><Badge tone={statusTone(b.status)}>{b.status}</Badge></div>
      <p className="mt-1">{b.title}</p><p className="text-xs text-gray-500">{fmtDateTime(b.starts_at)}</p>
      <ul className="mt-1 text-xs">{b.items.map((i) => <li key={i}>{i}</li>)}</ul>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 text-xs"><dt className="text-gray-500">Total</dt><dd>{inr(b.total_paise)}</dd><dt className="text-gray-500">Paid via gateway</dt><dd>{inr(b.payable_paise)}</dd>
        <dt className="text-gray-500">Payment</dt><dd>{b.payment_status || '—'}</dd><dt className="text-gray-500">Refunded</dt><dd>{inr(b.refund_paise)}</dd>
        <dt className="text-gray-500">Customer</dt><dd className="truncate">{b.customer.email}</dd>
        {b.checked_in_at && <><dt className="text-gray-500">Used at venue</dt><dd>{fmtDateTime(b.checked_in_at)}</dd></>}</dl>
    </div>
  )
}

function Detail({ id, onChanged }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [body, setBody] = useState('')
  const [internal, setInternal] = useState(false)
  const [esc, setEsc] = useState(null)
  const key = ['helpdesk-ticket', id]
  const { data: t, isLoading, isError, error, refetch } = useQuery({ queryKey: key, queryFn: () => api.get(`/helpdesk/tickets/${id}`) })
  const refresh = () => { qc.invalidateQueries({ queryKey: key }); onChanged() }
  const send = useMutation({ mutationFn: () => api.post(`/helpdesk/tickets/${id}/messages`, { body, internal }), onSuccess: () => { setBody(''); refresh(); toast.success(internal ? 'Note saved' : 'Reply sent') }, onError: (e) => toast.error(e.message) })
  const patch = useMutation({ mutationFn: (b) => api.patch(`/helpdesk/tickets/${id}`, b), onSuccess: refresh, onError: (e) => toast.error(e.message) })
  const escalate = useMutation({ mutationFn: (reason) => api.post(`/helpdesk/tickets/${id}/escalate-refund`, { reason }), onSuccess: () => { setEsc(null); refresh(); toast.success('Escalated to an admin') }, onError: (e) => toast.error(e.message) })
  if (isLoading) return <PageSpinner />
  if (isError) return <ErrorState error={error} retry={refetch} />
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="text-lg font-bold">#{t.id} · {t.subject}</h2>
          <p className="text-xs text-gray-500">{t.email} · opened {fmtDateTime(t.created_at)} · {label(t.category)}</p></div>
          <Badge tone={statusTone(t.status)}>{label(t.status)}</Badge></div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Select aria-label="Status" value={t.status === 'escalated' ? '' : t.status} onChange={(e) => e.target.value && patch.mutate({ status: e.target.value })} className="w-44">
            {t.status === 'escalated' && <option value="">escalated</option>}
            {['open', 'in_progress', 'waiting_customer', 'resolved'].map((s) => <option key={s} value={s}>{label(s)}</option>)}</Select>
          <Select aria-label="Priority" value={t.priority} onChange={(e) => patch.mutate({ priority: e.target.value })} className="w-32">{['low', 'normal', 'high', 'urgent'].map((p) => <option key={p}>{p}</option>)}</Select>
          <Button size="sm" variant="outline" onClick={() => patch.mutate({ assign: t.assigned_to_id ? 'none' : 'me' })}><UserCheck className="h-4 w-4" />{t.assigned_to_id ? `Assigned: ${t.assigned_to} (release)` : 'Assign to me'}</Button>
          {t.status !== 'escalated' && t.booking && <Button size="sm" variant="ghost" onClick={() => setEsc('')}>Escalate refund</Button>}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_18rem]">
        <section aria-label="Conversation" className="space-y-3">
          <div className="card p-4"><p className="text-xs font-semibold uppercase text-gray-400">Original message</p><p className="mt-1 whitespace-pre-wrap text-sm">{t.message}</p></div>
          {t.messages.map((m) => (
            <div key={m.id} className={`rounded-xl p-3 text-sm ${m.is_internal ? 'border border-dashed border-amber-400 bg-amber-50' : m.author_role === 'customer' ? 'bg-white ring-1 ring-black/5' : 'bg-emerald-50'}`}>
              <p className="mb-1 flex items-center gap-2 text-xs text-gray-500"><b className="text-ink">{m.author_name || m.author_role}</b>{m.is_internal && <Badge tone="amber">internal note</Badge>}<span>{fmtDateTime(m.created_at)}</span></p>
              <p className="whitespace-pre-wrap">{m.body}</p></div>))}
          <form className="card space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); if (body.trim()) send.mutate() }}>
            <Textarea label={internal ? 'Internal note (customer cannot see this)' : 'Reply to customer'} rows={3} value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000} />
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} />Internal note</label>
              <Button loading={send.isPending} disabled={!body.trim()}>{internal ? <StickyNote className="h-4 w-4" /> : <Send className="h-4 w-4" />}{internal ? 'Save note' : 'Send reply'}</Button></div>
          </form>
        </section>
        <aside className="space-y-3" aria-label="Context">
          <div className="card p-4 text-sm"><h3 className="mb-1 font-bold">Customer</h3>
            {t.customer ? <><p>{t.customer.name}</p><p className="text-xs text-gray-500">{t.customer.email}</p><p className="mt-1 text-xs">{t.customer.email_verified ? <Badge tone="green">email verified</Badge> : <Badge tone="amber">email unverified</Badge>}</p></> : <p className="text-gray-500">Guest (not signed in)</p>}</div>
          <div className="card p-4"><h3 className="mb-2 font-bold">Booking</h3>
            {t.booking ? <BookingCard b={t.booking} /> : <p className="text-sm text-gray-500">{t.booking_code ? 'The cited booking code does not belong to this customer, so it is not shown. Use the lookup above if you need to check it.' : 'No booking cited.'}</p>}</div>
        </aside>
      </div>

      <Modal open={esc !== null} onClose={() => setEsc(null)} title="Escalate refund to an admin">
        <form onSubmit={(e) => { e.preventDefault(); escalate.mutate(esc) }} className="space-y-3">
          <p className="text-sm text-gray-600">Agents cannot move money. An admin reviews this and refunds the booking if it is eligible.</p>
          <Textarea label="Why should this be refunded?" rows={4} value={esc || ''} onChange={(e) => setEsc(e.target.value)} minLength={10} maxLength={1000} required />
          <Button loading={escalate.isPending} disabled={(esc || '').trim().length < 10}>Escalate</Button>
        </form>
      </Modal>
    </div>
  )
}

function Lookup() {
  const [code, setCode] = useState('')
  const [found, setFound] = useState(null)
  const [err, setErr] = useState('')
  const m = useMutation({ mutationFn: (c) => api.get('/helpdesk/bookings/lookup', { code: c }), onSuccess: (b) => { setErr(''); setFound(b) }, onError: (e) => { setFound(null); setErr(e.message) } })
  return (
    <div className="card p-3">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); code.trim().length >= 4 && m.mutate(code.trim()) }} role="search">
        <Input aria-label="Booking code" placeholder="Look up a booking code" value={code} onChange={(e) => setCode(e.target.value)} className="uppercase" />
        <Button variant="dark" loading={m.isPending}><Search className="h-4 w-4" />Find</Button></form>
      {err && <p role="alert" className="mt-2 text-sm text-red-600">{err}</p>}
      {found && <div className="mt-3"><BookingCard b={found} /><p className="mt-1 text-[11px] text-gray-400">Lookups are recorded in the audit log.</p></div>}
    </div>
  )
}

export default function Helpdesk() {
  useTitle('Support desk')
  const [queue, setQueue] = useState('active')
  const [priority, setPriority] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [sel, setSel] = useState(null)
  const dq = useDebounce(q, 300)
  const qc = useQueryClient()
  const stats = useQuery({ queryKey: ['helpdesk-stats'], queryFn: () => api.get('/helpdesk/stats'), refetchInterval: 30000 })
  const list = useQuery({ queryKey: ['helpdesk-list', queue, priority, dq, page], placeholderData: (p) => p,
    queryFn: () => api.get('/helpdesk/tickets', { ...queueParams(queue), priority: priority || undefined, q: dq || undefined, page, size: 12 }), refetchInterval: 30000 })
  const changed = () => { qc.invalidateQueries({ queryKey: ['helpdesk-list'] }); qc.invalidateQueries({ queryKey: ['helpdesk-stats'] }) }
  const s = stats.data
  return (
    <div className="container-x space-y-5 py-6">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><LifeBuoy className="h-6 w-6 text-brand" aria-hidden="true" />Support desk</h1>
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Open" value={s ? s.by_status.open ?? 0 : '…'} /><Stat label="In progress" value={s ? s.by_status.in_progress ?? 0 : '…'} />
        <Stat label="Unassigned" value={s?.unassigned ?? '…'} tone={s?.unassigned ? 'text-amber-600' : ''} /><Stat label="Mine" value={s?.mine ?? '…'} />
      </div>
      <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
        <div className="space-y-3">
          <Lookup />
          <div role="tablist" aria-label="Queues" className="flex flex-wrap gap-1">{QUEUES.map(([k, l]) => (
            <button key={k} role="tab" aria-selected={queue === k} onClick={() => { setQueue(k); setPage(1) }} className={`rounded-full px-3 py-1 text-xs font-semibold ${queue === k ? 'bg-night text-white' : 'bg-gray-100 hover:bg-gray-200'}`}>{l}</button>))}</div>
          <div className="flex gap-2"><Input aria-label="Search tickets" type="search" placeholder="Subject, email or booking" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
            <Select aria-label="Priority" value={priority} onChange={(e) => { setPriority(e.target.value); setPage(1) }} className="w-28"><option value="">Any</option>{['urgent', 'high', 'normal', 'low'].map((p) => <option key={p}>{p}</option>)}</Select></div>
          {list.isError ? <ErrorState error={list.error} retry={list.refetch} /> : list.isLoading ? <PageSpinner /> : list.data.items.length === 0 ? <EmptyState title="Nothing in this queue" icon={LifeBuoy} /> : (
            <ul className="space-y-2">{list.data.items.map((t) => (
              <li key={t.id}><button onClick={() => setSel(t.id)} aria-current={sel === t.id} className={`card w-full p-3 text-left transition hover:ring-2 hover:ring-brand/30 ${sel === t.id ? 'ring-2 ring-brand' : ''}`}>
                <div className="flex items-center justify-between gap-2"><b className="truncate text-sm">{t.subject}</b><Badge tone={PRIORITY_TONE[t.priority]}>{t.priority}</Badge></div>
                <p className="truncate text-xs text-gray-500">{t.email}</p>
                <div className="mt-1 flex items-center justify-between text-xs"><Badge tone={statusTone(t.status)}>{label(t.status)}</Badge><span className="text-gray-400">{t.assigned_to || 'unassigned'}</span></div></button></li>))}</ul>)}
          {list.data && <Pagination page={list.data.page} pages={list.data.pages} onChange={setPage} />}
        </div>
        <div>{sel ? <Detail key={sel} id={sel} onChanged={changed} /> : <EmptyState title="Select a ticket" text="Pick a ticket from the queue to read the conversation and reply." icon={LifeBuoy} />}</div>
      </div>
    </div>
  )
}
