import { useEffect, useRef, useState } from 'react'

export function useDebounce(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function useTitle(title) {
  useEffect(() => {
    const prev = document.title
    document.title = title ? `${title} · BookMyShow Clone` : prev
    return () => { document.title = prev }
  }, [title])
}

/** Seconds remaining until `iso`; calls onExpire once. */
export function useCountdown(iso, onExpire) {
  const [left, setLeft] = useState(() => (iso ? Math.max(0, Math.floor((new Date(iso) - Date.now()) / 1000)) : 0))
  const fired = useRef(false)
  useEffect(() => {
    fired.current = false
    if (!iso) { setLeft(0); return }
    const tick = () => {
      const s = Math.max(0, Math.floor((new Date(iso) - Date.now()) / 1000))
      setLeft(s)
      if (s === 0 && !fired.current) { fired.current = true; onExpire?.() }
    }
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [iso]) // eslint-disable-line react-hooks/exhaustive-deps
  return left
}

let rzpPromise
export function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve(window.Razorpay)
  rzpPromise ||= new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://checkout.razorpay.com/v1/checkout.js'
    s.onload = () => resolve(window.Razorpay)
    s.onerror = () => { rzpPromise = null; reject(new Error('Could not load the payment window. Check your connection.')) }
    document.head.appendChild(s)
  })
  return rzpPromise
}

let gsiPromise
export function loadGoogle() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google)
  gsiPromise ||= new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = () => resolve(window.google)
    s.onerror = () => { gsiPromise = null; reject(new Error('Could not load Google sign-in')) }
    document.head.appendChild(s)
  })
  return gsiPromise
}
