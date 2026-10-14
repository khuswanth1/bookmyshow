const BASE = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')
const KEY = 'bms_tokens'

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
  /** Map server validation details to {field: message} */
  get fieldErrors() {
    const out = {}
    if (Array.isArray(this.details)) for (const d of this.details) if (d.field) out[d.field.split('.').pop()] = d.message
    return out
  }
}

export const tokens = {
  get() {
    try { return JSON.parse(localStorage.getItem(KEY)) || null } catch { return null }
  },
  set(t) {
    try { t ? localStorage.setItem(KEY, JSON.stringify(t)) : localStorage.removeItem(KEY) } catch { /* private mode */ }
  },
}

let refreshing = null
async function refreshTokens() {
  const t = tokens.get()
  if (!t?.refresh_token) return null
  refreshing ||= fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
    .then(async (r) => {
      if (!r.ok) return null
      const d = await r.json()
      tokens.set({ access_token: d.access_token, refresh_token: d.refresh_token })
      return d
    })
    .catch(() => null)
    .finally(() => { refreshing = null })
  return refreshing
}

function qs(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null || v === '' || v === false) continue
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x))
    else sp.append(k, v)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

async function request(path, { method = 'GET', body, params, signal, retry = true } = {}) {
  const t = tokens.get()
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (t?.access_token) headers.Authorization = `Bearer ${t.access_token}`
  let res
  try {
    res = await fetch(`${BASE}${path}${qs(params)}`, {
      method, headers, signal, body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError(0, 'network', 'Cannot reach the server. Check your connection and try again.')
  }
  // A 401 on a normal call means the session is over unless a refresh rescues it. Without this, a tab whose tokens vanished
  // (storage cleared, signed out in another tab) kept polling forever as a "signed-in" user. Auth endpoints are excluded
  // so a wrong password does not look like an expired session.
  if (res.status === 401 && !path.startsWith('/auth/')) {
    if (retry && t?.refresh_token) {
      const d = await refreshTokens()
      if (d) return request(path, { method, body, params, signal, retry: false })
    }
    tokens.set(null)
    window.dispatchEvent(new Event('bms:logout'))
  }
  if (res.status === 204) return null
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) {
    const e = data?.error
    throw new ApiError(res.status, e?.code || 'error', e?.message || `Request failed (${res.status})`, e?.details)
  }
  return data
}

export const api = {
  get: (p, params, opts) => request(p, { params, ...opts }),
  post: (p, body, opts) => request(p, { method: 'POST', body: body ?? {}, ...opts }),
  put: (p, body, opts) => request(p, { method: 'PUT', body: body ?? {}, ...opts }),
  patch: (p, body, opts) => request(p, { method: 'PATCH', body, ...opts }),
  del: (p, opts) => request(p, { method: 'DELETE', ...opts }),
}

/** Authenticated file download (e.g. CSV exports) */
export async function download(path, params, filename) {
  const t = tokens.get()
  const res = await fetch(`${BASE}${path}${qs(params)}`, { headers: t?.access_token ? { Authorization: `Bearer ${t.access_token}` } : {} })
  if (!res.ok) {
    let e = null
    try { e = (await res.json()).error } catch { /* not json */ }
    throw new ApiError(res.status, e?.code || 'error', e?.message || `Download failed (${res.status})`)
  }
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function wsUrl(path) {
  const base = import.meta.env.VITE_WS_URL
  if (base) return `${base.replace(/\/$/, '')}${path}`
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const api = BASE.startsWith('http') ? BASE.replace(/^http/, 'ws') : `${proto}://${location.host}${BASE}`
  return `${api}${path}`
}

export const uuid = () =>
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random().toString(16).slice(2)}`).replace(/-/g, '')
