import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bell, ChevronDown, Film, LogOut, MapPin, Menu, Search, Ticket, User, X, LayoutDashboard, Shield, Store, Building2, ScanLine, LifeBuoy } from 'lucide-react'
import { api } from '../../lib/api'
import { useAuth, useCity, useToast } from '../../context/providers'
import { useDebounce } from '../../hooks'
import { Button, Chip, Modal, Spinner } from '../ui'
import { clsx } from '../../lib/format'
import { portalFor } from '../../lib/roles'
import CityPicker from '../CityPicker'

const NAV = [
  ['/movies', 'Movies'], ['/stream', 'Stream'], ['/events', 'Events'], ['/plays', 'Plays'], ['/sports', 'Sports'], ['/activities', 'Activities'],
]
const SECONDARY = [
  ['/offers', 'Offers'], ['/gift-cards', 'Gift Cards'], ['/exclusives', 'BookMyShow Exclusives'], ['/corporates', 'Corporates'], ['/list-your-show', 'ListYourShow'],
]

function Logo({ to = '/' }) {
  return (
    <Link to={to} className="flex items-center gap-2 text-xl font-extrabold tracking-tight" aria-label="BookMyShow Clone home">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white"><Ticket className="h-5 w-5" aria-hidden="true" /></span>
      <span className="hidden sm:inline">book<span className="text-brand">my</span>show<span className="ml-1 rounded bg-night px-1.5 py-0.5 align-middle text-[10px] font-semibold uppercase text-white">clone</span></span>
    </Link>
  )
}

