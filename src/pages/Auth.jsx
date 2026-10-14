import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { loadGoogle, useTitle } from '../hooks'
import { Button, Input } from '../components/ui'
import { portalFor } from '../lib/roles'
import { email as vEmail, minLen, password as vPassword, phone as vPhone, validate } from '../lib/validators'

function GoogleButton({ onCredential }) {
  const { data: cfg } = useQuery({ queryKey: ['config'], queryFn: () => api.get('/auth/config'), staleTime: 3600_000 })
  const ref = useRef(null)
  const cb = useRef(onCredential)
  cb.current = onCredential
  useEffect(() => {
    if (!cfg?.google_client_id || !ref.current) return
    let dead = false
    loadGoogle().then((g) => {
      if (dead) return
      g.accounts.id.initialize({ client_id: cfg.google_client_id, callback: (r) => cb.current(r.credential) })
      g.accounts.id.renderButton(ref.current, { theme: 'outline', size: 'large', width: 320, text: 'continue_with' })
    }).catch(() => {})
    return () => { dead = true }
  }, [cfg])
  if (!cfg?.google_client_id) return null
  return (
    <>
      <div className="my-4 flex items-center gap-3 text-xs text-gray-400"><span className="h-px flex-1 bg-gray-200" />or<span className="h-px flex-1 bg-gray-200" /></div>
      <div ref={ref} className="flex justify-center" />
    </>
  )
}

function AuthShell({ title, sub, children, footer }) {
  return (
    <div className="grid min-h-screen place-items-center bg-gradient-to-br from-mist via-white to-rose-50 px-4 py-10">
      <div className="card w-full max-w-md p-6 sm:p-8">
        <Link to="/login" className="mb-5 flex items-center gap-2 text-lg font-extrabold" aria-label="BookMyShow Clone">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-white">▶</span>book<span className="-ml-1.5 text-brand">my</span><span className="-ml-1.5">show</span></Link>
        <h1 className="text-2xl font-bold">{title}</h1><p className="mb-5 mt-1 text-sm text-gray-500">{sub}</p>
        {children}
        <p className="mt-6 text-center text-sm text-gray-600">{footer}</p>
      </div>
    </div>
  )
}

function useAuthForm(initial, rules, submit) {
  const [v, setV] = useState(initial)
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [formErr, setFormErr] = useState('')
  const set = (k) => (e) => { setV((x) => ({ ...x, [k]: e.target.value })); if (errs[k]) setErrs((x) => ({ ...x, [k]: '' })) }
  const onSubmit = async (e) => {
    e.preventDefault(); setFormErr('')
    const er = validate(rules, v)
    setErrs(er)
    if (Object.keys(er).length) return
    setBusy(true)
    try { await submit(v) } catch (err) {
      if (Object.keys(err.fieldErrors || {}).length) setErrs(err.fieldErrors); else setFormErr(err.message)
    } finally { setBusy(false) }
  }
  const reset = () => { setErrs({}); setFormErr('') }
  return { v, set, errs, busy, formErr, onSubmit, reset }
}

const ROLE_TABS = {
  customer: { label: 'Customer', roles: ['user'], home: '/', sub: 'Welcome back. Book your next show.' },
  owner: { label: 'Owner', roles: ['vendor', 'organizer'], home: null, sub: 'Theater and event owners: manage your venues, shows and earnings.' },
  staff: { label: 'Staff', roles: ['checkin', 'support', 'manager'], home: null, sub: 'Door staff, support agents and theater managers.' },
  admin: { label: 'Admin', roles: ['admin'], home: '/admin', sub: 'Platform administration. Authorised staff only.' },
}
const homeFor = (u) => portalFor(u.role)
const FOOTERS = {
  owner: <>Want to list your theater? <Link to="/become-a-vendor" className="font-semibold text-brand">Register as an owner</Link></>,
  staff: 'Staff accounts are created by the platform admin (door staff, support) or by a theater vendor and approved by the admin (managers).',
  admin: 'Admin accounts are created by the platform team.',
}

export function Login() {
  useTitle('Sign in')
  const { login, google, user, logout } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const toast = useToast()
  const [role, setRole] = useState('customer')
  const tab = ROLE_TABS[role]
  const from = loc.state?.from

  const finish = (u) => {
    if (!tab.roles.includes(u.role)) {
      const right = Object.entries(ROLE_TABS).find(([, t]) => t.roles.includes(u.role))?.[1].label
      logout()
      throw new Error(`This account is ${/^[AEIOU]/.test(right) ? "an" : "a"} ${right} account. Choose the “${right}” button above to sign in.`)
    }
    toast.success('Welcome back!')
    nav(role === 'customer' && from ? from : homeFor(u), { replace: true })
  }
  const f = useAuthForm({ email: '', password: '' }, { email: [vEmail], password: [(x) => (x ? '' : 'Enter your password')] }, async (v) => finish(await login(v.email.trim(), v.password)))
  if (user) return <Navigate to={from || homeFor(user)} replace />
  return (
    <AuthShell title="Sign in" sub={tab.sub} footer={role === 'customer' ? <>New here? <Link to="/signup" className="font-semibold text-brand">Create an account</Link></> : FOOTERS[role]}>
      <div role="tablist" aria-label="Sign in as" className="mb-5 grid grid-cols-4 gap-1 rounded-xl bg-gray-100 p-1">
        {Object.entries(ROLE_TABS).map(([k, t]) => (
          <button key={k} role="tab" type="button" aria-selected={role === k} onClick={() => { setRole(k); f.reset() }}
            className={`rounded-lg px-2 py-2 text-xs font-semibold transition sm:text-sm ${role === k ? 'bg-white text-brand shadow' : 'text-gray-600 hover:text-ink'}`}>{t.label}</button>
        ))}
      </div>
      <form onSubmit={f.onSubmit} noValidate className="space-y-4">
        {f.formErr && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{f.formErr}</p>}
        <Input label="Email" type="email" autoComplete="email" value={f.v.email} onChange={f.set('email')} error={f.errs.email} />
        <Input label="Password" type="password" autoComplete="current-password" value={f.v.password} onChange={f.set('password')} error={f.errs.password} />
        <p className="-mt-2 text-right text-xs"><Link to="/forgot-password" className="font-semibold text-brand">Forgot password?</Link></p>
        <Button className="w-full" size="lg" loading={f.busy}>Sign in as {tab.label}</Button>
      </form>
      {role === 'customer' && <GoogleButton onCredential={async (c) => { try { finish(await google(c)) } catch (e) { toast.error(e.message) } }} />}
    </AuthShell>
  )
}

