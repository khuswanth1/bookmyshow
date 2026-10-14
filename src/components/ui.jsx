import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, ChevronLeft, ChevronRight, Eye, EyeOff, Loader2, X } from 'lucide-react'
import { clsx } from '../lib/format'

export function Spinner({ className = '', label = 'Loading' }) {
  return <Loader2 role="status" aria-label={label} className={clsx('animate-spin text-brand', className || 'h-6 w-6')} />
}

export function PageSpinner() {
  return <div className="flex min-h-[40vh] items-center justify-center"><Spinner className="h-8 w-8" /></div>
}

export function Skeleton({ className = '' }) {
  return <div aria-hidden="true" className={clsx('skeleton rounded-lg', className)} />
}

const variants = {
  primary: 'bg-brand text-white hover:bg-brand-dark disabled:bg-brand/50',
  dark: 'bg-night text-white hover:bg-ink disabled:bg-night/50',
  outline: 'border border-gray-300 bg-white text-ink hover:border-brand hover:text-brand disabled:opacity-50',
  ghost: 'text-ink hover:bg-black/5 disabled:opacity-50',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
}
export function Button({ variant = 'primary', size = 'md', loading, className = '', children, ...p }) {
  const sizes = { sm: 'px-3 py-1.5 text-sm', md: 'px-4 py-2.5 text-sm', lg: 'px-6 py-3 text-base' }
  return (
    <button
      {...p}
      disabled={p.disabled || loading}
      aria-busy={loading || undefined}
      className={clsx('inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition disabled:cursor-not-allowed', variants[variant], sizes[size], className)}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  )
}

export function Field({ label, error, hint, children, className = '', id }) {
  const gen = useId()
  const fid = id || gen
  const described = [error && `${fid}-err`, hint && `${fid}-hint`].filter(Boolean).join(' ') || undefined
  return (
    <div className={className}>
      {label && <label htmlFor={fid} className="mb-1 block text-sm font-medium text-ink">{label}</label>}
      {typeof children === 'function' ? children({ id: fid, 'aria-invalid': !!error || undefined, 'aria-describedby': described }) : children}
      {hint && !error && <p id={`${fid}-hint`} className="mt-1 text-xs text-gray-500">{hint}</p>}
      {error && <p id={`${fid}-err`} role="alert" className="mt-1 text-xs font-medium text-red-600">{error}</p>}
    </div>
  )
}

const inputCls = 'w-full rounded-lg border border-gray-300 bg-white px-3 py-2.5 text-sm text-ink placeholder:text-gray-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 aria-[invalid=true]:border-red-500 disabled:bg-gray-100'

export function Input({ label, error, hint, className = '', ...p }) {
  const [show, setShow] = useState(false)
  const isPw = p.type === 'password'
  return (
    <Field label={label} error={error} hint={hint} id={p.id} className={className}>
      {(a) => isPw ? (
        <div className="relative">
          <input {...a} {...p} type={show ? 'text' : 'password'} className={clsx(inputCls, 'pr-10')} />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? 'Hide password' : 'Show password'}
            aria-pressed={show}
            className="absolute inset-y-0 right-0 flex items-center px-3 text-gray-500 hover:text-ink"
          >
            {show ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
          </button>
        </div>
      ) : <input {...a} {...p} className={inputCls} />}
    </Field>
  )
}
export function Textarea({ label, error, hint, className = '', rows = 4, ...p }) {
  return (
    <Field label={label} error={error} hint={hint} id={p.id} className={className}>
      {(a) => <textarea {...a} rows={rows} {...p} className={inputCls} />}
    </Field>
  )
}
export function Select({ label, error, hint, className = '', children, ...p }) {
  return (
    <Field label={label} error={error} hint={hint} id={p.id} className={className}>
      {(a) => <select {...a} {...p} className={inputCls}>{children}</select>}
    </Field>
  )
}

export function Badge({ children, tone = 'gray', className = '' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-700', brand: 'bg-brand/10 text-brand', green: 'bg-emerald-100 text-emerald-700',
    amber: 'bg-amber-100 text-amber-800', red: 'bg-red-100 text-red-700', blue: 'bg-sky-100 text-sky-700', dark: 'bg-night text-white',
  }
  return <span className={clsx('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', tones[tone], className)}>{children}</span>
}

export const statusTone = (s) =>
  ({ confirmed: 'green', paid: 'green', approved: 'green', active: 'green', resolved: 'green', pending: 'amber', created: 'amber',
     open: 'amber', in_progress: 'blue', waiting_customer: 'amber', escalated: 'red', cancelled: 'red', failed: 'red', expired: 'gray', rejected: 'red', refunded: 'blue',
     partially_refunded: 'blue', exhausted: 'gray' }[s] || 'gray')

