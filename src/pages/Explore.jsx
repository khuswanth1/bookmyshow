import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarX } from 'lucide-react'
import { api } from '../lib/api'
import { useCity } from '../context/providers'
import { useTitle } from '../hooks'
import { ChipGroup, FilterShell, useUrlFilters } from '../components/filters'
import { CardSkeletons, EventCard } from '../components/cards'
import { Chip, EmptyState, ErrorState, Input, Pagination, Select, Toggle } from '../components/ui'
import { SECTIONS, ymd } from '../lib/format'

const PRICES = [['', 'Any price'], ['0-0', 'Free'], ['0-50000', 'Under ₹500'], ['50000-150000', '₹500 – ₹1,500'], ['150000-', 'Above ₹1,500']]

/** Shared listing for Events / Plays / Sports / Activities / Exclusives */
export default function Explore({ section, exclusive = false, title: forcedTitle }) {
  const meta = section ? SECTIONS[section] : { label: forcedTitle || 'Exclusives', blurb: 'Experiences you can only book here' }
  useTitle(meta.label)
  const [params, setParams] = useSearchParams()
  const f = useUrlFilters(params, setParams)
  const { city } = useCity()
  const cats = useQuery({ queryKey: ['categories', section], queryFn: () => api.get('/categories', { section }), enabled: !!section, staleTime: 3600_000 })
  const langs = useQuery({ queryKey: ['languages'], queryFn: () => api.get('/languages'), staleTime: 3600_000 })

  const [minP, maxP] = (f.one('price') || '-').split('-')
  const when = f.one('when')
  const today = new Date()
  const range = { today: [ymd(today), ymd(today)], tomorrow: [ymd(new Date(+today + 864e5)), ymd(new Date(+today + 864e5))], weekend: (() => { const d = today.getDay(); const sat = new Date(+today + ((6 - d + 7) % 7) * 864e5); return [ymd(sat), ymd(new Date(+sat + 864e5))] })(), week: [ymd(today), ymd(new Date(+today + 7 * 864e5))] }[when] || [f.one('from'), f.one('to')]
  const query = {
    section, exclusive: exclusive || undefined, city_id: city?.id, category_id: f.get('cat'), language_id: f.get('lang'), q: f.one('q') || undefined,
    date_from: range[0] || undefined, date_to: range[1] || undefined, min_price_paise: minP || undefined, max_price_paise: maxP || undefined,
    available_only: f.one('avail') === '1', sort: f.one('sort', 'date'), page: f.page, size: 12,
  }
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({ queryKey: ['events', query], queryFn: () => api.get('/events', query), placeholderData: (p) => p })
  const active = f.get('cat').length + f.get('lang').length + (f.one('price') ? 1 : 0) + (when || f.one('from') ? 1 : 0) + (f.one('avail') ? 1 : 0)

  return (
    <div className="container-x py-6">
      <h1 className="text-2xl font-bold sm:text-3xl">{meta.label}{city ? ` in ${city.name}` : ''}</h1>
      <p className="text-sm text-gray-500">{meta.blurb}</p>
      <div className="mb-5 mt-4 flex flex-wrap items-end gap-2">
        {[['', 'Any date'], ['today', 'Today'], ['tomorrow', 'Tomorrow'], ['weekend', 'This weekend'], ['week', 'Next 7 days']].map(([k, l]) => <Chip key={k} active={when === k || (!k && !when)} onClick={() => f.set('when', k)}>{l}</Chip>)}
        <div className="ml-auto flex gap-2">
          <Input aria-label="Search within results" type="search" placeholder="Search…" defaultValue={f.one('q')} onKeyDown={(e) => e.key === 'Enter' && f.set('q', e.currentTarget.value)} className="w-44" />
          <Select aria-label="Sort" value={f.one('sort', 'date')} onChange={(e) => f.set('sort', e.target.value)} className="w-40">
            <option value="date">Date</option><option value="price_asc">Price: low to high</option><option value="price_desc">Price: high to low</option><option value="newest">Newest</option>
          </Select>
        </div>
      </div>
      <div className="flex flex-col gap-6 lg:flex-row">
        <FilterShell activeCount={active} onClear={() => setParams(new URLSearchParams(), { replace: true })}>
          {section && <ChipGroup title="Categories" options={cats.data || []} selected={f.get('cat')} onChange={(v) => f.set('cat', v)} />}
          <ChipGroup title="Languages" options={langs.data || []} selected={f.get('lang')} onChange={(v) => f.set('lang', v)} />
          <ChipGroup title="Price" single options={PRICES.slice(1).map(([id, name]) => ({ id, name }))} selected={f.one('price') ? [f.one('price')] : []} onChange={(v) => f.set('price', v)} />
          <div className="py-3"><Toggle checked={f.one('avail') === '1'} onChange={(v) => f.set('avail', v ? '1' : '')} label="Hide sold-out" /></div>
        </FilterShell>
        <div className="min-w-0 flex-1" aria-busy={isFetching}>
          {isError ? <ErrorState error={error} retry={refetch} /> : isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><CardSkeletons n={6} /></div>
          ) : data.items.length === 0 ? (
            <EmptyState icon={CalendarX} title="Nothing found" text={`No ${meta.label.toLowerCase()} match your filters in ${city?.name || 'this city'}. Try a different date, category or city.`} />
          ) : (
            <>
              <p className="mb-3 text-sm text-gray-500">{data.total} result{data.total === 1 ? '' : 's'}</p>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{data.items.map((e) => <EventCard key={e.id} event={e} />)}</div>
              <Pagination page={data.page} pages={data.pages} onChange={f.setPage} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