export function Signup() {
  useTitle('Create account')
  const { register, google, user } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const toast = useToast()
  const to = loc.state?.from || '/'
  const f = useAuthForm({ name: '', email: '', phone: '', password: '' },
    { name: [minLen(2, 'Name')], email: [vEmail], phone: [vPhone], password: [vPassword] },
    async (v) => { await register({ name: v.name.trim(), email: v.email.trim(), phone: v.phone || null, password: v.password }); toast.success('Account created'); nav(to, { replace: true }) })
  if (user) return <Navigate to={to} replace />
  return (
    <AuthShell title="Create your account" sub="Takes less than a minute." footer={<>Already have an account? <Link to="/login" state={loc.state} className="font-semibold text-brand">Sign in</Link></>}>
      <form onSubmit={f.onSubmit} noValidate className="space-y-4">
        {f.formErr && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{f.formErr}</p>}
        <Input label="Full name" autoComplete="name" value={f.v.name} onChange={f.set('name')} error={f.errs.name} />
        <Input label="Email" type="email" autoComplete="email" value={f.v.email} onChange={f.set('email')} error={f.errs.email} />
        <Input label="Mobile number (optional)" type="tel" autoComplete="tel" placeholder="+919876543210" value={f.v.phone} onChange={f.set('phone')} error={f.errs.phone} />
        <Input label="Password" type="password" autoComplete="new-password" hint="At least 8 characters with letters and numbers" value={f.v.password} onChange={f.set('password')} error={f.errs.password} />
        <Button className="w-full" size="lg" loading={f.busy}>Create account</Button>
        <p className="text-center text-xs text-gray-500">By continuing you agree to our <Link to="/terms" className="underline">Terms</Link> and <Link to="/privacy" className="underline">Privacy Policy</Link>.</p>
      </form>
      <GoogleButton onCredential={async (c) => { try { await google(c); nav(to, { replace: true }) } catch (e) { toast.error(e.message) } }} />
    </AuthShell>
  )
}

export function ForgotPassword() {
  useTitle('Reset password')
  const nav = useNavigate()
  const toast = useToast()
  const [step, setStep] = useState('email')
  const [email, setEmail] = useState('')
  const [hint, setHint] = useState('')
  const f = useAuthForm({ code: '', new_password: '' },
    { code: [(x) => (/^\d{6}$/.test(x || '') ? '' : 'Enter the 6-digit code')], new_password: [vPassword] },
    async (v) => { await api.post('/auth/password/reset', { email: email.trim(), code: v.code, new_password: v.new_password }); toast.success('Password updated. Sign in with it now.'); nav('/login', { replace: true }) })
  const g = useAuthForm({ email: '' }, { email: [vEmail] }, async (v) => {
    const r = await api.post('/auth/password/forgot', { email: v.email.trim() })
    setEmail(v.email); setHint(r.dev_code ? `Development mode: your code is ${r.dev_code}` : r.message); setStep('code')
  })
  return (
    <AuthShell title="Reset your password" sub={step === 'email' ? 'Enter your account email and we will send you a 6-digit code.' : 'Enter the code from your email and choose a new password.'}
      footer={<Link to="/login" className="font-semibold text-brand">Back to sign in</Link>}>
      {step === 'email' ? (
        <form onSubmit={g.onSubmit} noValidate className="space-y-4">
          {g.formErr && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{g.formErr}</p>}
          <Input label="Email" type="email" autoComplete="email" value={g.v.email} onChange={g.set('email')} error={g.errs.email} />
          <Button className="w-full" size="lg" loading={g.busy}>Send code</Button>
        </form>
      ) : (
        <form onSubmit={f.onSubmit} noValidate className="space-y-4">
          {hint && <p role="status" className="rounded-lg bg-blue-50 p-3 text-sm text-blue-800">{hint}</p>}
          {f.formErr && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{f.formErr}</p>}
          <Input label="6-digit code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={f.v.code} onChange={f.set('code')} error={f.errs.code} />
          <Input label="New password" type="password" autoComplete="new-password" hint="At least 8 characters with letters and numbers" value={f.v.new_password} onChange={f.set('new_password')} error={f.errs.new_password} />
          <Button className="w-full" size="lg" loading={f.busy}>Update password</Button>
          <button type="button" onClick={() => setStep('email')} className="w-full text-center text-sm text-gray-500 underline">Use a different email</button>
        </form>
      )}
    </AuthShell>
  )
}

export function RequireAuth({ children, roles }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div className="grid min-h-[50vh] place-items-center text-gray-500">Loading…</div>
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />
  return children
}