export function Modal({ open, onClose, title, children, wide, labelledBy }) {
  const ref = useRef(null)
  const titleId = useId()
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return
    const prev = document.activeElement
    const onKey = (e) => {
      if (e.key === 'Escape') onCloseRef.current?.()
      if (e.key === 'Tab' && ref.current) {
        const f = ref.current.querySelectorAll('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])')
        if (!f.length) return
        const first = f[0], last = f[f.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    const timer = setTimeout(() => {
      if (ref.current && !ref.current.contains(document.activeElement)) {
        const target = ref.current.querySelector('[data-autofocus], input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])')
        target?.focus()
      }
    }, 30)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      prev?.focus?.()
    }
  }, [open])
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={labelledBy || titleId}
        className={clsx('relative max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:rounded-2xl', wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')}>
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-5 py-3">
          <h2 id={titleId} className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} aria-label="Close dialog" className="rounded-full p-1.5 hover:bg-gray-100"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

export function EmptyState({ title, text, action, icon: Icon }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white px-6 py-12 text-center">
      {Icon && <Icon className="mb-3 h-10 w-10 text-gray-300" aria-hidden="true" />}
      <h3 className="text-lg font-semibold">{title}</h3>
      {text && <p className="mt-1 max-w-md text-sm text-gray-500">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, retry }) {
  return (
    <div role="alert" className="flex flex-col items-center rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center">
      <AlertTriangle className="mb-2 h-8 w-8 text-red-500" aria-hidden="true" />
      <p className="font-semibold text-red-800">Something went wrong</p>
      <p className="mt-1 text-sm text-red-700">{error?.message || 'Please try again.'}</p>
      {retry && <Button className="mt-4" variant="outline" size="sm" onClick={retry}>Try again</Button>}
    </div>
  )
}

export function Pagination({ page, pages, onChange }) {
  if (!pages || pages <= 1) return null
  const nums = []
  for (let i = Math.max(1, page - 2); i <= Math.min(pages, page + 2); i++) nums.push(i)
  return (
    <nav aria-label="Pagination" className="mt-6 flex items-center justify-center gap-1">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></Button>
      {nums.map((n) => (
        <button key={n} onClick={() => onChange(n)} aria-current={n === page ? 'page' : undefined}
          className={clsx('h-9 min-w-9 rounded-lg px-2 text-sm font-medium', n === page ? 'bg-brand text-white' : 'bg-white ring-1 ring-gray-200 hover:ring-brand')}>
          {n}
        </button>
      ))}
      <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Next page"><ChevronRight className="h-4 w-4" /></Button>
    </nav>
  )
}

export function Tabs({ tabs, value, onChange, label = 'Sections' }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-gray-200 [scrollbar-width:none]">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={clsx('whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-semibold transition',
            value === t.id ? 'border-brand text-brand' : 'border-transparent text-gray-500 hover:text-ink')}>
          {t.label}{t.count != null && <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 text-xs">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

export function Stat({ label, value, sub, tone }) {
  return (
    <div className="card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className={clsx('mt-1 text-2xl font-bold', tone)}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" className="peer sr-only" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="relative h-6 w-11 rounded-full bg-gray-300 transition after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition peer-checked:bg-brand peer-checked:after:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-brand" />
      {label}
    </label>
  )
}

export function Poster({ a = '#1f2937', b = '#e11d48', url, title, className = '', ratio = 'aspect-[2/3]', badge }) {
  return (
    <div className={clsx('relative overflow-hidden rounded-xl', ratio, className)}
      style={{ background: `linear-gradient(155deg, ${a} 0%, ${b} 140%)` }}>
      {url ? <img src={url} alt={title} loading="lazy" className="h-full w-full object-cover" /> : (
        <div className="flex h-full w-full flex-col justify-end p-3 text-white" role="img" aria-label={title}>
          <div className="absolute inset-0 opacity-20" style={{ background: 'radial-gradient(circle at 80% 10%, #fff 0, transparent 45%)' }} />
          <span className="relative line-clamp-3 text-lg font-extrabold leading-tight drop-shadow sm:text-xl">{title}</span>
        </div>
      )}
      {badge && <span className="absolute left-2 top-2 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">{badge}</span>}
    </div>
  )
}

export function Rating({ value, count }) {
  if (!count && !Number(value)) return <span className="text-xs text-gray-500">No ratings yet</span>
  return (
    <span className="inline-flex items-center gap-1 text-sm font-semibold" aria-label={`Rated ${value} out of 10 by ${count} people`}>
      <span className="text-brand" aria-hidden="true">★</span>{Number(value).toFixed(1)}/10
      {count > 0 && <span className="text-xs font-normal text-gray-500">({count})</span>}
    </span>
  )
}

export function Breadcrumb({ items }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-3 text-sm text-gray-500">
      {items.map((it, i) => (
        <span key={i}>{i > 0 && <span className="mx-1.5">/</span>}{it}</span>
      ))}
    </nav>
  )
}

export function Chip({ active, children, ...p }) {
  return (
    <button {...p} aria-pressed={active}
      className={clsx('whitespace-nowrap rounded-full border px-3.5 py-1.5 text-sm font-medium transition',
        active ? 'border-brand bg-brand text-white' : 'border-gray-300 bg-white hover:border-brand hover:text-brand')}>
      {children}
    </button>
  )
}
