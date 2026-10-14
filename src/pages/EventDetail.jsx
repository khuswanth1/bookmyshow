import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Calendar, Clock, Languages, MapPin, Minus, Plus, ShieldCheck, Users } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { useTitle } from '../hooks'
import { Badge, Button, ErrorState, PageSpinner, Poster } from '../components/ui'
import { FavButton } from '../components/cards'
import MapView from '../components/MapView'
import { fmtDate, fmtTime, inr } from '../lib/format'

export default function EventDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const [qty, setQty] = useState({})
  const { data: e, isLoading, isError, error, refetch } = useQuery({ queryKey: ['event', id], queryFn: () => api.get(`/events/${id}`), refetchInterval: 30000 })
  useTitle(e?.title)
  if (isLoading) return <PageSpinner />
  if (isError) return <div className="container-x py-10"><ErrorState error={error} retry={refetch} /></div>

  const picked = e.ticket_types.filter((t) => qty[t.id] > 0).map((t) => ({ ticket_type_id: t.id, quantity: qty[t.id] }))
  const count = picked.reduce((a, p) => a + p.quantity, 0)
  const total = e.ticket_types.reduce((a, t) => a + (qty[t.id] || 0) * t.price_paise, 0)
  const change = (t, d) => setQty((q) => ({ ...q, [t.id]: Math.max(0, Math.min(t.max_per_booking, t.available, (q[t.id] || 0) + d)) }))
  const book = () => {
    if (!user) { toast.info('Sign in to book tickets'); return nav('/login', { state: { from: `/event/${id}` } }) }
    nav(`/checkout/event/${id}`, { state: { tickets: picked } })
  }
  const past = new Date(e.ends_at || e.starts_at) < new Date()

  return (
    <>
      <section className="text-white" style={{ background: `linear-gradient(110deg, ${e.color_a} 20%, ${e.color_b} 170%)` }}>
        <div className="container-x grid gap-6 py-8 md:grid-cols-[22rem_1fr]">
          <Poster a={e.color_a} b={e.color_b} url={e.image_url} title={e.title} ratio="aspect-[16/10]" className="shadow-2xl ring-1 ring-white/20" />
          <div>
            <div className="flex flex-wrap gap-2"><Badge tone="brand" className="!bg-white/20 !text-white">{e.category.name}</Badge>{e.is_exclusive && <Badge tone="dark" className="!bg-black/50">Exclusive</Badge>}</div>
            <h1 className="mt-2 text-3xl font-extrabold sm:text-4xl">{e.title}</h1>
            <ul className="mt-4 space-y-1.5 text-sm text-white/90">
              <li className="flex items-center gap-2"><Calendar className="h-4 w-4" />{fmtDate(e.starts_at, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</li>
              <li className="flex items-center gap-2"><Clock className="h-4 w-4" />{fmtTime(e.starts_at)}{e.ends_at && ` – ${fmtTime(e.ends_at)}`}</li>
              <li className="flex items-center gap-2"><MapPin className="h-4 w-4" />{e.venue_name}, {e.city.name}</li>
              {e.language && <li className="flex items-center gap-2"><Languages className="h-4 w-4" />{e.language.name}</li>}
              <li className="flex items-center gap-2"><Users className="h-4 w-4" />{e.age_limit}</li>
            </ul>
            <div className="mt-4"><FavButton type="event" id={e.id} className="!p-3" /></div>
          </div>
        </div>
      </section>

      <div className="container-x grid gap-6 py-8 lg:grid-cols-[1fr_24rem]">
        <div className="space-y-6">
          <section className="card p-5"><h2 className="mb-2 text-xl font-bold">About</h2><p className="whitespace-pre-line text-gray-700">{e.description}</p>
            {e.performers?.length > 0 && <p className="mt-3 text-sm"><b>Featuring:</b> {e.performers.join(', ')}</p>}</section>
          <section className="card p-5"><h2 className="mb-1 text-xl font-bold">Venue</h2><p className="mb-3 text-sm text-gray-600">{e.address}</p>
            <MapView points={[{ lat: e.lat, lng: e.lng, title: e.venue_name, subtitle: e.address }]} height={260} /></section>
          <section className="flex items-start gap-3 rounded-xl bg-white p-5 text-sm text-gray-600 ring-1 ring-black/5"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />Tickets are delivered instantly with a QR code. Cancel up to 2 hours before the start for a refund of the ticket value.</section>
        </div>

        <aside className="card h-fit p-5 lg:sticky lg:top-28" aria-labelledby="tk-h">
          <h2 id="tk-h" className="mb-3 text-lg font-bold">Select tickets</h2>
          {past ? <p className="text-sm text-gray-500">This event has ended.</p> : (
            <ul className="space-y-3">
              {e.ticket_types.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-3 rounded-lg border p-3">
                  <div><p className="font-semibold">{t.name}</p><p className="text-sm font-bold text-brand">{t.price_paise ? inr(t.price_paise) : 'Free'}</p>
                    {t.description && <p className="text-xs text-gray-500">{t.description}</p>}
                    {t.available === 0 ? <Badge tone="red">Sold out</Badge> : t.available <= 10 && <p className="text-xs font-semibold text-amber-700">Only {t.available} left</p>}</div>
                  {t.available > 0 && (
                    <div className="flex items-center gap-2" role="group" aria-label={`Quantity for ${t.name}`}>
                      <button onClick={() => change(t, -1)} disabled={!qty[t.id]} aria-label={`Remove one ${t.name}`} className="grid h-8 w-8 place-items-center rounded-full border hover:border-brand disabled:opacity-40"><Minus className="h-4 w-4" /></button>
                      <span className="w-6 text-center font-semibold" aria-live="polite">{qty[t.id] || 0}</span>
                      <button onClick={() => change(t, 1)} disabled={(qty[t.id] || 0) >= Math.min(t.max_per_booking, t.available)} aria-label={`Add one ${t.name}`} className="grid h-8 w-8 place-items-center rounded-full border hover:border-brand disabled:opacity-40"><Plus className="h-4 w-4" /></button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {!past && <Button size="lg" className="mt-4 w-full" disabled={!count} onClick={book}>{count ? `Book ${count} ticket${count > 1 ? 's' : ''} · ${inr(total)}` : 'Select tickets'}</Button>}
        </aside>
      </div>
    </>
  )
}
