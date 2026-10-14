import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { QRCodeSVG } from 'qrcode.react'
import { CalendarCheck, CheckCircle2, Mail, Printer, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import { useToast } from '../context/providers'
import { useTitle } from '../hooks'
import { Badge, Button, ErrorState, Modal, PageSpinner, Poster, statusTone } from '../components/ui'
import { PriceBreakdown } from './Checkout'
import { fmtDateTime, inr } from '../lib/format'

export default function BookingDetail() {
  const { id } = useParams()
  const loc = useLocation()
  const toast = useToast()
  const qc = useQueryClient()
  const [confirm, setConfirm] = useState(false)
  const { data: b, isLoading, isError, error, refetch } = useQuery({ queryKey: ['booking', id], queryFn: () => api.get(`/bookings/${id}`) })
  useTitle(b ? `Ticket ${b.code}` : 'Ticket')
  const cancel = useMutation({
    mutationFn: () => api.post(`/bookings/${id}/cancel`),
    onSuccess: (r) => { toast.success(`Cancelled. ${inr(r.refund_paise)} will be refunded.`); setConfirm(false); qc.invalidateQueries({ queryKey: ['booking', id] }); qc.invalidateQueries({ queryKey: ['bookings'] }) },
    onError: (e) => { toast.error(e.message); setConfirm(false) },
  })
  const calRetry = useMutation({ mutationFn: () => api.post(`/bookings/${id}/calendar`), onSuccess: (r) => { toast[r.status === 'synced' ? 'success' : 'error'](r.status === 'synced' ? 'Added to Google Calendar' : 'Still could not reach Google Calendar'); qc.invalidateQueries({ queryKey: ['booking'] }) }, onError: (e) => toast.error(e.message) })
  const resend = useMutation({ mutationFn: () => api.post(`/bookings/${id}/resend`), onSuccess: (r) => toast.success(r.message), onError: (e) => toast.error(e.message) })

  if (isLoading) return <PageSpinner />
  if (isError) return <div className="container-x py-10"><ErrorState error={error} retry={refetch} /></div>
  const ok = b.status === 'confirmed'
  return (
    <div className="container-x max-w-3xl py-8">
      {loc.state?.justBooked && ok && (
        <div role="status" className="mb-5 flex items-center gap-3 rounded-xl bg-emerald-50 p-4 text-emerald-800"><CheckCircle2 className="h-6 w-6" /><div><b>Booking confirmed!</b><p className="text-sm">Show the QR code below at the entrance. We've also added it to your bookings.</p></div></div>
      )}
      {!ok && <div role="status" className="mb-5 flex items-center gap-3 rounded-xl bg-gray-100 p-4"><XCircle className="h-6 w-6 text-gray-500" /><span>This booking is <b>{b.status}</b>{b.status === 'cancelled' && b.refund_paise > 0 && <>. Refund of {inr(b.refund_paise)} initiated.</>}</span></div>}

      <article className="card overflow-hidden print:shadow-none" aria-label="Ticket">
        <div className="flex flex-col sm:flex-row">
          <div className="flex-1 p-5">
            <div className="flex gap-4">
              <Poster a={b.poster.a} b={b.poster.b} url={b.poster.url} title={b.title} className="w-24 shrink-0" />
              <div>
                <Badge tone={statusTone(b.status)}>{b.status}</Badge>
                <h1 className="mt-1 text-xl font-bold">{b.title}</h1>
                <p className="text-sm text-gray-600">{b.subtitle}</p>
                <p className="mt-2 text-sm font-semibold">{fmtDateTime(b.starts_at)}</p>
                <p className="text-sm text-gray-600">{b.venue}</p>
              </div>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs uppercase text-gray-500">Booking ID</dt><dd className="font-mono font-bold">{b.code}</dd></div>
              <div><dt className="text-xs uppercase text-gray-500">{b.kind === 'movie' ? 'Seats' : 'Tickets'}</dt><dd className="font-semibold">{b.items.map((i) => (i.quantity > 1 ? `${i.label} × ${i.quantity}` : i.label)).join(', ')}</dd></div>
            </dl>
          </div>
          {ok && b.qr_token && (
            <div className="flex flex-col items-center justify-center gap-2 border-t border-dashed bg-gray-50 p-6 sm:w-56 sm:border-l sm:border-t-0">
              <QRCodeSVG value={`BMS|${b.code}|${b.qr_token}`} size={160} level="M" role="img" aria-label={`QR code for booking ${b.code}`} />
              <p className="text-xs text-gray-500">Scan at the entrance</p>
            </div>
          )}
        </div>
        <div className="border-t p-5"><PriceBreakdown b={b} /></div>
      </article>

      <div className="mt-5 flex flex-wrap gap-3 print:hidden">
        <Button variant="outline" onClick={() => window.print()}><Printer className="h-4 w-4" />Print ticket</Button>
        {ok && <Button variant="outline" onClick={() => resend.mutate()} loading={resend.isPending}><Mail className="h-4 w-4" />Resend confirmation</Button>}
        {ok && b.can_cancel && <Button variant="danger" onClick={() => setConfirm(true)}>Cancel booking</Button>}
        <Link to="/account/bookings"><Button variant="ghost">All bookings</Button></Link>
      </div>
      {ok && b.calendar_status === 'synced' && <p role="status" className="mt-3 flex items-center gap-2 text-sm text-emerald-700"><CalendarCheck className="h-4 w-4" aria-hidden="true" />Added to your Google Calendar.</p>}
      {ok && b.calendar_status === 'failed' && (
        <p role="status" className="mt-3 flex flex-wrap items-center gap-2 text-sm text-amber-800">We couldn't add this booking to your Google Calendar.
          <Button size="sm" variant="outline" loading={calRetry.isPending} onClick={() => calRetry.mutate()}>Try again</Button></p>)}
      {ok && !b.can_cancel && <p className="mt-3 text-xs text-gray-500">Cancellation is closed for this booking.</p>}

      <Modal open={confirm} onClose={() => setConfirm(false)} title="Cancel this booking?">
        <p className="text-sm text-gray-600">You'll get back the ticket value (after any discount). The convenience fee, taxes and donation are non-refundable. Refunds reach your original payment method in 5–7 working days.</p>
        <div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirm(false)}>Keep booking</Button><Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>Yes, cancel</Button></div>
      </Modal>
    </div>
  )
}
