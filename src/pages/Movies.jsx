import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Film } from 'lucide-react'
import { api } from '../lib/api'
import { useCity } from '../context/providers'
import { useTitle } from '../hooks'
import { ChipGroup, FilterShell, useUrlFilters } from '../components/filters'
import { MovieCard } from '../components/cards'
import { Chip, EmptyState, ErrorState, Pagination, Select } from '../components/ui'

export default function Movies() {
  useTitle('Movies')
  const [params, setParams] = useSearchParams()
  const f = useUrlFilters(params, setParams)
  const { city } = useCity()
  const status = f.one('status', 'now_showing')
  const genres = useQuery({ queryKey: ['genres'], queryFn: () => api.get('/genres'), staleTime: 3600_000 })
  const langs = useQuery({ queryKey: ['languages'], queryFn: () => api.get('/languages'), staleTime: 3600_000 })

  const query = {
    status, city_id: status === 'now_showing' ? city?.id : undefined, genre_id: f.get('genre'), language_id: f.get('lang'),
    min_rating: f.one('rating') || undefined, sort: f.one('sort', 'popular'), q: f.one('q') || undefined, page: f.page, size: 20,
  }
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({ queryKey: ['movies', query], queryFn: () => api.get('/movies', query), placeholderData: (p) => p })
  const active = f.get('genre').length + f.get('lang').length + (f.one('rating') ? 1 : 0)
  const clear = () => setParams(new URLSearchParams({ status }), { replace: true })

  return (
    <div className="container-x py-6">
      <h1 className="mb-1 text-2xl font-bold sm:text-3xl">Movies{status === 'now_showing' && city ? ` in ${city.name}` : ''}</h1>
      <div className="mb-5 mt-3 flex flex-wrap items-center gap-2">
        <Chip active={status === 'now_showing'} onClick={() => f.set('status', 'now_showing')}>Now showing</Chip>
        <Chip active={status === 'coming_soon'} onClick={() => f.set('status', 'coming_soon')}>Coming soon</Chip>
        <div className="ml-auto flex items-center gap-2">
          <Select aria-label="Sort movies" value={f.one('sort', 'popular')} onChange={(e) => f.set('sort', e.target.value)} className="w-40">
            <option value="popular">Popularity</option><option value="rating">Rating</option><option value="release">Release date</option><option value="title">A–Z</option>
          </Select>
        </div>
      </div>
      <div className="flex flex-col gap-6 lg:flex-row">
        <FilterShell activeCount={active} onClear={clear}>
          <ChipGroup title="Languages" options={langs.data || []} selected={f.get('lang')} onChange={(v) => f.set('lang', v)} />
          <ChipGroup title="Genres" options={genres.data || []} selected={f.get('genre')} onChange={(v) => f.set('genre', v)} />
          <ChipGroup title="Minimum rating" single options={[6, 7, 8, 9].map((n) => ({ id: n, name: `${n}+ ★` }))} selected={f.one('rating') ? [f.one('rating')] : []} onChange={(v) => f.set('rating', v)} />
        </FilterShell>
        <div className="min-w-0 flex-1" aria-busy={isFetching}>
          {isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton aspect-[2/3] rounded-xl" />)}</div>
          ) : data.items.length === 0 ? (
            <EmptyState icon={Film} title="No movies match" text="Try removing a filter or choosing another city." />
          ) : (
            <>
              <p className="mb-3 text-sm text-gray-500">{data.total} movie{data.total === 1 ? '' : 's'}</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 xl:grid-cols-4">
                {data.items.map((m) => <MovieCard key={m.id} movie={m} className="!w-full" />)}
              </div>
              <Pagination page={data.page} pages={data.pages} onChange={f.setPage} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
