import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, Wifi, WifiOff } from 'lucide-react'
import { api, wsUrl } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { useCountdown, useTitle } from '../hooks'
import { Button, ErrorState, PageSpinner } from '../components/ui'
import { clsx, duration, fmtDateTime, inr, secondsToClock } from '../lib/format'

const STYLE = {
  available: 'bg-white text-emerald-700 ring-1 ring-emerald-500 hover:bg-emerald-50',
  selected: 'bg-emerald-600 text-white ring-1 ring-emerald-700',
  locked: 'bg-amber-200 text-amber-800 ring-1 ring-amber-300 cursor-not-allowed',
  booked: 'bg-gray-300 text-gray-400 cursor-not-allowed',
  blocked: 'bg-gray-100 text-gray-300 ring-1 ring-gray-200 cursor-not-allowed line-through',
}

function useSeatSocket(showId, onSeats, onOpen) {
  const [live, setLive] = useState(false)
  const cb = useRef({ onSeats, onOpen })
  cb.current = { onSeats, onOpen }
  useEffect(() => {
    let ws, retry, closed = false, tries = 0, ping
    const connect = () => {
      ws = new WebSocket(wsUrl(`/ws/shows/${showId}`))
      ws.onopen = () => { setLive(true); if (tries > 0) cb.current.onOpen?.(); tries = 0 }
      ws.onmessage = (e) => { try { const m = JSON.parse(e.data); if (m.type === 'seats') cb.current.onSeats(m.seats) } catch { /* ignore */ } }
      ws.onclose = () => { setLive(false); if (!closed) retry = setTimeout(connect, Math.min(10000, 1000 * 2 ** tries++)) }
    }
    connect()
    ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
    return () => { closed = true; clearTimeout(retry); clearInterval(ping); ws?.close() }
  }, [showId])
  return live
}

