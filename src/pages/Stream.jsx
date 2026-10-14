import { useSearchParams, Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkCheck, BookmarkPlus, ExternalLink, Info, Tv } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { useTitle } from '../hooks'
import { ChipGroup, FilterShell, useUrlFilters } from '../components/filters'
import { VideoCard } from '../components/cards'
import { Badge, Button, Chip, EmptyState, ErrorState, Input, PageSpinner, Pagination, Poster } from '../components/ui'
import { secondsToClock } from '../lib/format'

function WatchButton({ video }) {
  const { user } = useAuth()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const m = useMutation({
    mutationFn: () => (video.in_watchlist ? api.del(`/videos/${video.id}/watchlist`) : api.put(`/videos/${video.id}/watchlist`)),
    onSuccess: (r) => { toast.success(r.message); qc.invalidateQueries({ queryKey: ['video'] }); qc.invalidateQueries({ queryKey: ['videos'] }) },
    onError: (e) => toast.error(e.message),
  })
  return (
    <Button variant="outline" loading={m.isPending} onClick={() => (user ? m.mutate() : nav('/login', { state: { from: `/stream/${video.id}` } }))} aria-pressed={video.in_watchlist}>
      {video.in_watchlist ? <BookmarkCheck className="h-4 w-4 text-brand" /> : <BookmarkPlus className="h-4 w-4" />}{video.in_watchlist ? 'In watchlist' : 'Add to watchlist'}
    </Button>
  )
}

