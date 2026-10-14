import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Gift, Percent, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import { useCity } from '../context/providers'
import { CardSkeletons, EventCard, MovieCard, SectionHeader, VideoCard } from '../components/cards'
import { ErrorState, Poster } from '../components/ui'
import { fmtDate, SECTIONS } from '../lib/format'
import { useTitle } from '../hooks'

function Hero({ items }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (items.length < 2) return
    const t = setInterval(() => setI((x) => (x + 1) % items.length), 6000)
    return () => clearInterval(t)
  }, [items.length])
  if (!items.length) return null
  const it = items[i % items.length]
  return (
    <section aria-roledescription="carousel" aria-label="Featured" className="relative overflow-hidden bg-night">
      <div className="container-x relative">
        <Link to={it.to} className="relative block h-56 overflow-hidden rounded-none sm:h-72 md:h-80 md:rounded-b-2xl" style={{ background: `linear-gradient(110deg, ${it.a} 10%, ${it.b} 130%)` }}>
          <div className="absolute inset-0 opacity-25" style={{ background: 'radial-gradient(circle at 85% 20%, #fff 0, transparent 40%)' }} />
          <div className="relative flex h-full max-w-xl flex-col justify-center gap-2 p-6 text-white sm:p-10">
            <span className="w-fit rounded bg-white/20 px-2 py-0.5 text-xs font-bold uppercase tracking-wider backdrop-blur">{it.tag}</span>
            <h2 className="text-3xl font-extrabold leading-tight drop-shadow sm:text-5xl">{it.title}</h2>
            <p className="line-clamp-2 text-sm text-white/85 sm:text-base">{it.sub}</p>
            <span className="mt-2 w-fit rounded-lg bg-white px-4 py-2 text-sm font-bold text-ink">{it.cta}</span>
          </div>
        </Link>
        {items.length > 1 && (
          <>
            <button aria-label="Previous slide" onClick={() => setI((i - 1 + items.length) % items.length)} className="absolute left-6 top-1/2 hidden -translate-y-1/2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60 sm:block"><ChevronLeft /></button>
            <button aria-label="Next slide" onClick={() => setI((i + 1) % items.length)} className="absolute right-6 top-1/2 hidden -translate-y-1/2 rounded-full bg-black/40 p-2 text-white hover:bg-black/60 sm:block"><ChevronRight /></button>
            <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5">
              {items.map((_, k) => <button key={k} aria-label={`Slide ${k + 1}`} aria-current={k === i} onClick={() => setI(k)} className={`h-2 rounded-full transition-all ${k === i ? 'w-6 bg-white' : 'w-2 bg-white/50'}`} />)}
            </div>
          </>
        )}
      </div>
    </section>
  )
}

