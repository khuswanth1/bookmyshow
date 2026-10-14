import { useMemo, useState } from 'react'
import { LocateFixed, MapPin, Search } from 'lucide-react'
import { useCity, useToast } from '../context/providers'
import { Button, Chip, Modal } from './ui'

export default function CityPicker() {
  const { city, cities, setCity, pickerOpen, closePicker, detect } = useCity()
  const [q, setQ] = useState('')
  const [region, setRegion] = useState('india')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  const list = useMemo(() => cities.filter((c) => c.region === region && c.name.toLowerCase().includes(q.trim().toLowerCase())), [cities, region, q])
  const popular = cities.filter((c) => c.is_popular && region === 'india' && !q)

  const useLocation = async () => {
    setBusy(true)
    try {
      const { city: c, distance_km } = await detect()
      setCity(c)
      toast.success(`Showing ${c.name}${distance_km > 150 ? ` (nearest available city, ${Math.round(distance_km)} km away)` : ''}`)
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <Modal open={pickerOpen} onClose={city ? closePicker : undefined} title="Choose your city" wide>
      <div className="space-y-4">
        <div className="relative">
          <label htmlFor="city-q" className="sr-only">Search cities</label>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
          <input id="city-q" data-autofocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search for your city"
            className="w-full rounded-lg border border-gray-300 py-2.5 pl-9 pr-3 text-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20" />
        </div>
        <Button variant="outline" onClick={useLocation} loading={busy} className="w-full"><LocateFixed className="h-4 w-4" />Detect my location</Button>
        <p className="-mt-2 text-xs text-gray-500">We only ask your browser for location when you click this button.</p>
        <div className="flex gap-2" role="group" aria-label="Region">
          <Chip active={region === 'india'} onClick={() => setRegion('india')}>India</Chip>
          <Chip active={region === 'international'} onClick={() => setRegion('international')}>International</Chip>
        </div>
        {popular.length > 0 && (
          <section aria-label="Popular cities">
            <h3 className="mb-2 text-sm font-semibold text-gray-500">Popular cities</h3>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {popular.map((c) => (
                <button key={c.id} onClick={() => setCity(c)} className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-left text-sm font-medium hover:border-brand hover:text-brand">
                  <MapPin className="h-3.5 w-3.5 shrink-0 text-brand" aria-hidden="true" />{c.name}
                </button>
              ))}
            </div>
          </section>
        )}
        <section aria-label="All cities">
          <h3 className="mb-2 text-sm font-semibold text-gray-500">{q ? 'Results' : 'All cities'}</h3>
          {list.length === 0 ? <p className="text-sm text-gray-500">No cities found.</p> : (
            <ul className="grid max-h-56 grid-cols-2 gap-x-4 gap-y-1 overflow-y-auto sm:grid-cols-3">
              {list.map((c) => (
                <li key={c.id}><button onClick={() => setCity(c)} className={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-gray-100 ${city?.id === c.id ? 'font-bold text-brand' : ''}`}>{c.name}<span className="ml-1 text-xs text-gray-400">{c.country !== 'India' ? c.country : ''}</span></button></li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Modal>
  )
}
