import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Calendar, Heart, MapPin, Play } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { Badge, Poster, Rating } from './ui'
import { duration, fmtDate, inr, secondsToClock } from '../lib/format'

export function useFavorites() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const nav = useNavigate()
  const { data } = useQuery({ queryKey: ['favorites'], enabled: !!user, queryFn: () => api.get('/favorites') })
  const keys = new Set(data?.keys || [])
  const m = useMutation({
    mutationFn: ({ type, id, on }) => (on ? api.del(`/favorites/${type}/${id}`) : api.put(`/favorites/${type}/${id}`)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['favorites'] }),
    onError: (e) => toast.error(e.message),
  })
  return {
    has: (type, id) => keys.has(`${type}:${id}`),
    toggle: (type, id) => {
      if (!user) { toast.info('Sign in to save favorites'); return nav('/login', { state: { from: location.pathname } }) }
      m.mutate({ type, id, on: keys.has(`${type}:${id}`) })
    },
  }
}

export function FavButton({ type, id, className = '' }) {
  const fav = useFavorites()
  const on = fav.has(type, id)
  return (
    <button onClick={(e) => { e.preventDefault(); e.stopPropagation(); fav.toggle(type, id) }} aria-pressed={on} aria-label={on ? 'Remove from favorites' : 'Add to favorites'}
      className={`rounded-full bg-black/45 p-1.5 text-white backdrop-blur hover:bg-black/65 ${className}`}>
      <Heart className={`h-4 w-4 ${on ? 'fill-brand text-brand' : ''}`} />
    </button>
  )
}

export function MovieCard({ movie, className = '' }) {
  const upcoming = new Date(movie.release_date) > new Date()
  return (
    <Link to={`/movies/${movie.id}`} className={`group block w-40 shrink-0 sm:w-44 ${className}`}>
      <div className="relative">
        <Poster a={movie.color_a} b={movie.color_b} url={movie.poster_url} title={movie.title} badge={upcoming ? `Releases ${fmtDate(movie.release_date, { day: 'numeric', month: 'short' })}` : movie.certificate}
          className="transition group-hover:shadow-lg group-hover:ring-2 group-hover:ring-brand" />
        <FavButton type="movie" id={movie.id} className="absolute right-2 top-2" />
      </div>
      <h3 className="mt-2 line-clamp-1 text-sm font-semibold group-hover:text-brand">{movie.title}</h3>
      <p className="line-clamp-1 text-xs text-gray-500">{movie.genres.map((g) => g.name).join(' / ')}</p>
      {!upcoming && <div className="mt-0.5"><Rating value={movie.rating_avg} count={movie.rating_count} /></div>}
    </Link>
  )
}

export function EventCard({ event, className = '' }) {
  return (
    <Link to={`/event/${event.id}`} className={`group card block overflow-hidden transition hover:shadow-lg ${className}`}>
      <div className="relative">
        <Poster a={event.color_a} b={event.color_b} url={event.image_url} title={event.title} ratio="aspect-[16/10]" className="rounded-none" />
        <FavButton type="event" id={event.id} className="absolute right-2 top-2" />
        <div className="absolute left-2 top-2 flex gap-1">
          {event.is_exclusive && <Badge tone="dark">Exclusive</Badge>}
          {event.sold_out && <Badge tone="red">Sold out</Badge>}
        </div>
      </div>
      <div className="p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand">{event.category.name}</p>
        <h3 className="mt-0.5 line-clamp-1 font-semibold group-hover:text-brand">{event.title}</h3>
        <p className="mt-1 flex items-center gap-1 text-xs text-gray-500"><Calendar className="h-3.5 w-3.5" aria-hidden="true" />{fmtDate(event.starts_at, { weekday: 'short', day: 'numeric', month: 'short' })}</p>
        <p className="flex items-center gap-1 text-xs text-gray-500"><MapPin className="h-3.5 w-3.5" aria-hidden="true" /><span className="line-clamp-1">{event.venue_name}, {event.city.name}</span></p>
        <p className="mt-2 text-sm font-bold">{event.min_price_paise === 0 ? 'Free' : <>From {inr(event.min_price_paise)}</>}</p>
      </div>
    </Link>
  )
}

export function VideoCard({ video, className = '' }) {
  return (
    <Link to={`/stream/${video.id}`} className={`group block w-56 shrink-0 ${className}`}>
      <div className="relative">
        <Poster a={video.color_a} b={video.color_b} url={video.thumbnail_url} title={video.title} ratio="aspect-video" className="group-hover:ring-2 group-hover:ring-brand" />
        <span className="absolute inset-0 grid place-items-center opacity-0 transition group-hover:opacity-100"><span className="rounded-full bg-black/60 p-3 text-white"><Play className="h-5 w-5 fill-white" /></span></span>
        <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-xs text-white">{secondsToClock(video.duration_sec)}</span>
      </div>
      <h3 className="mt-2 line-clamp-1 text-sm font-semibold group-hover:text-brand">{video.title}</h3>
      <p className="text-xs text-gray-500">{video.year} · {video.genres.map((g) => g.name).slice(0, 2).join(', ')}</p>
    </Link>
  )
}

export function SectionHeader({ title, to, linkText = 'See all', sub }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div><h2 className="text-xl font-bold sm:text-2xl">{title}</h2>{sub && <p className="text-sm text-gray-500">{sub}</p>}</div>
      {to && <Link to={to} className="shrink-0 text-sm font-semibold text-brand hover:underline">{linkText} ›</Link>}
    </div>
  )
}

export function CardSkeletons({ n = 6, tall }) {
  return Array.from({ length: n }, (_, i) => (
    <div key={i} className={`shrink-0 ${tall ? 'w-44' : 'w-full'}`} aria-hidden="true">
      <div className={`skeleton rounded-xl ${tall ? 'aspect-[2/3]' : 'aspect-[16/10]'}`} />
      <div className="skeleton mt-2 h-4 w-3/4 rounded" /><div className="skeleton mt-1 h-3 w-1/2 rounded" />
    </div>
  ))
}