export default function Home() {
  useTitle('Movies, events, plays, sports & activities')
  const { city } = useCity()
  const cid = city?.id
  const live = { staleTime: 0, refetchOnWindowFocus: true, refetchInterval: 15000 }
  const movies = useQuery({ queryKey: ['movies', 'home', cid], queryFn: () => api.get('/movies', { status: 'now_showing', city_id: cid, size: 12 }), ...live })
  const soon = useQuery({ queryKey: ['movies', 'soon'], queryFn: () => api.get('/movies', { status: 'coming_soon', size: 12, sort: 'release' }), ...live })
  const featured = useQuery({ queryKey: ['events', 'featured', cid], queryFn: () => api.get('/events', { featured: true, city_id: cid, size: 8 }), ...live })
  const exclusive = useQuery({ queryKey: ['events', 'exclusive'], queryFn: () => api.get('/events', { exclusive: true, size: 6 }), ...live })
  const bySection = useQuery({
    ...live,
    queryKey: ['events', 'by-section', cid],
    queryFn: async () => Object.fromEntries(await Promise.all(Object.keys(SECTIONS).map(async (s) => [s, (await api.get('/events', { section: s, city_id: cid, size: 4 })).items]))),
  })
  const videos = useQuery({ queryKey: ['videos', 'home'], queryFn: () => api.get('/videos', { size: 10 }) })
  const offers = useQuery({ queryKey: ['offers'], queryFn: () => api.get('/offers') })

  const hero = [
    ...(featured.data?.items || []).slice(0, 3).map((e) => ({ to: `/event/${e.id}`, title: e.title, sub: `${e.venue_name}, ${e.city.name} · ${fmtDate(e.starts_at)}`, tag: e.category.name, a: e.color_a, b: e.color_b, cta: 'Book tickets' })),
    ...(movies.data?.items || []).slice(0, 2).map((m) => ({ to: `/movies/${m.id}`, title: m.title, sub: m.synopsis, tag: 'Now showing', a: m.color_a, b: m.color_b, cta: 'Book now' })),
  ]

  return (
    <>
      <Hero items={hero} />
      <div className="container-x space-y-12 py-8">
        <section aria-labelledby="h-movies">
          <SectionHeader title="Recommended movies" to="/movies" sub={city ? `Now showing in ${city.name}` : undefined} />
          <h2 id="h-movies" className="sr-only">Recommended movies</h2>
          {movies.isError ? <ErrorState error={movies.error} retry={movies.refetch} /> : (
            <div className="scroll-x">{movies.isLoading ? <CardSkeletons tall /> : movies.data.items.length ? movies.data.items.map((m) => <MovieCard key={m.id} movie={m} />) : <p className="text-sm text-gray-500">No movies are playing in this city right now.</p>}</div>
          )}
        </section>

        {(offers.data || []).length > 0 && (
          <section aria-label="Offers" className="grid gap-3 sm:grid-cols-3">
            {offers.data.slice(0, 3).map((o, i) => (
              <Link key={o.id} to="/offers" className="flex items-center gap-3 rounded-xl p-4 text-white shadow-sm transition hover:shadow-md" style={{ background: ['linear-gradient(120deg,#be123c,#f97316)', 'linear-gradient(120deg,#4338ca,#06b6d4)', 'linear-gradient(120deg,#047857,#a3e635)'][i % 3] }}>
                <Percent className="h-8 w-8 shrink-0" aria-hidden="true" />
                <div><p className="font-bold leading-tight">{o.title}</p><p className="text-xs text-white/85">Use code <b>{o.code}</b></p></div>
              </Link>
            ))}
          </section>
        )}

        {(featured.data?.items || []).length > 0 && (
          <section>
            <SectionHeader title="Featured events" to="/events" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{featured.data.items.slice(0, 4).map((e) => <EventCard key={e.id} event={e} />)}</div>
          </section>
        )}

        {Object.entries(SECTIONS).map(([key, s]) => {
          const items = bySection.data?.[key] || []
          if (!bySection.isLoading && !items.length) return null
          return (
            <section key={key}>
              <SectionHeader title={s.label} sub={s.blurb} to={`/${key}`} />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{bySection.isLoading ? <CardSkeletons n={4} /> : items.map((e) => <EventCard key={e.id} event={e} />)}</div>
            </section>
          )
        })}

        {(exclusive.data?.items || []).length > 0 && (
          <section className="rounded-2xl bg-night p-5 text-white">
            <SectionHeader title="BookMyShow Exclusives" sub="Only here" to="/exclusives" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 [&_.card]:text-ink">{exclusive.data.items.slice(0, 3).map((e) => <EventCard key={e.id} event={e} />)}</div>
          </section>
        )}

        <section>
          <SectionHeader title="Coming soon" to="/movies?status=coming_soon" />
          <div className="scroll-x">{soon.isLoading ? <CardSkeletons tall /> : soon.data?.items.map((m) => <MovieCard key={m.id} movie={m} />)}</div>
        </section>

        <section>
          <SectionHeader title="Stream" sub="Openly licensed films to watch right now" to="/stream" />
          <div className="scroll-x">{videos.isLoading ? <CardSkeletons /> : videos.data?.items.map((v) => <VideoCard key={v.id} video={v} />)}</div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2">
          <Link to="/gift-cards" className="card flex items-center gap-4 p-5 hover:shadow-md"><Gift className="h-10 w-10 text-brand" /><div><h2 className="font-bold">Gift a night out</h2><p className="text-sm text-gray-500">Digital gift cards, redeemable on any booking.</p></div></Link>
          <Link to="/list-your-show" className="card flex items-center gap-4 p-5 hover:shadow-md"><Sparkles className="h-10 w-10 text-brand" /><div><h2 className="font-bold">Hosting a show?</h2><p className="text-sm text-gray-500">List it on ListYourShow and sell tickets in minutes.</p></div></Link>
        </section>
      </div>
    </>
  )
}
