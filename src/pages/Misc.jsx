import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, Building2, Check, ChevronDown, Copy, Gift, Percent, Search as SearchIcon, Store } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { loadRazorpay, useTitle } from '../hooks'
import { Badge, Button, Chip, EmptyState, ErrorState, Input, PageSpinner, Select, Textarea } from '../components/ui'
import { EventCard, MovieCard, SectionHeader, VideoCard } from '../components/cards'
import { SupportForm } from './Account'
import { clsx, fmtDate, inr } from '../lib/format'
import { minLen, phoneRequired, validate } from '../lib/validators'

/* ------------------------------------------------------------ Offers & corporates */
function OfferCard({ o }) {
  const toast = useToast()
  const copy = async () => { try { await navigator.clipboard.writeText(o.code); toast.success(`Copied ${o.code}`) } catch { toast.info(`Code: ${o.code}`) } }
  const tone = { bank: 'from-indigo-700 to-sky-500', corporate: 'from-emerald-700 to-lime-500', general: 'from-rose-700 to-orange-500' }[o.kind]
  return (
    <li className="card overflow-hidden">
      <div className={`bg-gradient-to-r ${tone} p-4 text-white`}><Badge tone="dark" className="!bg-white/20 capitalize">{o.kind}{o.bank_name && ` · ${o.bank_name}`}</Badge>
        <h3 className="mt-2 text-lg font-bold">{o.title}</h3></div>
      <div className="p-4"><p className="text-sm text-gray-600">{o.description}</p>
        <ul className="mt-2 space-y-0.5 text-xs text-gray-500">
          {o.min_order_paise > 0 && <li>Minimum order {inr(o.min_order_paise)}</li>}{o.max_discount_paise && <li>Max discount {inr(o.max_discount_paise)}</li>}
          <li>Valid on {o.applies_to === 'all' ? 'movies & events' : o.applies_to === 'movie' ? 'movie tickets' : 'events, plays, sports & activities'}</li>{o.ends_at && <li>Valid till {fmtDate(o.ends_at)}</li>}</ul>
        <button onClick={copy} className="mt-3 inline-flex items-center gap-2 rounded-lg border-2 border-dashed border-brand px-3 py-1.5 font-mono text-sm font-bold text-brand hover:bg-brand/5"><Copy className="h-3.5 w-3.5" />{o.code}</button></div>
    </li>
  )
}

export function Offers({ kind, title }) {
  useTitle(title || 'Offers')
  const [tab, setTab] = useState(kind || '')
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['offers', tab], queryFn: () => api.get('/offers', { kind: tab || undefined }) })
  return (
    <div className="container-x py-6">
      <h1 className="text-2xl font-bold sm:text-3xl">{title || 'Offers & promotions'}</h1>
      <p className="mb-4 text-sm text-gray-500">Apply a code on the checkout page.</p>
      {!kind && <div className="mb-5 flex flex-wrap gap-2">{[['', 'All'], ['general', 'General'], ['bank', 'Bank offers'], ['corporate', 'Corporate vouchers']].map(([k, l]) => <Chip key={k} active={tab === k} onClick={() => setTab(k)}>{l}</Chip>)}</div>}
      {isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? <PageSpinner /> : !data.length ? <EmptyState icon={Percent} title="No offers right now" /> : <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{data.map((o) => <OfferCard key={o.id} o={o} />)}</ul>}
    </div>
  )
}

export function Corporates() {
  useTitle('Corporates')
  return (
    <>
      <div className="container-x pt-6">
        <div className="rounded-2xl bg-gradient-to-r from-night to-emerald-700 p-8 text-white sm:p-12">
          <Building2 className="mb-3 h-10 w-10" /><h1 className="text-3xl font-extrabold">BookMyShow for Corporates</h1>
          <p className="mt-2 max-w-2xl text-white/85">Reward teams and clients with movie vouchers, host private screenings and team outings, and give employees exclusive discounts.</p>
          <div className="mt-5 flex flex-wrap gap-3"><Link to="/support"><Button variant="outline" className="!border-white !bg-white !text-ink">Talk to our team</Button></Link><Link to="/gift-cards"><Button variant="outline" className="!border-white/60 !bg-transparent !text-white">Bulk gift cards</Button></Link></div>
        </div>
      </div>
      <Offers kind="corporate" title="Corporate vouchers" />
    </>
  )
}

