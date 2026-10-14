export const required = (label) => (v) => (String(v ?? '').trim() ? '' : `${label} is required`)
export const email = (v) => (/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(v || '').trim()) ? '' : 'Enter a valid email address')
export const phone = (v) => (!v || /^\+?[0-9]{8,15}$/.test(v) ? '' : 'Enter 8–15 digits, optionally starting with +')
export const phoneRequired = (v) => (/^\+?[0-9]{8,15}$/.test(v || '') ? '' : 'Enter 8–15 digits, optionally starting with +')
export const password = (v) =>
  !v || v.length < 8 ? 'Use at least 8 characters'
    : !/[A-Za-z]/.test(v) || !/\d/.test(v) ? 'Include both letters and numbers' : ''
export const minLen = (n, label) => (v) => (String(v || '').trim().length >= n ? '' : `${label} must be at least ${n} characters`)

/** validate({field: [fn,...]}, values) -> {field: msg} (first failing rule per field) */
export function validate(rules, values) {
  const errs = {}
  for (const [k, fns] of Object.entries(rules)) {
    for (const fn of fns) {
      const m = fn(values[k], values)
      if (m) { errs[k] = m; break }
    }
  }
  return errs
}