export function StreamHome() {
  useTitle('Stream')
  const [params, setParams] = useSearchParams()
  const f = useUrlFilters(params, setParams)
  const { user } = useAuth()
  const genres = useQuery({ queryKey: ['genres'], queryFn: () => api.get('/genres'), staleTime: 3600_000 })
  const langs = useQuery({ queryKey: ['languages'], queryFn: () => api.get('/languages'), staleTime: 3600_000 })
  const tab = f.one('tab', 'browse')
  const query = { q: f.one('q') || undefined, genre_id: f.one('genre') || undefined, language_id: f.one('lang') || undefined, page: f.page, size: 12 }
  const list = useQuery({ queryKey: ['videos', query], queryFn: () => api.get('/videos', query), enabled: tab === 'browse', placeholderData: (p) => p })
  const featured = useQuery({ queryKey: ['videos', 'featured'], queryFn: () => api.get('/videos', { featured: true, size: 3 }) })
  const wl = useQuery({ queryKey: ['videos', 'watchlist', user?.id], enabled: tab === 'watchlist' && !!user, queryFn: () => api.get('/videos/watchlist') })
  const hero = featured.data?.items?.[0]
  return (
    <div className="container-x py-6">
      <h1 className="text-2xl font-bold sm:text-3xl">Stream</h1>
      <p className="mb-4 flex items-start gap-2 text-sm text-gray-500"><Info className="mt-0.5 h-4 w-4 shrink-0" />Only openly licensed films (Creative Commons) are streamed here, with attribution on every title.</p>
      {hero && tab === 'browse' && !f.one('q') && (
        <Link to={`/stream/${hero.id}`} className="relative mb-6 block overflow-hidden rounded-2xl p-6 text-white sm:p-10" style={{ background: `linear-gradient(110deg, ${hero.color_a}, ${hero.color_b} 160%)` }}>
          <Badge tone="dark" className="!bg-white/20">Featured</Badge>
          <h2 className="mt-2 max-w-lg text-3xl font-extrabold sm:text-4xl">{hero.title}</h2>
          <p className="mt-2 max-w-xl text-white/85">{hero.description}</p>
          <span className="mt-4 inline-block rounded-lg bg-white px-4 py-2 text-sm font-bold text-ink">▶ Watch now · {secondsToClock(hero.duration_sec)}</span>
        </Link>
      )}
      <div className="mb-4 flex flex-wrap gap-2"><Chip active={tab === 'browse'} onClick={() => f.set('tab', '')}>Browse</Chip><Chip active={tab === 'watchlist'} onClick={() => f.set('tab', 'watchlist')}>My watchlist</Chip></div>
      {tab === 'watchlist' ? (
        !user ? <EmptyState icon={Tv} title="Sign in to see your watchlist" action={<Link to="/login"><Button>Sign in</Button></Link>} /> :
        wl.isLoading ? <PageSpinner /> : wl.data?.length ? <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">{wl.data.map((v) => <VideoCard key={v.id} video={v} className="!w-full" />)}</div> :
        <EmptyState icon={Tv} title="Your watchlist is empty" text="Add titles with the bookmark button on any video page." />
      ) : (
        <div className="flex flex-col gap-6 lg:flex-row">
          <FilterShell activeCount={(f.one('genre') ? 1 : 0) + (f.one('lang') ? 1 : 0)} onClear={() => setParams(new URLSearchParams(), { replace: true })}>
            <div className="py-3"><Input type="search" label="Search titles" defaultValue={f.one('q')} onKeyDown={(e) => e.key === 'Enter' && f.set('q', e.currentTarget.value)} placeholder="Press Enter to search" /></div>
            <ChipGroup title="Genres" single options={genres.data || []} selected={f.one('genre') ? [f.one('genre')] : []} onChange={(v) => f.set('genre', v)} />
            <ChipGroup title="Languages" single options={langs.data || []} selected={f.one('lang') ? [f.one('lang')] : []} onChange={(v) => f.set('lang', v)} />
          </FilterShell>
          <div className="min-w-0 flex-1">
            {list.isError ? <ErrorState error={list.error} retry={list.refetch} /> : list.isLoading ? <PageSpinner /> : list.data.items.length === 0 ? <EmptyState icon={Tv} title="No videos found" /> : (
              <>
                <div className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 xl:grid-cols-4">{list.data.items.map((v) => <VideoCard key={v.id} video={v} className="!w-full" />)}</div>
                <Pagination page={list.data.page} pages={list.data.pages} onChange={f.setPage} />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function VideoPlayer() {
  const { id } = useParams()
  const { user } = useAuth()
  const { data: v, isLoading, isError, error, refetch } = useQuery({ queryKey: ['video', id, user?.id], queryFn: () => api.get(`/videos/${id}`) })
  const related = useQuery({ queryKey: ['videos', 'related'], queryFn: () => api.get('/videos', { size: 8 }) })
  useTitle(v?.title)
  if (isLoading) return <PageSpinner />
  if (isError) return <div className="container-x py-10"><ErrorState error={error} retry={refetch} /></div>
  return (
    <div className="container-x py-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div>
          <div className="aspect-video overflow-hidden rounded-xl bg-black shadow-lg">
            <video key={v.video_url} controls playsInline preload="metadata" className="h-full w-full" aria-label={`Video player: ${v.title}`}>
              <source src={v.video_url} type={v.video_url.endsWith('.webm') ? 'video/webm' : 'video/mp4'} />
              Your browser does not support HTML5 video.
            </video>
          </div>
          <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
            <div><h1 className="text-2xl font-bold">{v.title}</h1>
              <p className="text-sm text-gray-500">{v.year} · {secondsToClock(v.duration_sec)} · {v.language?.name} · {v.genres.map((g) => g.name).join(', ')}</p></div>
            <WatchButton video={v} />
          </div>
          <p className="mt-3 text-gray-700">{v.description}</p>
          <div className="mt-4 rounded-lg bg-white p-4 text-sm ring-1 ring-black/5">
            <p><b>License:</b> {v.license}</p><p className="text-gray-600">{v.attribution}</p>
            {v.source_url && <a href={v.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 font-semibold text-brand">Source & license <ExternalLink className="h-3.5 w-3.5" /></a>}
          </div>
        </div>
        <aside aria-label="More to watch"><h2 className="mb-3 font-bold">More to watch</h2>
          <ul className="space-y-3">{related.data?.items.filter((x) => x.id !== v.id).slice(0, 6).map((x) => (
            <li key={x.id}><Link to={`/stream/${x.id}`} className="flex gap-3 rounded-lg p-1 hover:bg-white">
              <Poster a={x.color_a} b={x.color_b} title={x.title} ratio="aspect-video" className="w-32 shrink-0" /><span className="text-sm font-semibold">{x.title}<span className="block text-xs font-normal text-gray-500">{x.year}</span></span></Link></li>
          ))}</ul></aside>
      </div>
    </div>
  )
}
