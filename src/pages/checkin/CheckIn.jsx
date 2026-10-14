import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, CameraOff, CheckCircle2, Keyboard, ScanLine, ShieldAlert, XCircle } from 'lucide-react'
import jsQR from 'jsqr'
import { api } from '../../lib/api'
import { useTitle } from '../../hooks'
import { Badge, Button, EmptyState, ErrorState, Input, PageSpinner, Stat } from '../../components/ui'
import { DataTable } from '../../components/portal'
import { fmtDateTime, fmtTime } from '../../lib/format'
import { parseTicketQr } from '../../lib/qr'

const TONES = {
  admitted: { box: 'bg-emerald-600 text-white', Icon: CheckCircle2, title: 'ADMIT' },
  duplicate: { box: 'bg-amber-500 text-black', Icon: ShieldAlert, title: 'ALREADY USED' },
  invalid: { box: 'bg-red-600 text-white', Icon: XCircle, title: 'INVALID' },
  wrong_event: { box: 'bg-red-600 text-white', Icon: XCircle, title: 'WRONG EVENT' },
  not_confirmed: { box: 'bg-red-600 text-white', Icon: XCircle, title: 'NOT VALID' },
}
const resultTone = (r) => ({ admitted: 'green', duplicate: 'amber' }[r] || 'red')

function ResultBanner({ r, onDismiss }) {
  if (!r) return <div className="grid min-h-40 place-items-center rounded-2xl border-2 border-dashed border-gray-300 text-sm text-gray-500" role="status">Waiting for the first ticket…</div>
  const t = TONES[r.result]
  return (
    <div role="alert" className={`rounded-2xl p-5 shadow-lg ${t.box}`}>
      <div className="flex items-center gap-3"><t.Icon className="h-10 w-10 shrink-0" aria-hidden="true" /><div className="min-w-0">
        <p className="text-3xl font-black tracking-wide">{t.title}</p><p className="text-base font-semibold">{r.message}</p></div></div>
      {(r.holder_name || r.items?.length > 0) && (
        <div className="mt-3 rounded-xl bg-black/15 p-3 text-sm">
          {r.holder_name && <p><b>{r.holder_name}</b> · {r.booking_code}</p>}
          {r.items?.map((i) => <p key={i}>{i}</p>)}
          {r.result === 'duplicate' && r.checked_in_at && <p className="mt-1 font-semibold">First scanned at {fmtTime(r.checked_in_at)}</p>}
        </div>)}
      <button onClick={onDismiss} className="mt-3 rounded-lg bg-black/20 px-3 py-1.5 text-sm font-semibold hover:bg-black/30">Next ticket</button>
    </div>
  )
}

/** Camera scanner. Decodes frames locally with jsQR; the video never leaves the device. */
function Scanner({ onCode, paused }) {
  const video = useRef(null)
  const canvas = useRef(null)
  const stream = useRef(null)
  const raf = useRef(0)
  const last = useRef({ text: '', at: 0 })
  const [state, setState] = useState('idle') // idle | starting | on | error
  const [err, setErr] = useState('')
  const pausedRef = useRef(paused)
  pausedRef.current = paused
  const cb = useRef(onCode)
  cb.current = onCode

  const stop = useCallback(() => {
    cancelAnimationFrame(raf.current)
    stream.current?.getTracks().forEach((t) => t.stop())
    stream.current = null
    setState('idle')
  }, [])

  const tick = useCallback(() => {
    const v = video.current, c = canvas.current
    if (v && c && v.readyState === v.HAVE_ENOUGH_DATA && !pausedRef.current) {
      const w = 480, h = Math.round((v.videoHeight / v.videoWidth) * w) || 360
      c.width = w; c.height = h
      const ctx = c.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(v, 0, 0, w, h)
      const hit = jsQR(ctx.getImageData(0, 0, w, h).data, w, h, { inversionAttempts: 'dontInvert' })
      // The same code in front of the camera is only reported again after 4s (the server also guards duplicates).
      if (hit?.data && (hit.data !== last.current.text || Date.now() - last.current.at > 4000)) {
        last.current = { text: hit.data, at: Date.now() }
        cb.current(hit.data)
      }
    }
    raf.current = requestAnimationFrame(tick)
  }, [])

  const start = async () => {
    setErr(''); setState('starting')
    if (!navigator.mediaDevices?.getUserMedia) { setErr('This browser cannot open the camera here. Camera access needs HTTPS (or localhost). Use manual entry below.'); setState('error'); return }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      video.current.srcObject = stream.current
      await video.current.play()
      setState('on')
      raf.current = requestAnimationFrame(tick)
    } catch (e) {
      setErr(e?.name === 'NotAllowedError' ? 'Camera permission was denied. Allow it in the browser, or use manual entry below.' : 'Could not start the camera. Use manual entry below.')
      setState('error')
    }
  }
  useEffect(() => stop, [stop])

  return (
    <div>
      <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-black">
        <video ref={video} muted playsInline className="h-full w-full object-cover" aria-label="Camera preview" />
        <canvas ref={canvas} className="hidden" />
        {state === 'on' && <div className="pointer-events-none absolute inset-8 rounded-2xl border-4 border-white/70" aria-hidden="true" />}
        {state !== 'on' && <div className="absolute inset-0 grid place-items-center p-6 text-center text-white">
          <div><ScanLine className="mx-auto mb-2 h-10 w-10 opacity-70" aria-hidden="true" /><p className="text-sm opacity-80">{state === 'starting' ? 'Starting camera…' : 'Camera is off'}</p></div></div>}
      </div>
      {err && <p role="alert" className="mt-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">{err}</p>}
      <div className="mt-3">{state === 'on'
        ? <Button variant="outline" onClick={stop}><CameraOff className="h-4 w-4" />Stop camera</Button>
        : <Button onClick={start} loading={state === 'starting'}><Camera className="h-4 w-4" />Start camera</Button>}</div>
    </div>
  )
}

