import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, Check, Clock, XCircle } from 'lucide-react'
import { api } from '../../lib/api'
import { useAuth, useToast } from '../../context/providers'
import { useTitle } from '../../hooks'
import { Badge, Button, Input, PageSpinner, Textarea } from '../../components/ui'
import { email as vEmail, minLen, password as vPassword, phoneRequired, validate } from '../../lib/validators'

const STEPS = ['Register as a vendor', 'Super admin verifies your business', 'Submit your theater', 'Admin approves the theater', 'Add screens, seat layouts and shows', 'Customers start booking']

/** Theater-vendor onboarding: creates the account if needed, then submits the vendor application. */
export default function BecomeVendor() {
  useTitle('List your theater')
  const { user, register } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const qc = useQueryClient()
  const profile = useQuery({ queryKey: ['vendor-profile', user?.id], enabled: !!user, queryFn: () => api.get('/vendor/profile') })
  const [v, setV] = useState({ name: '', email: '', password: '', business_name: '', contact_phone: '', gst_number: '', pan_number: '', address: '', description: '' })
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => { setV({ ...v, [k]: e.target.value }); setErrs({ ...errs, [k]: '' }) }

  const submit = async (e) => {
    e.preventDefault()
    const rules = { business_name: [minLen(2, 'Business name')], contact_phone: [phoneRequired], pan_number: [(x) => (!x || /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(x) ? '' : 'PAN looks like ABCDE1234F')] }
    if (!user) Object.assign(rules, { name: [minLen(2, 'Your name')], email: [vEmail], password: [vPassword] })
    const er = validate(rules, v)
    setErrs(er)
    if (Object.keys(er).length) return
    setBusy(true)
    try {
      if (!user) await register({ name: v.name.trim(), email: v.email.trim(), password: v.password })
      await api.post('/vendor/register', { business_name: v.business_name.trim(), contact_phone: v.contact_phone, gst_number: v.gst_number || null, pan_number: v.pan_number || null, address: v.address || null, description: v.description || null })
      toast.success('Application submitted. We will verify your business shortly.')
      qc.invalidateQueries({ queryKey: ['vendor-profile'] })
    } catch (err) { setErrs(Object.keys(err.fieldErrors).length ? err.fieldErrors : { form: err.message }) } finally { setBusy(false) }
  }

  const p = profile.data
  return (
    <div className="container-x py-6">
      <div className="rounded-2xl bg-gradient-to-r from-night to-indigo-700 p-8 text-white sm:p-12"><Building2 className="mb-3 h-10 w-10" />
        <h1 className="text-3xl font-extrabold sm:text-4xl">List your theater</h1>
        <p className="mt-2 max-w-2xl text-white/85">Bring your cinemas online: manage screens and seat layouts, schedule shows, set prices, watch occupancy live, and get paid through weekly payouts.</p></div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_22rem]">
        <section className="card p-5">
          {user && profile.isLoading ? <PageSpinner /> : p ? (
            <div><h2 className="text-xl font-bold">Your vendor application</h2>
              <p className="mt-2 flex items-center gap-2"><b>{p.business_name}</b>
                <Badge tone={p.status === 'approved' ? 'green' : p.status === 'pending' ? 'amber' : 'red'}>{p.status}</Badge></p>
              {p.status === 'pending' && <p className="mt-3 flex items-start gap-2 text-sm text-gray-600"><Clock className="mt-0.5 h-4 w-4 shrink-0" />Waiting for the platform admin to verify your business. You'll get a notification when it's reviewed.</p>}
              {p.status === 'rejected' && <p className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700"><XCircle className="mt-0.5 h-4 w-4 shrink-0" />Rejected: {p.rejection_reason}. Contact support to reapply.</p>}
              {p.status === 'suspended' && <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">Suspended: {p.rejection_reason}</p>}
              {(p.status === 'approved' || p.status === 'suspended') && <Link to="/vendor"><Button className="mt-4">Open vendor portal</Button></Link>}
            </div>
          ) : (
            <form onSubmit={submit} noValidate className="space-y-4"><h2 className="text-xl font-bold">Vendor registration</h2>
              {errs.form && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{errs.form}</p>}
              {!user && (
                <fieldset className="space-y-4 rounded-lg bg-gray-50 p-4"><legend className="px-1 text-sm font-semibold">Your account</legend>
                  <div className="grid gap-4 sm:grid-cols-2"><Input label="Full name" value={v.name} onChange={set('name')} error={errs.name} /><Input label="Email" type="email" value={v.email} onChange={set('email')} error={errs.email} /></div>
                  <Input label="Password" type="password" autoComplete="new-password" hint="At least 8 characters with letters and numbers" value={v.password} onChange={set('password')} error={errs.password} />
                  <p className="text-xs text-gray-500">Already have an account? <Link to="/login" state={{ from: '/become-a-vendor' }} className="font-semibold text-brand">Sign in first</Link>.</p></fieldset>)}
              <div className="grid gap-4 sm:grid-cols-2"><Input label="Business / company name" value={v.business_name} onChange={set('business_name')} error={errs.business_name} /><Input label="Contact phone" type="tel" placeholder="+919876543210" value={v.contact_phone} onChange={set('contact_phone')} error={errs.contact_phone} /></div>
              <div className="grid gap-4 sm:grid-cols-2"><Input label="GST number (optional)" value={v.gst_number} onChange={set('gst_number')} error={errs.gst_number} /><Input label="PAN (optional)" placeholder="ABCDE1234F" value={v.pan_number} onChange={(e) => set('pan_number')({ target: { value: e.target.value.toUpperCase() } })} error={errs.pan_number} /></div>
              <Input label="Registered address" value={v.address} onChange={set('address')} />
              <Textarea label="About your theaters" value={v.description} onChange={set('description')} />
              <Button size="lg" loading={busy}>Submit application</Button></form>
          )}
        </section>
        <aside className="card h-fit p-5 text-sm"><h2 className="mb-3 font-bold">How approval works</h2>
          <ol className="space-y-3">{STEPS.map((t, i) => <li key={t} className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-white">{i + 1}</span>{t}</li>)}</ol>
          <p className="mt-4 flex items-start gap-2 text-xs text-gray-500"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0" />Unapproved vendors and theaters are never shown to customers.</p></aside>
      </div>
    </div>
  )
}