export default function SeatSelection() {
  const { showId } = useParams()
  const { user } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: show, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['show', showId, user?.id], queryFn: () => api.get(`/shows/${showId}`), staleTime: 0, refetchOnWindowFocus: false,
  })
  useTitle(show ? `${show.movie.title}: select seats` : 'Select seats')

  const [status, setStatus] = useState({}) // seatId -> available|locked|booked (what everyone else sees)
  const [sel, setSel] = useState([]) // my selected seat ids
  const [expires, setExpires] = useState(null)
  const [busy, setBusy] = useState(false)
  const confirmed = useRef([]) // last selection the server acknowledged
  const chain = useRef(Promise.resolve())
  const selRef = useRef(sel)
  selRef.current = sel

  const hydrate = useCallback((d) => {
    setStatus(Object.fromEntries(d.seats.map((s) => [s.id, s.status])))
    const mine = d.seats.filter((s) => s.mine).map((s) => s.id)
    setSel(mine); confirmed.current = mine
  }, [])
  useEffect(() => { if (show) hydrate(show) }, [show, hydrate])
  // when we reload the page with existing holds, approximate the expiry from the lock TTL
  useEffect(() => { if (show && sel.length && !expires) setExpires(new Date(Date.now() + show.lock_minutes * 60000).toISOString()) }, [show]) // eslint-disable-line

  const onSeats = useCallback((changes) => {
    setStatus((prev) => { const n = { ...prev }; for (const c of changes) n[c.id] = c.status; return n })
    // one of *my* held seats became available/booked elsewhere => my hold lapsed
    const lost = changes.filter((c) => selRef.current.includes(c.id) && c.status === 'available')
    if (lost.length && !busy) {
      setSel((s) => s.filter((id) => !lost.some((l) => l.id === id)))
      confirmed.current = confirmed.current.filter((id) => !lost.some((l) => l.id === id))
      toast.info('Your seat hold expired')
    }
  }, [busy, toast])
  const live = useSeatSocket(showId, onSeats, () => refetch())

  const seatsById = useMemo(() => Object.fromEntries((show?.seats || []).map((s) => [s.id, s])), [show])
  const rows = useMemo(() => {
    const m = new Map()
    for (const s of show?.seats || []) { if (!m.has(s.row)) m.set(s.row, []); m.get(s.row).push(s) }
    return [...m.entries()]
  }, [show])
  const aisles = useMemo(() => Object.fromEntries((show?.layout?.rows || []).map((r) => [r.label, r.aisles || []])), [show])
  const total = sel.reduce((a, id) => a + (seatsById[id]?.price_paise || 0), 0)

  const left = useCountdown(sel.length ? expires : null, () => {
    if (!selRef.current.length) return
    toast.info('Your seat hold expired. Please select seats again.')
    setSel([]); confirmed.current = []; setExpires(null); refetch()
  })

  const push = (ids) => {
    setBusy(true)
    chain.current = chain.current
      .then(() => api.put(`/shows/${showId}/locks`, { seat_ids: ids }))
      .then((r) => { confirmed.current = ids; setExpires(r.expires_at) })
      .catch((e) => {
        if (e.code === 'seat_unavailable') {
          const bad = e.details?.seat_ids || []
          setStatus((p) => { const n = { ...p }; bad.forEach((id) => { n[id] = 'locked' }); return n })
          toast.error('Those seats were just taken by someone else. Please pick others.')
        } else toast.error(e.message)
        setSel(confirmed.current)
      })
      .finally(() => setBusy(false))
  }

  const toggle = (seat) => {
    if (!user) { toast.info('Sign in to select seats'); return nav('/login', { state: { from: `/shows/${showId}/seats` } }) }
    const on = sel.includes(seat.id)
    if (!on && sel.length >= show.max_seats) return toast.error(`You can select up to ${show.max_seats} seats`)
    const next = on ? sel.filter((i) => i !== seat.id) : [...sel, seat.id]
    setSel(next)
    push(next)
  }

  const seatState = (s) => (sel.includes(s.id) ? 'selected' : status[s.id] === 'booked' ? 'booked' : status[s.id] === 'blocked' ? 'blocked' : status[s.id] === 'locked' ? 'locked' : 'available')

  if (isLoading) return <PageSpinner />
  if (isError) return <div className="container-x py-10"><ErrorState error={error} retry={refetch} /></div>
  const closed = new Date(show.starts_at) <= new Date()
  let lastCat = null

  return (
    <div className="pb-28">
      <div className="border-b bg-white">
        <div className="container-x flex flex-wrap items-center justify-between gap-3 py-4">
          <div>
            <Link to={`/movies/${show.movie.id}`} className="text-xs font-semibold text-brand hover:underline">‹ Back to {show.movie.title}</Link>
            <h1 className="text-xl font-bold sm:text-2xl">{show.movie.title}</h1>
            <p className="text-sm text-gray-600">{show.venue.name} · {show.screen_name} · {fmtDateTime(show.starts_at)} · {show.language} · {show.format}</p>
          </div>
          <span className={clsx('inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold', live ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-200 text-gray-600')} role="status">
            {live ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}{live ? 'Live availability' : 'Reconnecting…'}
          </span>
        </div>
      </div>

      <div className="container-x py-6">
        {closed ? <ErrorState error={{ message: 'Booking is closed for this show.' }} /> : (
          <div className="card overflow-x-auto p-4 sm:p-8">
            <div className="mx-auto w-max min-w-full">
              <div className="mx-auto w-full max-w-xl" aria-hidden="true">
                <div className="mx-auto h-2 w-4/5 rounded-b-[100%] bg-gradient-to-b from-gray-400 to-transparent" />
                <p className="mb-6 mt-1 text-center text-[11px] font-semibold uppercase tracking-[0.3em] text-gray-400">All eyes this way</p>
              </div>
              <div className="flex flex-col items-center gap-1.5" role="group" aria-label="Seat map">
                {rows.map(([label, seats]) => {
                  const cat = seats[0].category
                  const header = cat !== lastCat
                  lastCat = cat
                  return (
                    <div key={label} className="flex flex-col items-center gap-1.5">
                      {header && <p className="mt-3 w-full border-b pb-1 text-center text-xs font-bold uppercase tracking-wider text-gray-500">{cat} · {inr(seats[0].price_paise)}</p>}
                      <div role="group" aria-label={`Row ${label}`} className="flex items-center gap-1.5">
                        <span className="w-5 text-center text-xs font-semibold text-gray-400" aria-hidden="true">{label}</span>
                        {seats.map((s) => {
                          const st = seatState(s)
                          return (
                            <span key={s.id} className="flex">
                              <button
                                disabled={st === 'booked' || st === 'locked' || st === 'blocked'} onClick={() => toggle(s)} aria-pressed={st === 'selected'}
                                aria-label={`Row ${s.row} seat ${s.number}, ${s.category}, ${inr(s.price_paise)}, ${st === 'selected' ? 'selected' : st === 'available' ? 'available' : 'unavailable'}`}
                                className={clsx('seat h-7 w-7 rounded-t-lg text-[10px] font-semibold sm:h-8 sm:w-8 sm:text-xs', STYLE[st])}>
                                {s.number}
                              </button>
                              {aisles[label]?.includes(s.number) && <span className="w-4 sm:w-6" aria-hidden="true" />}
                            </span>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
              <ul className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-gray-600" aria-label="Legend">
                {[['available', 'Available'], ['selected', 'Selected'], ['locked', 'Being booked'], ['booked', 'Sold'], ['blocked', 'Unavailable']].map(([k, l]) => (
                  <li key={k} className="flex items-center gap-1.5"><span className={clsx('h-4 w-4 rounded-t', STYLE[k])} />{l}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-white shadow-[0_-4px_16px_rgba(0,0,0,.08)]">
        <div className="container-x flex flex-wrap items-center justify-between gap-3 py-3">
          <div aria-live="polite">
            {sel.length === 0 ? <p className="text-sm text-gray-500">Select up to {show.max_seats} seats</p> : (
              <>
                <p className="text-sm font-semibold">{sel.map((id) => `${seatsById[id].row}${seatsById[id].number}`).join(', ')}</p>
                <p className="text-xs text-gray-500">{sel.length} ticket{sel.length > 1 ? 's' : ''} · {inr(total)} <span className="ml-2 inline-flex items-center gap-1 font-semibold text-amber-700"><Clock className="h-3 w-3" />held for {secondsToClock(left)}</span></p>
              </>
            )}
          </div>
          <Button size="lg" disabled={!sel.length || busy || closed} loading={busy} onClick={() => nav(`/checkout/movie/${showId}`)}>
            Pay {sel.length ? inr(total) : ''}
          </Button>
        </div>
      </div>
    </div>
  )
}
