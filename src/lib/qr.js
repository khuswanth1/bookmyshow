/** Ticket QR payload is `BMS|<booking code>|<secret token>` (see BookingDetail). Returns null for anything else. */
export function parseTicketQr(text) {
  const parts = String(text || '').trim().split('|')
  if (parts.length !== 3 || parts[0] !== 'BMS' || !parts[1] || !parts[2]) return null
  return { code: parts[1], token: parts[2] }
}
