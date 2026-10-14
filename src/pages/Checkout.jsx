import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Gift, Heart, Lock, Tag, X } from 'lucide-react'
import { api, uuid } from '../lib/api'
import { useAuth, useToast } from '../context/providers'
import { loadRazorpay, useCountdown, useTitle } from '../hooks'
import { Button, ErrorState, Input, PageSpinner } from '../components/ui'
import { fmtDateTime, inr, secondsToClock } from '../lib/format'

export function PriceBreakdown({ b }) {
  const rows = [
    ['Tickets', b.subtotal_paise], b.discount_paise ? ['Coupon discount', -b.discount_paise] : null,
    ['Convenience fee', b.fee_paise], ['GST on fee', b.tax_paise], b.donation_paise ? ['Donation', b.donation_paise] : null,
  ].filter(Boolean)
  return (
    <dl className="space-y-1.5 text-sm">
      {rows.map(([k, v]) => <div key={k} className="flex justify-between"><dt className="text-gray-600">{k}</dt><dd className={v < 0 ? 'font-medium text-emerald-600' : ''}>{v < 0 ? '−' : ''}{inr(Math.abs(v))}</dd></div>)}
      <div className="flex justify-between border-t pt-2 font-semibold"><dt>Order total</dt><dd>{inr(b.total_paise)}</dd></div>
      {b.gift_card_paise > 0 && <div className="flex justify-between text-emerald-600"><dt>Gift card</dt><dd>−{inr(b.gift_card_paise)}</dd></div>}
      <div className="flex justify-between text-base font-bold"><dt>Amount payable</dt><dd>{inr(b.payable_paise)}</dd></div>
    </dl>
  )
}

