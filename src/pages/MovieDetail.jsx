import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, Film, MapPin, Play, Star } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, useCity, useToast } from '../context/providers'
import { useTitle } from '../hooks'
import { Badge, Button, Chip, EmptyState, ErrorState, Modal, PageSpinner, Pagination, Poster, Rating, Select, Textarea } from '../components/ui'
import { FavButton } from '../components/cards'
import MapView from '../components/MapView'
import { clsx, duration, fmtDate, fmtTime, inr, ymd } from '../lib/format'

function Trailer({ id, open, onClose, title }) {
  return (
    <Modal open={open} onClose={onClose} title={`${title}: trailer`} wide>
      <div className="aspect-video overflow-hidden rounded-lg bg-black">
        {open && <iframe className="h-full w-full" src={`https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0`} title={`${title} trailer`} allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen />}
      </div>
      <p className="mt-3 text-xs text-gray-500">Demo trailer: an open-licensed Blender Foundation short film (Creative Commons) stands in for real trailers.</p>
    </Modal>
  )
}

function Reviews({ movieId }) {
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [score, setScore] = useState(8)
  const [comment, setComment] = useState('')
  const q = useQuery({ queryKey: ['ratings', movieId, page], queryFn: () => api.get(`/movies/${movieId}/ratings`, { page, size: 5 }), placeholderData: (p) => p })
  const m = useMutation({
    mutationFn: () => api.put(`/movies/${movieId}/ratings`, { score, comment: comment.trim() || null }),
    onSuccess: () => { toast.success('Thanks for rating!'); setComment(''); qc.invalidateQueries({ queryKey: ['ratings', movieId] }); qc.invalidateQueries({ queryKey: ['movie', String(movieId)] }) },
    onError: (e) => toast.error(e.message),
  })
  return (
    <section aria-labelledby="reviews-h" className="card p-5">
      <h2 id="reviews-h" className="text-xl font-bold">Ratings & reviews</h2>
      {user ? (
        <form onSubmit={(e) => { e.preventDefault(); m.mutate() }} className="mt-4 space-y-3 rounded-lg bg-gray-50 p-4">
          <div role="radiogroup" aria-label="Your rating out of 10" className="flex flex-wrap gap-1.5">
            {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
              <button type="button" role="radio" aria-checked={score === n} key={n} onClick={() => setScore(n)}
                className={clsx('h-9 w-9 rounded-lg text-sm font-bold ring-1', score === n ? 'bg-brand text-white ring-brand' : 'bg-white ring-gray-300 hover:ring-brand')}>{n}</button>
            ))}
          </div>
          <Textarea label="Your review (optional)" rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
          <Button loading={m.isPending}>Submit rating</Button>
        </form>
      ) : <p className="mt-3 text-sm text-gray-500"><Link to="/login" className="font-semibold text-brand">Sign in</Link> to rate this movie.</p>}
      <ul className="mt-5 divide-y">
        {q.data?.items.length === 0 && <li className="py-3 text-sm text-gray-500">No reviews yet. Be the first!</li>}
        {q.data?.items.map((r) => (
          <li key={r.id} className="py-3"><div className="flex items-center gap-2"><Badge tone="brand">★ {r.score}/10</Badge><span className="text-sm font-semibold">{r.user_name}</span><span className="text-xs text-gray-400">{fmtDate(r.created_at, { day: 'numeric', month: 'short', year: 'numeric' })}</span></div>
            {r.comment && <p className="mt-1 text-sm text-gray-700">{r.comment}</p>}</li>
        ))}
      </ul>
      {q.data && <Pagination page={q.data.page} pages={q.data.pages} onChange={setPage} />}
    </section>
  )
}

function DateStrip({ dates, value, onChange }) {
  return (
    <div className="scroll-x" role="tablist" aria-label="Show dates">
      {dates.map((d) => {
        const dt = new Date(`${d}T00:00:00`)
        const on = value === d
        return (
          <button key={d} role="tab" aria-selected={on} onClick={() => onChange(d)}
            className={clsx('flex w-16 shrink-0 flex-col items-center rounded-lg px-2 py-2 text-center ring-1 transition', on ? 'bg-brand text-white ring-brand' : 'bg-white ring-gray-200 hover:ring-brand')}>
            <span className="text-[11px] font-semibold uppercase">{dt.toLocaleDateString('en-IN', { weekday: 'short' })}</span>
            <span className="text-xl font-bold leading-tight">{dt.getDate()}</span>
            <span className="text-[11px] uppercase">{dt.toLocaleDateString('en-IN', { month: 'short' })}</span>
          </button>
        )
      })}
    </div>
  )
}

