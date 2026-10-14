import L from 'leaflet'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import { useEffect } from 'react'

// Bundler-safe marker (avoids Leaflet's default image path lookup)
const pin = L.divIcon({
  className: '',
  html: '<div style="width:26px;height:26px;border-radius:50% 50% 50% 0;background:#f84464;transform:rotate(-45deg);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>',
  iconSize: [26, 26], iconAnchor: [13, 26], popupAnchor: [0, -24],
})

function Fit({ points }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points.map((p) => [p.lat, p.lng]), { padding: [30, 30], maxZoom: 14 })
    else if (points.length === 1) map.setView([points[0].lat, points[0].lng], 14)
  }, [points, map])
  return null
}

/** OpenStreetMap view. points: [{lat,lng,title,subtitle}] */
export default function MapView({ points, height = 280, className = '' }) {
  const pts = (points || []).filter((p) => p.lat != null && p.lng != null)
  if (!pts.length) return null
  return (
    <div className={`overflow-hidden rounded-xl ring-1 ring-black/10 ${className}`} style={{ height }}>
      <MapContainer center={[pts[0].lat, pts[0].lng]} zoom={13} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Fit points={pts} />
        {pts.map((p, i) => (
          <Marker key={i} position={[p.lat, p.lng]} icon={pin}>
            <Popup><b>{p.title}</b>{p.subtitle && <><br />{p.subtitle}</>}<br />
              <a href={`https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lng}#map=16/${p.lat}/${p.lng}`} target="_blank" rel="noreferrer">Open in OpenStreetMap</a></Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