function Door({ event, onBack }) {
  const qc = useQueryClient()
  const [result, setResult] = useState(null)
  const [code, setCode] = useState('')
  const busy = useRef(false)
  const stats = useQuery({ queryKey: ['checkin-stats', event.id], queryFn: () => api.get(`/checkin/events/${event.id}/stats`), refetchInterval: 5000 })
  const scan = useMutation({
    mutationFn: (b) => api.post('/checkin/scan', { event_id: event.id, ...b }),
    onSuccess: (r) => { setResult(r); navigator.vibrate?.(r.result === 'admitted' ? 80 : [120, 60, 120]); qc.invalidateQueries({ queryKey: ['checkin-stats', event.id] }) },
    onError: (e) => setResult({ result: 'invalid', message: e.message }),
    onSettled: () => { busy.current = false },
  })
  const onCode = useCallback((text) => {
    if (busy.current) return
    busy.current = true
    if (!parseTicketQr(text)) { busy.current = false; setResult({ result: 'invalid', message: 'This is not a BookMyShow ticket QR code.' }); return }
    scan.mutate({ qr: text })
  }, [scan])
  const s = stats.data

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><button onClick={onBack} className="text-sm font-semibold text-brand">← All events</button><h1 className="text-2xl font-bold">{event.title}</h1><p className="text-sm text-gray-500">{fmtDateTime(event.starts_at)} · {event.venue_name}</p></div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Admitted" value={s ? `${s.tickets_admitted} / ${s.tickets_sold}` : '…'} sub="tickets in / sold" />
        <Stat label="Parties arrived" value={s ? `${s.bookings_arrived} / ${s.bookings}` : '…'} />
        <Stat label="Still to arrive" value={s ? s.tickets_sold - s.tickets_admitted : '…'} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="card space-y-4 p-4" aria-label="Scan tickets">
          <Scanner onCode={onCode} paused={scan.isPending || !!result} />
          <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (code.trim()) { setResult(null); scan.mutate({ booking_code: code.trim() }); setCode('') } }}>
            <Input label="Manual entry: booking code" value={code} onChange={(e) => setCode(e.target.value)} className="uppercase" autoComplete="off" autoCapitalize="characters" />
            <Button variant="dark" loading={scan.isPending}><Keyboard className="h-4 w-4" />Check</Button>
          </form>
        </section>
        <section className="space-y-4" aria-live="polite" aria-label="Scan result">
          <ResultBanner r={result} onDismiss={() => setResult(null)} />
          <div><h2 className="mb-2 font-bold">Recent scans</h2>
            {stats.isError ? <ErrorState error={stats.error} retry={stats.refetch} /> : (
              <DataTable caption="Recent scans" rows={s?.recent || []} empty="No scans yet." columns={[
                { header: 'Time', render: (r) => fmtTime(r.at) },
                { header: 'Result', render: (r) => <Badge tone={resultTone(r.result)}>{r.result.replace('_', ' ')}</Badge> },
                { header: 'Guest', render: (r) => r.holder_name ? <>{r.holder_name}<p className="text-xs text-gray-500">{r.booking_code}{r.method === 'manual' ? ' · manual' : ''}</p></> : '—' },
                { header: 'Qty', key: 'tickets' }]} />)}
          </div>
        </section>
      </div>
    </div>
  )
}

export default function CheckIn() {
  useTitle('Check-in')
  const [selected, setSelected] = useState(null)
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ['checkin-events'], queryFn: () => api.get('/checkin/events'), refetchInterval: 30000 })
  if (isLoading) return <div className="container-x py-6"><PageSpinner /></div>
  if (isError) return <div className="container-x py-6"><ErrorState error={error} retry={refetch} /></div>
  const current = data.find((e) => e.id === selected)
  return (
    <div className="container-x py-6">
      {current ? <Door event={current} onBack={() => setSelected(null)} /> : (
        <div className="space-y-4">
          <h1 className="text-2xl font-bold">Today at the door</h1>
          {data.length === 0
            ? <EmptyState title="No events assigned to you" text="The organizer of an event assigns you to it. Ask them to add your account email." icon={ScanLine} />
            : <ul className="grid gap-3 sm:grid-cols-2">{data.map((e) => (
              <li key={e.id} className="card p-4"><b>{e.title}</b><p className="text-sm text-gray-500">{fmtDateTime(e.starts_at)} · {e.venue_name}</p>
                <p className="mt-2 text-sm">{e.tickets_admitted} / {e.tickets_sold} admitted</p>
                <Button className="mt-3" onClick={() => setSelected(e.id)}><ScanLine className="h-4 w-4" />Open scanner</Button></li>))}</ul>}
        </div>)}
    </div>
  )
}