/* ------------------------------------------------------------ Gift cards */
export function GiftCards() {
  useTitle('Gift cards')
  const { user } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [amt, setAmt] = useState(100000)
  const [v, setV] = useState({ recipient_name: '', recipient_email: '', message: '' })
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [code, setCode] = useState('')
  const [bal, setBal] = useState(null)

  const buy = async (e) => {
    e.preventDefault()
    if (!user) { toast.info('Sign in to buy a gift card'); return nav('/login', { state: { from: '/gift-cards' } }) }
    const er = validate({ recipient_name: [minLen(2, 'Recipient name')], recipient_email: [(x) => (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(x) ? '' : 'Enter a valid email')] }, v)
    setErrs(er)
    if (Object.keys(er).length) return
    setBusy(true)
    try {
      const out = await api.post('/gift-cards', { amount_paise: amt, ...v, message: v.message || null })
      const Razorpay = await loadRazorpay()
      new Razorpay({
        key: out.razorpay.key_id, amount: out.razorpay.amount, currency: 'INR', order_id: out.razorpay.order_id, name: 'BookMyShow Clone', description: 'Gift card',
        prefill: { name: user.name, email: user.email }, theme: { color: '#f84464' },
        handler: async (res) => {
          try { const r = await api.post('/payments/verify', res); toast.success(`Gift card ${r.gift_card_code} is active!`); qc.invalidateQueries({ queryKey: ['gift-cards-mine'] }); nav('/account/gift-cards') } catch (err) { toast.error(err.message) } finally { setBusy(false) }
        },
        modal: { ondismiss: () => setBusy(false) },
      }).open()
    } catch (err) { toast.error(err.message); setBusy(false) }
  }
  const check = async (e) => {
    e.preventDefault(); setBal(null)
    if (!user) return nav('/login', { state: { from: '/gift-cards' } })
    try { setBal(await api.get(`/gift-cards/check/${code.trim().toUpperCase()}`)) } catch (err) { toast.error(err.message) }
  }
  return (
    <div className="container-x py-6">
      <h1 className="text-2xl font-bold sm:text-3xl">Gift cards</h1><p className="mb-6 text-sm text-gray-500">The perfect plan for someone special. Valid for 12 months on any movie or event.</p>
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <form onSubmit={buy} noValidate className="card space-y-4 p-5">
          <div className="rounded-xl bg-gradient-to-br from-night to-brand p-6 text-white"><Gift className="h-8 w-8" /><p className="mt-6 text-3xl font-extrabold">{inr(amt)}</p><p className="text-sm text-white/75">BookMyShow Clone gift card</p></div>
          <fieldset><legend className="mb-2 text-sm font-medium">Choose an amount</legend><div className="flex flex-wrap gap-2">{[50000, 100000, 200000, 500000, 1000000].map((a) => <Chip key={a} type="button" active={amt === a} onClick={() => setAmt(a)}>{inr(a)}</Chip>)}</div></fieldset>
          <div className="grid gap-4 sm:grid-cols-2"><Input label="Recipient name" value={v.recipient_name} onChange={(e) => setV({ ...v, recipient_name: e.target.value })} error={errs.recipient_name} /><Input label="Recipient email" type="email" value={v.recipient_email} onChange={(e) => setV({ ...v, recipient_email: e.target.value })} error={errs.recipient_email} /></div>
          <Textarea label="Message (optional)" rows={2} maxLength={500} value={v.message} onChange={(e) => setV({ ...v, message: e.target.value })} />
          <Button size="lg" loading={busy}>Pay {inr(amt)}</Button>
        </form>
        <aside className="space-y-4">
          <form onSubmit={check} className="card space-y-3 p-5"><h2 className="font-bold">Check balance</h2><Input aria-label="Gift card code" placeholder="GCXXXXXXXXXXXX" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} /><Button variant="dark" disabled={code.length < 6}>Check</Button>
            {bal && <p className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">Balance <b>{inr(bal.balance_paise)}</b> ({bal.status}){bal.expires_at && <> · expires {fmtDate(bal.expires_at)}</>}</p>}</form>
          <Link to="/account/gift-cards" className="card block p-5 font-semibold text-brand hover:shadow-md">View my gift cards ›</Link>
        </aside>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ ListYourShow */
export function ListYourShow() {
  useTitle('ListYourShow')
  const { user } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const qc = useQueryClient()
  const profile = useQuery({ queryKey: ['organizer-profile'], enabled: !!user, queryFn: () => api.get('/organizer/profile') })
  const [v, setV] = useState({ company_name: '', contact_phone: '', website: '', gst_number: '', description: '' })
  const [errs, setErrs] = useState({})
  const m = useMutation({
    mutationFn: (b) => api.post('/organizer/register', b),
    onSuccess: () => { toast.success('Application submitted!'); qc.invalidateQueries({ queryKey: ['organizer-profile'] }) },
    onError: (e) => setErrs(Object.keys(e.fieldErrors).length ? e.fieldErrors : { form: e.message }),
  })
  const submit = (e) => {
    e.preventDefault()
    if (!user) return nav('/login', { state: { from: '/list-your-show' } })
    const er = validate({ company_name: [minLen(2, 'Company name')], contact_phone: [phoneRequired] }, v)
    setErrs(er)
    if (!Object.keys(er).length) m.mutate({ ...v, website: v.website || null, gst_number: v.gst_number || null, description: v.description || null })
  }
  const p = profile.data
  return (
    <div className="container-x py-6">
      <div className="rounded-2xl bg-gradient-to-r from-brand to-orange-500 p-8 text-white sm:p-12"><Store className="mb-3 h-10 w-10" /><h1 className="text-3xl font-extrabold sm:text-4xl">List your show</h1>
        <p className="mt-2 max-w-2xl text-white/90">Sell tickets for concerts, comedy, plays, sports and experiences. Set up venues, define ticket inventory and pricing, and watch sales live.</p></div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section className="card p-5">
          {p ? (
            <div><h2 className="text-xl font-bold">Your application</h2>
              <p className="mt-2 text-sm"><b>{p.company_name}</b> <Badge tone={p.status === 'approved' ? 'green' : p.status === 'rejected' ? 'red' : 'amber'}>{p.status}</Badge></p>
              {p.status === 'approved' ? <Link to="/organizer"><Button className="mt-4">Open organizer portal</Button></Link> : <p className="mt-3 text-sm text-gray-600">{p.status === 'pending' ? 'Our team is reviewing your application. You will be notified here once approved.' : 'Unfortunately your application was not approved. Contact support for details.'}</p>}</div>
          ) : (
            <form onSubmit={submit} noValidate className="space-y-4"><h2 className="text-xl font-bold">Register as an organizer</h2>
              {errs.form && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{errs.form}</p>}
              {!user && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">You'll need to <Link className="font-semibold underline" to="/login" state={{ from: '/list-your-show' }}>sign in</Link> first.</p>}
              <div className="grid gap-4 sm:grid-cols-2"><Input label="Company / organizer name" value={v.company_name} onChange={(e) => setV({ ...v, company_name: e.target.value })} error={errs.company_name} /><Input label="Contact phone" type="tel" placeholder="+919876543210" value={v.contact_phone} onChange={(e) => setV({ ...v, contact_phone: e.target.value })} error={errs.contact_phone} /></div>
              <div className="grid gap-4 sm:grid-cols-2"><Input label="Website (optional)" value={v.website} onChange={(e) => setV({ ...v, website: e.target.value })} /><Input label="GST number (optional)" value={v.gst_number} onChange={(e) => setV({ ...v, gst_number: e.target.value })} /></div>
              <Textarea label="Tell us about your shows" value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />
              <Button size="lg" loading={m.isPending}>Submit application</Button></form>
          )}
        </section>
        <aside className="card h-fit space-y-3 p-5 text-sm"><h2 className="font-bold">How it works</h2>{['Apply and get approved', 'Add your venue & create an event', 'Set ticket types, prices and inventory', 'Track sales and manage bookings live'].map((t, i) => <p key={t} className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-white">{i + 1}</span>{t}</p>)}</aside>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ Search */
export function SearchPage() {
  const [p] = useSearchParams()
  const q = p.get('q') || ''
  useTitle(`Search: ${q}`)
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['search', q], enabled: q.length >= 2, queryFn: () => api.get('/search', { q }) })
  const none = data && !data.movies.length && !data.events.length && !data.videos.length && !data.venues.length
  return (
    <div className="container-x space-y-8 py-6">
      <h1 className="text-2xl font-bold">Results for “{q}”</h1>
      {q.length < 2 ? <EmptyState icon={SearchIcon} title="Type at least 2 characters" /> : isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? <PageSpinner /> : none ? <EmptyState icon={SearchIcon} title="No results" text="Check the spelling or try a broader term." /> : (
        <>
          {data.movies.length > 0 && <section><SectionHeader title="Movies" /><div className="scroll-x">{data.movies.map((m) => <MovieCard key={m.id} movie={m} />)}</div></section>}
          {data.events.length > 0 && <section><SectionHeader title="Events & activities" /><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{data.events.map((e) => <EventCard key={e.id} event={e} />)}</div></section>}
          {data.videos.length > 0 && <section><SectionHeader title="Stream" /><div className="scroll-x">{data.videos.map((v) => <VideoCard key={v.id} video={v} />)}</div></section>}
          {data.venues.length > 0 && <section><SectionHeader title="Cinemas & venues" /><ul className="grid gap-3 sm:grid-cols-2">{data.venues.map((v) => <li key={v.id} className="card p-4"><b>{v.name}</b><p className="text-sm text-gray-500">{v.address}</p></li>)}</ul></section>}
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ Support / FAQ / static */
export function SupportPage() {
  useTitle('Contact support')
  return (
    <div className="container-x max-w-3xl py-6"><h1 className="text-2xl font-bold sm:text-3xl">Contact support</h1><p className="mb-5 text-sm text-gray-500">Include your booking ID so we can help faster. Looking for answers? Check the <Link className="font-semibold text-brand" to="/faqs">FAQs</Link>.</p>
      <div className="card p-5"><SupportForm /></div></div>
  )
}

export function Faqs() {
  useTitle('FAQs')
  const { data, isLoading } = useQuery({ queryKey: ['faqs'], queryFn: () => api.get('/faqs') })
  const [open, setOpen] = useState(null)
  if (isLoading) return <PageSpinner />
  const groups = Object.entries((data || []).reduce((a, f) => ((a[f.category] ||= []).push(f), a), {}))
  return (
    <div className="container-x max-w-3xl py-6"><h1 className="mb-5 text-2xl font-bold sm:text-3xl">Frequently asked questions</h1>
      {groups.map(([cat, items]) => (
        <section key={cat} className="mb-6"><h2 className="mb-2 font-bold text-brand">{cat}</h2>
          <div className="card divide-y">{items.map((f) => (
            <div key={f.id}><h3><button aria-expanded={open === f.id} aria-controls={`faq-${f.id}`} onClick={() => setOpen(open === f.id ? null : f.id)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left font-medium">{f.question}<ChevronDown className={clsx('h-4 w-4 shrink-0 transition', open === f.id && 'rotate-180')} /></button></h3>
              {open === f.id && <p id={`faq-${f.id}`} className="px-4 pb-4 text-sm text-gray-600">{f.answer}</p>}</div>))}</div></section>
      ))}
      <p className="text-sm text-gray-600">Still stuck? <Link to="/support" className="font-semibold text-brand">Contact support</Link>.</p></div>
  )
}

const DOCS = {
  about: ['About us', ['BookMyShow Clone is a demonstration ticketing platform built to show how a modern entertainment marketplace works end to end: discovery, live seat availability, secure payments, organizer tools and an admin back-office.', 'Everything here is sample data: movie titles, venues and events are fictional, and payments run in Razorpay test mode. No real tickets are issued and no money moves.', 'The Stream catalog only contains openly licensed films (Creative Commons) published by the Blender Foundation.']],
  careers: ['Careers', ['We are a demo project, so there are no real openings. In a real deployment this page would list roles pulled from your applicant tracking system.', 'Interested in how this app was built? The full source, API documentation (Swagger) and deployment guide are in the repository README.']],
  press: ['Press', ['Press kit placeholder. For a real deployment, publish logos, brand guidelines, executive bios and media contacts here.', 'Media enquiries: use the Contact support form with the subject “Press”.']],
  terms: ['Terms & Conditions', ['1. Demo service. This site is a demonstration. Bookings are not valid for entry at any real venue.', '2. Bookings & holds. Selected seats are held for a limited time while you pay. Unpaid holds are released automatically.', '3. Cancellations. Confirmed bookings can be cancelled until the cut-off shown on the booking. The ticket value is refunded; the convenience fee, taxes and optional donations are non-refundable.', '4. Payments. Payments are processed by Razorpay in test mode. Never enter real card details.', '5. Conduct. Do not misuse the platform, attempt to bypass seat locks, or resell tickets in violation of organizer rules.', '6. Content. Stream titles are provided under their respective Creative Commons licenses; attribution is shown on each title.']],
  privacy: ['Privacy Policy', ['What we collect: your name, email, optional phone number, bookings, payments metadata (we never store card numbers), favorites and support messages.', 'Location: your browser location is requested only when you press “Detect my location”, and is used once to pick the nearest city. Coordinates are not stored.', 'Google sign-in: if you use it, we receive your name, email and profile picture from Google.', 'Cookies & storage: we store your session tokens and chosen city in your browser to keep you signed in. We do not run advertising trackers.', 'Your rights: you can update your profile at any time, and you can request account deletion through support.']],
}
export function StaticDoc({ doc }) {
  const [title, paras] = DOCS[doc]
  useTitle(title)
  return <div className="container-x max-w-3xl py-8"><h1 className="mb-4 text-3xl font-bold">{title}</h1><div className="card space-y-4 p-6 leading-relaxed text-gray-700">{paras.map((p, i) => <p key={i}>{p}</p>)}</div><p className="mt-4 text-xs text-gray-400">Last updated {fmtDate(new Date(), { day: 'numeric', month: 'long', year: 'numeric' })}</p></div>
}

export function NotFound() {
  useTitle('Page not found')
  return <div className="container-x"><EmptyState title="Page not found" text="The page you're looking for doesn't exist or has moved." action={<Link to="/"><Button>Go home</Button></Link>} /></div>
}
