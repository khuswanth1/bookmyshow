/** paise -> "₹1,234.50" (drops .00) */
export function inr(paise) {
  const v = (paise || 0) / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', minimumFractionDigits: Number.isInteger(v) ? 0 : 2, maximumFractionDigits: 2,
  }).format(v)
}

export const fmtDate = (d, opts) =>
  d ? new Intl.DateTimeFormat('en-IN', opts || { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(d)) : ''

export const fmtTime = (d) =>
  d ? new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true }).format(new Date(d)).toUpperCase() : ''

export const fmtDateTime = (d) => (d ? `${fmtDate(d, { weekday: 'short', day: 'numeric', month: 'short' })}, ${fmtTime(d)}` : '')

export function duration(min) {
  if (!min) return ''
  const h = Math.floor(min / 60), m = min % 60
  return h ? `${h}h ${m ? `${m}m` : ''}`.trim() : `${m}m`
}

export function secondsToClock(s) {
  const m = Math.floor(s / 60), r = s % 60
  return `${m}:${String(r).padStart(2, '0')}`
}

/** Local YYYY-MM-DD (not UTC) */
export function ymd(d) {
  const x = new Date(d)
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
}

export const clsx = (...a) => a.filter(Boolean).join(' ')

export const SECTIONS = {
  events: { label: 'Events', blurb: 'Concerts, comedy, workshops and more' },
  plays: { label: 'Plays', blurb: 'Theatre, improv, puppetry and storytelling' },
  sports: { label: 'Sports', blurb: 'Runs, matches, tournaments and esports' },
  activities: { label: 'Activities', blurb: 'Adventures, food trails, nightlife and tours' },
}