export default function Checkout() {
  const { kind, id } = useParams()
  const loc = useLocation()
  const { user } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const qc = useQueryClient()
  const cfg = useQuery({ queryKey: ['config'], queryFn: () => api.get('/auth/config'), staleTime: 3600_000 })
  const initiatives = useQuery({ queryKey: ['initiatives'], queryFn: () => api.get('/initiatives') })
  const offers = useQuery({ queryKey: ['offers'], queryFn: () => api.get('/offers') })

  const isMovie = kind === 'movie'
  const picked = loc.state?.tickets // event: [{ticket_type_id, quantity}]
  const show = useQuery({ queryKey: ['show', id, user?.id], enabled: isMovie && !!user, queryFn: () => api.get(`/shows/${id}`), staleTime: 0 })
  const event = useQuery({ queryKey: ['event', id], enabled: !isMovie, queryFn: () => api.get(`/events/${id}`) })

  const [code, setCode] = useState('')
  const [coupon, setCoupon] = useState(null) // {code,title,discount_paise}
  const [couponErr, setCouponErr] = useState('')
  const [giftCode, setGiftCode] = useState('')
  const [gift, setGift] = useState(null) // {code,balance_paise}
  const [giftErr, setGiftErr] = useState('')
  const [initiative, setInitiative] = useState(null)
  const [busy, setBusy] = useState(false)
  const [booking, setBooking] = useState(null) // created pending booking
  const key = useRef(uuid())
  const bookingRef = useRef(null)
  bookingRef.current = booking

  const lines = useMemo(() => {
    if (isMovie) return (show.data?.seats || []).filter((s) => s.mine).map((s) => ({ label: `${s.row}${s.number} · ${s.category}`, qty: 1, unit: s.price_paise }))
    if (!event.data || !picked) return []
    return picked.map((p) => { const t = event.data.ticket_types.find((x) => x.id === p.ticket_type_id); return t && { label: t.name, qty: p.quantity, unit: t.price_paise } }).filter(Boolean)
  }, [isMovie, show.data, event.data, picked])
  const subtotal = lines.reduce((a, l) => a + l.qty * l.unit, 0)

  // preview math mirrors the server; the server remains the source of truth
  const discount = coupon ? Math.min(coupon.discount_paise, subtotal) : 0
  const fee = Math.round(((subtotal - discount) * (cfg.data?.convenience_fee_pct ?? 3)) / 100)
  const tax = Math.round((fee * (cfg.data?.gst_pct ?? 18)) / 100)
  const donation = initiative ? initiative.amount_paise : 0
  const total = subtotal - discount + fee + tax + donation
  const giftApplied = gift ? Math.min(gift.balance_paise, total) : 0
  const preview = { subtotal_paise: subtotal, discount_paise: discount, fee_paise: fee, tax_paise: tax, donation_paise: donation, total_paise: total, gift_card_paise: giftApplied, payable_paise: total - giftApplied }

  const title = isMovie ? show.data?.movie.title : event.data?.title
  useTitle(title ? `Checkout: ${title}` : 'Checkout')
  const left = useCountdown(booking?.expires_at, () => { toast.error('Payment window expired. Please try again.'); setBooking(null); key.current = uuid() })

  // any change to price inputs invalidates the pending booking & its hold
  const abandon = async () => {
    const b = bookingRef.current
    if (b) { setBooking(null); key.current = uuid(); try { await api.post(`/bookings/${b.id}/abandon`) } catch { /* expires on its own */ } }
  }
  const changed = (fn) => (...a) => { abandon(); fn(...a) }

  const applyCoupon = async (c = code) => {
    setCouponErr('')
    if (!c.trim()) return setCouponErr('Enter a coupon code')
    try { setCoupon(await api.post('/coupons/validate', { code: c.trim(), kind, subtotal_paise: subtotal })); abandon(); setCode(c) } catch (e) { setCouponErr(e.message); setCoupon(null) }
  }
  const applyGift = async () => {
    setGiftErr('')
    if (!giftCode.trim()) return setGiftErr('Enter a gift card code')
    try {
      const g = await api.get(`/gift-cards/check/${giftCode.trim().toUpperCase()}`)
      if (g.status !== 'active' || g.balance_paise <= 0) return setGiftErr('This gift card has no usable balance')
      setGift(g); abandon()
    } catch (e) { setGiftErr(e.message); setGift(null) }
  }

  useEffect(() => () => { // leaving the page releases an unpaid hold
    const b = bookingRef.current
    if (b && b.status === 'pending' && !window.__bmsPaying) api.post(`/bookings/${b.id}/abandon`).catch(() => {})
  }, [])

  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />
  if (isMovie ? show.isLoading : event.isLoading) return <PageSpinner />
  if (isMovie ? show.isError : event.isError) return <div className="container-x py-10"><ErrorState error={isMovie ? show.error : event.error} /></div>
  if (!isMovie && !picked) return <Navigate to={`/event/${id}`} replace />
  if (!lines.length) return <div className="container-x py-10"><ErrorState error={{ message: 'No seats are held for you. Please select seats again.' }} retry={() => nav(`/shows/${id}/seats`)} /></div>

  const finish = (b) => { window.__bmsPaying = false; qc.invalidateQueries({ queryKey: ['bookings'] }); qc.invalidateQueries({ queryKey: ['show'] }); nav(`/bookings/${b.id}`, { replace: true, state: { justBooked: true } }) }

  const verify = async (res, tries = 0) => {
    try {
      const v = await api.post('/payments/verify', res)
      toast.success('Payment successful!')
      finish(v.booking)
    } catch (e) {
      if (e.code === 'booking_failed_refunded') { window.__bmsPaying = false; toast.error(e.message); return nav('/account/bookings') }
      if ((e.status === 0 || e.status >= 500) && tries < 3) return setTimeout(() => verify(res, tries + 1), 1500 * (tries + 1))
      window.__bmsPaying = false
      toast.error(`${e.message} If money was debited it will be refunded automatically.`)
    } finally { setBusy(false) }
  }

  const pay = async () => {
    setBusy(true)
    try {
      const body = isMovie
        ? { kind: 'movie', show_id: Number(id), seat_ids: (show.data.seats).filter((s) => s.mine).map((s) => s.id) }
        : { kind: 'event', event_id: Number(id), tickets: picked }
      const out = await api.post('/bookings', { ...body, idempotency_key: key.current, coupon_code: coupon?.code, gift_card_code: gift?.code, initiative_id: initiative?.id })
      setBooking(out.booking)
      if (!out.razorpay) return finish(out.booking) // fully covered by gift card / coupon
      const Razorpay = await loadRazorpay()
      window.__bmsPaying = true
      const rz = new Razorpay({
        key: out.razorpay.key_id, amount: out.razorpay.amount, currency: out.razorpay.currency, order_id: out.razorpay.order_id,
        name: 'BookMyShow Clone', description: `${title} · ${out.booking.code}`, image: '/favicon.svg',
        prefill: { name: user.name, email: user.email, contact: user.phone || '' }, theme: { color: '#f84464' },
        notes: { booking: out.booking.code },
        handler: (res) => verify(res),
        modal: { ondismiss: () => { window.__bmsPaying = false; setBusy(false); toast.info('Payment cancelled. Your seats stay held until the timer ends.') } },
      })
      rz.on('payment.failed', (r) => toast.error(r.error?.description || 'Payment failed. You can retry.'))
      rz.open()
    } catch (e) {
      setBusy(false)
      if (e.code === 'seat_unavailable' || e.code === 'sold_out') { toast.error(e.message); if (isMovie) nav(`/shows/${id}/seats`) }
      else toast.error(e.message)
    }
  }

  return (
    <div className="container-x py-6">
      <h1 className="mb-4 text-2xl font-bold">Review & pay</h1>
      <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
        <div className="space-y-4">
          <section className="card p-5" aria-labelledby="sum-h">
            <h2 id="sum-h" className="text-lg font-bold">{title}</h2>
            <p className="text-sm text-gray-600">{isMovie ? `${show.data.venue.name} · ${show.data.screen_name} · ${fmtDateTime(show.data.starts_at)} · ${show.data.language}` : `${event.data.venue_name}, ${event.data.city.name} · ${fmtDateTime(event.data.starts_at)}`}</p>
            <ul className="mt-3 divide-y text-sm">
              {lines.map((l, i) => <li key={i} className="flex justify-between py-2"><span>{l.label}{l.qty > 1 && ` × ${l.qty}`}</span><span>{inr(l.unit * l.qty)}</span></li>)}
            </ul>
          </section>

          <section className="card p-5" aria-labelledby="cp-h">
            <h2 id="cp-h" className="mb-3 flex items-center gap-2 text-lg font-bold"><Tag className="h-5 w-5 text-brand" />Offers & coupons</h2>
            {coupon ? (
              <div className="flex items-center justify-between rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
                <span><Check className="mr-1 inline h-4 w-4" /><b>{coupon.code}</b> applied: you save {inr(coupon.discount_paise)}</span>
                <button onClick={() => { setCoupon(null); setCode(''); abandon() }} aria-label="Remove coupon"><X className="h-4 w-4" /></button>
              </div>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); applyCoupon() }} className="flex items-start gap-2">
                <Input aria-label="Coupon code" placeholder="Enter coupon code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} error={couponErr} className="flex-1" />
                <Button variant="dark" type="submit">Apply</Button>
              </form>
            )}
            {!coupon && (offers.data || []).filter((o) => o.applies_to === 'all' || o.applies_to === kind).length > 0 && (
              <ul className="mt-3 space-y-2">
                {offers.data.filter((o) => o.applies_to === 'all' || o.applies_to === kind).slice(0, 4).map((o) => (
                  <li key={o.id} className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-gray-300 p-2.5 text-sm">
                    <span><b className="font-mono">{o.code}</b><span className="ml-2 text-gray-600">{o.title}</span></span>
                    <Button size="sm" variant="outline" onClick={() => applyCoupon(o.code)}>Apply</Button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card p-5" aria-labelledby="gc-h">
            <h2 id="gc-h" className="mb-3 flex items-center gap-2 text-lg font-bold"><Gift className="h-5 w-5 text-brand" />Gift card</h2>
            {gift ? (
              <div className="flex items-center justify-between rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
                <span><b>{gift.code}</b>: balance {inr(gift.balance_paise)}, applying {inr(giftApplied)}</span>
                <button onClick={() => { setGift(null); setGiftCode(''); abandon() }} aria-label="Remove gift card"><X className="h-4 w-4" /></button>
              </div>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); applyGift() }} className="flex items-start gap-2">
                <Input aria-label="Gift card code" placeholder="Gift card code" value={giftCode} onChange={(e) => setGiftCode(e.target.value.toUpperCase())} error={giftErr} className="flex-1" />
                <Button variant="dark" type="submit">Apply</Button>
              </form>
            )}
          </section>

          {(initiatives.data || []).length > 0 && (
            <section className="card p-5" aria-labelledby="ini-h">
              <h2 id="ini-h" className="mb-3 flex items-center gap-2 text-lg font-bold"><Heart className="h-5 w-5 text-brand" />Make a difference</h2>
              <div className="space-y-2">
                {initiatives.data.map((i) => (
                  <label key={i.id} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm has-[:checked]:border-brand has-[:checked]:bg-brand/5">
                    <input type="checkbox" className="mt-1 accent-[#f84464]" checked={initiative?.id === i.id} onChange={(e) => { abandon(); setInitiative(e.target.checked ? i : null) }} />
                    <span><b>{i.title}</b> <span className="text-brand">+{inr(i.amount_paise)}</span><span className="block text-xs text-gray-500">{i.description} {i.partner_name && `(${i.partner_name})`}</span></span>
                  </label>
                ))}
              </div>
            </section>
          )}
        </div>

        <aside className="card h-fit p-5 lg:sticky lg:top-28" aria-labelledby="pay-h">
          <h2 id="pay-h" className="mb-3 text-lg font-bold">Payment summary</h2>
          <PriceBreakdown b={booking || preview} />
          {booking && left > 0 && <p className="mt-3 rounded-lg bg-amber-50 p-2 text-center text-xs font-semibold text-amber-800" role="timer">Complete payment within {secondsToClock(left)}</p>}
          <Button size="lg" className="mt-4 w-full" loading={busy} onClick={pay}>
            <Lock className="h-4 w-4" />{preview.payable_paise === 0 ? 'Confirm booking' : booking ? `Pay ${inr(booking.payable_paise)}` : `Pay ${inr(preview.payable_paise)}`}
          </Button>
          <p className="mt-3 text-center text-xs text-gray-500">Secured by Razorpay (test mode). Use test card 4111 1111 1111 1111, any future expiry, any CVV; or UPI <b>success@razorpay</b>.</p>
        </aside>
      </div>
    </div>
  )
}
