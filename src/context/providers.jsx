import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, tokens, wsUrl } from '../lib/api'
import { CheckCircle2, Info, XCircle } from 'lucide-react'

/* ---------------------------------------------------------------- Toasts */
const ToastCtx = createContext(null)
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, type = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setItems((l) => [...l, { id, message, type }])
    setTimeout(() => setItems((l) => l.filter((t) => t.id !== id)), 5000)
  }, [])
  const api_ = useMemo(() => ({
    success: (m) => push(m, 'success'), error: (m) => push(m, 'error'), info: (m) => push(m, 'info'),
  }), [push])
  const Icon = { success: CheckCircle2, error: XCircle, info: Info }
  return (
    <ToastCtx.Provider value={api_}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[200] flex w-[min(92vw,22rem)] flex-col gap-2">
        {items.map((t) => {
          const I = Icon[t.type]
          return (
            <div key={t.id} role={t.type === 'error' ? 'alert' : 'status'}
              className={`pointer-events-auto flex items-start gap-2 rounded-lg px-4 py-3 text-sm text-white shadow-lg ${t.type === 'error' ? 'bg-red-600' : t.type === 'success' ? 'bg-emerald-600' : 'bg-night'}`}>
              <I className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /><span>{t.message}</span>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

/* ---------------------------------------------------------------- Auth */
const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!tokens.get())
  const toast = useToast()
  const qc = useQueryClient()

  const setSession = useCallback((d) => {
    tokens.set({ access_token: d.access_token, refresh_token: d.refresh_token })
    setUser(d.user)
    return d.user
  }, [])

  useEffect(() => {
    if (!tokens.get()) return
    api.get('/users/me').then(setUser).catch(() => tokens.set(null)).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const h = () => { setUser(null); qc.clear() }
    window.addEventListener('bms:logout', h)
    return () => window.removeEventListener('bms:logout', h)
  }, [qc])

  // Private realtime channel: booking confirmations / notifications
  const wsRef = useRef(null)
  useEffect(() => {
    if (!user) return
    const t = tokens.get()?.access_token
    if (!t) return
    let closed = false, retry, failures = 0
    const connect = () => {
      const ws = new WebSocket(wsUrl(`/ws/me?token=${encodeURIComponent(tokens.get()?.access_token || t)}`))
      wsRef.current = ws
      ws.onopen = () => { failures = 0 }
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data)
          if (m.type === 'notification') toast.info(m.title)
          qc.invalidateQueries({ queryKey: ['notifications'] })
          if (m.type === 'booking') qc.invalidateQueries({ queryKey: ['bookings'] })
        } catch { /* ignore */ }
      }
      // The access token lives 30 minutes and the server refuses an expired one (403 before the socket opens), so any
      // failed connect first makes a normal API call, which refreshes the token, then retries with back-off.
      ws.onclose = () => {
        if (closed) return
        failures += 1
        retry = setTimeout(async () => {
          await api.get('/users/me').catch(() => {})
          if (!closed) connect()
        }, Math.min(4000 * 2 ** (failures - 1), 60000))
      }
    }
    connect()
    const ping = setInterval(() => wsRef.current?.readyState === 1 && wsRef.current.send('ping'), 25000)
    return () => { closed = true; clearTimeout(retry); clearInterval(ping); wsRef.current?.close() }
  }, [user?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(() => ({
    user, loading,
    login: async (email, password) => setSession(await api.post('/auth/login', { email, password })),
    register: async (body) => setSession(await api.post('/auth/register', body)),
    google: async (credential) => setSession(await api.post('/auth/google', { credential })),
    logout: () => { tokens.set(null); setUser(null); qc.clear() },
    updateUser: setUser,
  }), [user, loading, setSession, qc])

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

/* ---------------------------------------------------------------- City */
const CityCtx = createContext(null)
export const useCity = () => useContext(CityCtx)
const CITY_KEY = 'bms_city'

export function CityProvider({ children }) {
  const [city, setCityState] = useState(() => {
    try { return JSON.parse(localStorage.getItem(CITY_KEY)) } catch { return null }
  })
  const [pickerOpen, setPickerOpen] = useState(false)
  const { data: cities = [], isLoading } = useQuery({ queryKey: ['cities'], queryFn: () => api.get('/cities'), staleTime: 3600_000 })

  const setCity = useCallback((c) => {
    setCityState(c)
    try { localStorage.setItem(CITY_KEY, JSON.stringify(c)) } catch { /* ignore */ }
    setPickerOpen(false)
  }, [])

  // First visit: ask for a city (never request geolocation without a click)
  useEffect(() => { if (!city && !isLoading && cities.length) setPickerOpen(true) }, [city, isLoading, cities.length])
  // Drop a stored city that no longer exists/is inactive
  useEffect(() => {
    if (city && cities.length && !cities.some((c) => c.id === city.id)) setCityState(null)
  }, [city, cities])

  const detect = useCallback(() => new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error('Location is not supported by this browser'))
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try { resolve(await api.get('/cities/detect', { lat: pos.coords.latitude, lng: pos.coords.longitude })) } catch (e) { reject(e) }
      },
      (err) => reject(new Error(err.code === 1 ? 'Location permission was denied. Pick a city manually.' : 'Could not get your location')),
      { timeout: 10000, maximumAge: 600000 },
    )
  }), [])

  const value = useMemo(() => ({ city, cities, setCity, pickerOpen, openPicker: () => setPickerOpen(true), closePicker: () => setPickerOpen(false), detect }),
    [city, cities, setCity, pickerOpen, detect])
  return <CityCtx.Provider value={value}>{children}</CityCtx.Provider>
}