function SearchBox() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const dq = useDebounce(q.trim(), 250)
  const nav = useNavigate()
  const { city } = useCity()
  const box = useRef(null)
  const { data, isFetching } = useQuery({
    queryKey: ['search-suggest', dq, city?.id], enabled: dq.length >= 2,
    queryFn: () => api.get('/search', { q: dq, city_id: city?.id }),
  })
  useEffect(() => {
    const h = (e) => !box.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const go = (path) => { setOpen(false); setQ(''); nav(path) }
  const rows = data ? [
    ...data.movies.map((m) => ({ k: `m${m.id}`, t: m.title, s: 'Movie', to: `/movies/${m.id}` })),
    ...data.events.map((e) => ({ k: `e${e.id}`, t: e.title, s: e.category.name, to: `/event/${e.id}` })),
    ...data.videos.map((v) => ({ k: `v${v.id}`, t: v.title, s: 'Stream', to: `/stream/${v.id}` })),
    ...data.venues.map((v) => ({ k: `c${v.id}`, t: v.name, s: 'Venue', to: `/search?q=${encodeURIComponent(v.name)}` })),
  ] : []
  return (
    <div ref={box} className="relative w-full max-w-xl" role="search">
      <form onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) go(`/search?q=${encodeURIComponent(q.trim())}`) }}>
        <label htmlFor="global-search" className="sr-only">Search for movies, events, plays, sports and activities</label>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        <input id="global-search" value={q} autoComplete="off" onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
          placeholder="Search for movies, events, plays, sports…"
          className="w-full rounded-lg border border-gray-300 bg-white py-2.5 pl-9 pr-9 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20" />
        {isFetching && <Spinner className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2" />}
      </form>
      {open && dq.length >= 2 && (
        <div className="absolute z-50 mt-1 max-h-96 w-full overflow-auto rounded-xl bg-white p-1 shadow-xl ring-1 ring-black/10">
          {rows.length === 0 && !isFetching && <p className="p-3 text-sm text-gray-500">No matches for “{dq}”.</p>}
          {rows.map((r) => (
            <button key={r.k} onClick={() => go(r.to)} className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-gray-100">
              <span className="truncate font-medium">{r.t}</span><span className="ml-3 shrink-0 text-xs text-gray-500">{r.s}</span>
            </button>
          ))}
          {rows.length > 0 && <button onClick={() => go(`/search?q=${encodeURIComponent(dq)}`)} className="w-full rounded-lg px-3 py-2 text-left text-sm font-semibold text-brand hover:bg-gray-100">See all results</button>}
        </div>
      )}
    </div>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const nav = useNavigate()
  const { data: unread } = useQuery({ queryKey: ['notifications', 'unread'], enabled: !!user, refetchInterval: 60000, queryFn: () => api.get('/notifications/unread-count') })
  useEffect(() => {
    const h = (e) => !ref.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  if (!user) return <Link to="/login"><Button size="sm">Sign in</Button></Link>
  const item = 'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-gray-100'
  return (
    <div ref={ref} className="relative flex items-center gap-1">
      <Link to="/account/notifications" aria-label={`Notifications${unread?.count ? `, ${unread.count} unread` : ''}`} className="relative rounded-full p-2 hover:bg-gray-100">
        <Bell className="h-5 w-5" />{!!unread?.count && <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-brand ring-2 ring-white" />}
      </Link>
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 hover:bg-gray-100">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-night text-sm font-bold text-white">{user.name[0]?.toUpperCase()}</span>
        <ChevronDown className="h-4 w-4" aria-hidden="true" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-50 mt-1 w-56 rounded-xl bg-white p-1 shadow-xl ring-1 ring-black/10" onClick={() => setOpen(false)}>
          <div className="border-b px-3 py-2"><p className="truncate text-sm font-semibold">{user.name}</p><p className="truncate text-xs text-gray-500">{user.email}</p></div>
          <Link role="menuitem" to="/account" className={item}><User className="h-4 w-4" />My account</Link>
          <Link role="menuitem" to="/account/bookings" className={item}><Ticket className="h-4 w-4" />My bookings</Link>
          {(user.role === 'organizer' || user.role === 'admin') && <Link role="menuitem" to="/organizer" className={item}><Store className="h-4 w-4" />Organizer portal</Link>}
          {(user.role === 'vendor' || user.role === 'manager') && <Link role="menuitem" to="/vendor" className={item}><Building2 className="h-4 w-4" />Vendor portal</Link>}
          {(user.role === 'checkin' || user.role === 'admin') && <Link role="menuitem" to="/checkin" className={item}><ScanLine className="h-4 w-4" />Check-in scanner</Link>}
          {(user.role === 'support' || user.role === 'admin') && <Link role="menuitem" to="/helpdesk" className={item}><LifeBuoy className="h-4 w-4" />Support desk</Link>}
          {user.role === 'admin' && <Link role="menuitem" to="/admin" className={item}><Shield className="h-4 w-4" />Admin panel</Link>}
          <button role="menuitem" className={item} onClick={() => { logout(); nav('/') }}><LogOut className="h-4 w-4" />Sign out</button>
        </div>
      )}
    </div>
  )
}

const portalHome = (u) => portalFor(u?.role)

function Header() {
  const { user } = useAuth()
  const staff = !!user && user.role !== 'user' // owners/organizers/admins see only their portal, not the customer storefront
  const { city, openPicker } = useCity()
  const [mobile, setMobile] = useState(false)
  const loc = useLocation()
  useEffect(() => setMobile(false), [loc.pathname])
  const link = ({ isActive }) => clsx('border-b-2 py-2 text-sm font-medium transition', isActive ? 'border-brand text-brand' : 'border-transparent text-gray-700 hover:text-brand')
  return (
    <header className="sticky top-0 z-40 bg-white shadow-sm">
      <div className="container-x flex items-center gap-3 py-3">
        {!staff && <button className="rounded-lg p-2 hover:bg-gray-100 lg:hidden" aria-label="Open menu" aria-expanded={mobile} onClick={() => setMobile(!mobile)}>
          {mobile ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>}
        <Logo to={portalHome(user)} />
        {!staff && <div className="hidden flex-1 justify-center md:flex"><SearchBox /></div>}
        <div className="ml-auto flex items-center gap-2">
          {!staff && <button onClick={openPicker} className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm font-medium hover:bg-gray-100" aria-label={`Selected city ${city?.name || 'none'}. Change city`}>
            <MapPin className="h-4 w-4 text-brand" aria-hidden="true" /><span className="max-w-24 truncate">{city?.name || 'Select city'}</span><ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          </button>}
          <UserMenu />
        </div>
      </div>
      {!staff && <div className="container-x pb-3 md:hidden"><SearchBox /></div>}
      {!staff && <nav aria-label="Primary" className="hidden border-t border-gray-100 bg-white lg:block">
        <div className="container-x flex items-center justify-between">
          <div className="flex gap-6">{NAV.map(([to, l]) => <NavLink key={to} to={to} className={link}>{l}</NavLink>)}</div>
          <div className="flex gap-5">{SECONDARY.map(([to, l]) => <NavLink key={to} to={to} className={clsx(link({ isActive: loc.pathname === to }), 'text-xs')}>{l}</NavLink>)}</div>
        </div>
      </nav>}
      {!staff && mobile && (
        <nav aria-label="Mobile" className="border-t bg-white lg:hidden">
          <ul className="container-x grid grid-cols-2 gap-1 py-3">
            {[...NAV, ...SECONDARY].map(([to, l]) => (
              <li key={to}><NavLink to={to} className={({ isActive }) => clsx('block rounded-lg px-3 py-2 text-sm font-medium', isActive ? 'bg-brand/10 text-brand' : 'hover:bg-gray-100')}>{l}</NavLink></li>
            ))}
          </ul>
        </nav>
      )}
    </header>
  )
}

function Footer() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const submit = async (e) => {
    e.preventDefault()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return toast.error('Enter a valid email address')
    setBusy(true)
    try { await api.post('/newsletter', { email }); toast.success('Subscribed. Thanks!'); setEmail('') } catch (err) { toast.error(err.message) } finally { setBusy(false) }
  }
  const col = 'space-y-2 text-sm text-gray-300 [&_a:hover]:text-white'
  return (
    <footer className="mt-16 bg-night text-white">
      <div className="container-x grid gap-8 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <h2 className="mb-3 font-bold">Stay in the loop</h2>
          <form onSubmit={submit} className="flex gap-2">
            <label htmlFor="nl" className="sr-only">Email for newsletter</label>
            <input id="nl" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" className="min-w-0 flex-1 rounded-lg bg-white/10 px-3 py-2 text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-brand" />
            <Button size="sm" loading={busy}>Subscribe</Button>
          </form>
          <p className="mt-3 text-xs text-gray-400">Weekly picks, early access and offers. Unsubscribe anytime.</p>
        </div>
        <nav aria-label="Explore"><h2 className="mb-3 font-bold">Explore</h2>
          <ul className={col}>{[...NAV, ...SECONDARY].map(([to, l]) => <li key={to}><Link to={to}>{l}</Link></li>)}</ul></nav>
        <nav aria-label="Help"><h2 className="mb-3 font-bold">Help</h2>
          <ul className={col}>
            <li><Link to="/support">Contact support</Link></li><li><Link to="/faqs">FAQs</Link></li>
            <li><Link to="/account/bookings">Resend booking confirmation</Link></li><li><Link to="/list-your-show">List your show</Link></li><li><Link to="/become-a-vendor">List your theater</Link></li>
          </ul></nav>
        <nav aria-label="Company"><h2 className="mb-3 font-bold">Company</h2>
          <ul className={col}>
            <li><Link to="/about">About us</Link></li><li><Link to="/careers">Careers</Link></li><li><Link to="/press">Press</Link></li>
            <li><Link to="/terms">Terms & Conditions</Link></li><li><Link to="/privacy">Privacy Policy</Link></li>
          </ul></nav>
      </div>
      <div className="border-t border-white/10 py-4 text-center text-xs text-gray-400">
        Demo project — payments run in Razorpay test mode; no real tickets are issued. © {new Date().getFullYear()} BookMyShow Clone.
      </div>
    </footer>
  )
}

export default function Layout() {
  const { pathname } = useLocation()
  const { user } = useAuth()
  const staff = !!user && user.role !== 'user'
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only-focusable fixed left-2 top-2 z-[300] rounded bg-white px-3 py-2 text-sm font-semibold shadow">Skip to content</a>
      <Header />
      <main id="main" className="flex-1"><Outlet /></main>
      {!staff && <Footer />}
      {!staff && <CityPicker />}
    </div>
  )
}