function Showtimes({ movie }) {
  const { city, openPicker } = useCity()
  const nav = useNavigate()
  const [date, setDate] = useState(null)
  const [lang, setLang] = useState('')
  const [fmt, setFmt] = useState('')
  const [price, setPrice] = useState('')
  const [map, setMap] = useState(false)

  const dates = useQuery({ queryKey: ['movie-dates', movie.id, city?.id], enabled: !!city, queryFn: () => api.get(`/movies/${movie.id}/dates`, { city_id: city.id }) })
  const day = date || dates.data?.[0]
  const shows = useQuery({
    queryKey: ['movie-shows', movie.id, city?.id, day, lang, fmt, price], enabled: !!city && !!day,
    queryFn: () => api.get(`/movies/${movie.id}/shows`, { city_id: city.id, on: day, language_id: lang || undefined, format: fmt || undefined, max_price_paise: price || undefined }),
    refetchInterval: 20000,
  })
  const points = useMemo(() => (shows.data || []).map((g) => ({ lat: g.venue.lat, lng: g.venue.lng, title: g.venue.name, subtitle: g.venue.address })), [shows.data])

  if (!city) return <EmptyState icon={MapPin} title="Choose a city to see showtimes" action={<Button onClick={openPicker}>Select city</Button>} />
  if (new Date(movie.release_date) > new Date()) return <EmptyState icon={Clock} title={`Releasing on ${fmtDate(movie.release_date)}`} text="Showtimes will appear here once bookings open." />
  if (dates.isLoading) return <PageSpinner />
  if (!dates.data?.length) return <EmptyState icon={Film} title={`No upcoming shows in ${city.name}`} text="Try another city." action={<Button onClick={openPicker}>Change city</Button>} />

  return (
    <div>
      <DateStrip dates={dates.data} value={day} onChange={setDate} />
      <div className="mt-4 flex flex-wrap gap-3">
        <Select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)} className="w-40"><option value="">All languages</option>{movie.languages.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</Select>
        <Select aria-label="Format" value={fmt} onChange={(e) => setFmt(e.target.value)} className="w-36"><option value="">All formats</option>{['2D', '3D', 'IMAX 2D'].map((f) => <option key={f}>{f}</option>)}</Select>
        <Select aria-label="Max price" value={price} onChange={(e) => setPrice(e.target.value)} className="w-40"><option value="">Any price</option><option value="20000">Up to ₹200</option><option value="30000">Up to ₹300</option><option value="50000">Up to ₹500</option></Select>
        <Button variant="outline" size="sm" className="self-end" onClick={() => setMap(!map)}><MapPin className="h-4 w-4" />{map ? 'Hide map' : 'Show map'}</Button>
      </div>
      {map && <MapView points={points} className="mt-4" />}
      <div className="mt-4 space-y-3" aria-busy={shows.isFetching}>
        {shows.isLoading ? <PageSpinner /> : shows.data?.length === 0 ? <p className="text-sm text-gray-500">No shows match these filters.</p> : shows.data?.map((g) => (
          <div key={g.venue.id} className="card p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><h3 className="font-bold">{g.venue.name}</h3><p className="text-xs text-gray-500">{g.venue.address}</p></div>
              <div className="flex flex-wrap gap-1">{g.venue.amenities.slice(0, 3).map((a) => <Badge key={a}>{a}</Badge>)}</div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {g.shows.map((s) => {
                const ratio = s.total ? s.available / s.total : 1
                const full = s.available === 0
                const tone = full ? 'border-gray-200 bg-gray-100 text-gray-400' : ratio < 0.25 ? 'border-amber-500 text-amber-700 hover:bg-amber-50' : 'border-emerald-500 text-emerald-700 hover:bg-emerald-50'
                return (
                  <button key={s.id} disabled={full} onClick={() => nav(`/shows/${s.id}/seats`)}
                    title={`${s.language} · ${s.format} · ${s.screen} · from ${inr(Math.min(...Object.values(s.prices)))} · ${full ? 'Sold out' : `${s.available} seats left`}`}
                    className={clsx('rounded-lg border px-3 py-1.5 text-center text-sm font-semibold disabled:cursor-not-allowed', tone)}>
                    {fmtTime(s.starts_at)}<span className="block text-[10px] font-normal uppercase">{s.language} · {s.format}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        <p className="flex flex-wrap gap-4 text-xs text-gray-500"><span className="text-emerald-600">● Available</span><span className="text-amber-600">● Filling fast</span><span className="text-gray-400">● Sold out</span></p>
      </div>
    </div>
  )
}

export default function MovieDetail() {
  const { id } = useParams()
  const [trailer, setTrailer] = useState(false)
  const { data: m, isLoading, isError, error, refetch } = useQuery({ queryKey: ['movie', id], queryFn: () => api.get(`/movies/${id}`) })
  useTitle(m?.title)
  if (isLoading) return <PageSpinner />
  if (isError) return <div className="container-x py-10"><ErrorState error={error} retry={refetch} /></div>
  const upcoming = new Date(m.release_date) > new Date()
  return (
    <>
      <section className="text-white" style={{ background: `linear-gradient(100deg, ${m.color_a} 20%, ${m.color_b} 160%)` }}>
        <div className="container-x flex flex-col gap-6 py-8 sm:flex-row">
          <Poster a={m.color_a} b={m.color_b} url={m.poster_url} title={m.title} className="w-44 shrink-0 self-center shadow-2xl ring-1 ring-white/20 sm:w-56 sm:self-start" />
          <div className="flex-1">
            <h1 className="text-3xl font-extrabold sm:text-4xl">{m.title}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
              {!upcoming && <span className="inline-flex items-center gap-1 rounded-lg bg-black/40 px-3 py-1.5"><Star className="h-4 w-4 fill-yellow-400 text-yellow-400" /><b>{Number(m.rating_avg) > 0 ? `${Number(m.rating_avg).toFixed(1)}/10` : 'New'}</b>{m.rating_count > 0 && <span className="text-white/70">({m.rating_count} votes)</span>}</span>}
              <span className="inline-flex items-center gap-1"><Clock className="h-4 w-4" />{duration(m.duration_min)}</span>
              <Badge tone="dark" className="!bg-white/20">{m.certificate}</Badge><span>{fmtDate(m.release_date, { day: 'numeric', month: 'long', year: 'numeric' })}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">{m.genres.map((g) => <span key={g.id} className="rounded-full bg-white/15 px-3 py-1 text-xs font-medium">{g.name}</span>)}</div>
            <p className="mt-3 text-sm text-white/85">{m.languages.map((l) => l.name).join(', ')}</p>
            <p className="mt-4 max-w-2xl text-white/90">{m.synopsis}</p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              {!upcoming && <a href="#showtimes"><Button size="lg">Book tickets</Button></a>}
              {m.trailer_youtube_id && <Button size="lg" variant="outline" className="!bg-transparent !text-white !border-white/60 hover:!bg-white/10" onClick={() => setTrailer(true)}><Play className="h-4 w-4" />Watch trailer</Button>}
              <FavButton type="movie" id={m.id} className="!p-3" />
            </div>
          </div>
        </div>
      </section>
      <div className="container-x space-y-6 py-8">
        <section id="showtimes" aria-labelledby="st-h" className="scroll-mt-24"><h2 id="st-h" className="mb-4 text-xl font-bold">Showtimes</h2><Showtimes movie={m} /></section>
        <section className="card grid gap-6 p-5 sm:grid-cols-2">
          <div><h2 className="mb-3 text-xl font-bold">Cast</h2><ul className="space-y-2">{m.cast_members.map((c) => <li key={c.name} className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-night text-sm font-bold text-white">{c.name[0]}</span><span><b className="block text-sm">{c.name}</b><span className="text-xs text-gray-500">{c.role}</span></span></li>)}</ul></div>
          <div><h2 className="mb-3 text-xl font-bold">Crew</h2><ul className="space-y-2">{m.crew.map((c) => <li key={c.name} className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-brand/10 text-sm font-bold text-brand">{c.name[0]}</span><span><b className="block text-sm">{c.name}</b><span className="text-xs text-gray-500">{c.role}</span></span></li>)}</ul></div>
        </section>
        {!upcoming && <Reviews movieId={m.id} />}
      </div>
      <Trailer id={m.trailer_youtube_id} open={trailer} onClose={() => setTrailer(false)} title={m.title} />
    </>
  )
}
