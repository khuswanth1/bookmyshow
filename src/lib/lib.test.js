import { describe, expect, it } from 'vitest'
import { clsx, duration, inr, secondsToClock, ymd } from './format'
import { parseTicketQr } from './qr'
import { portalFor } from './roles'
import { email, password, phone, validate } from './validators'

describe('format', () => {
  it('formats paise as rupees and drops .00', () => {
    expect(inr(35000)).toBe('₹350')
    expect(inr(72478)).toBe('₹724.78')
    expect(inr(0)).toBe('₹0')
    expect(inr(1234500)).toBe('₹12,345')
  })
  it('formats durations and clocks', () => {
    expect(duration(138)).toBe('2h 18m')
    expect(duration(120)).toBe('2h')
    expect(duration(45)).toBe('45m')
    expect(secondsToClock(65)).toBe('1:05')
  })
  it('uses local calendar date for ymd', () => {
    expect(ymd(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05')
  })
  it('joins truthy class names', () => {
    expect(clsx('a', false, null, 'b')).toBe('a b')
  })
})

describe('validators', () => {
  it('validates emails', () => {
    expect(email('a@b.co')).toBe('')
    expect(email('nope')).not.toBe('')
    expect(email('a@b')).not.toBe('')
  })
  it('requires letters and numbers in passwords', () => {
    expect(password('abcdefg1')).toBe('')
    expect(password('abcdefgh')).not.toBe('')
    expect(password('12345678')).not.toBe('')
    expect(password('a1')).not.toBe('')
  })
  it('validates optional phone numbers', () => {
    expect(phone('')).toBe('')
    expect(phone('+919876543210')).toBe('')
    expect(phone('12ab')).not.toBe('')
  })
  it('reports the first failing rule per field', () => {
    const errs = validate({ email: [email], password: [password] }, { email: 'x', password: 'abcdefg1' })
    expect(Object.keys(errs)).toEqual(['email'])
  })
})


describe('ticket QR + role routing', () => {
  it('parses a valid ticket payload', () => {
    expect(parseTicketQr('BMS|ABC123|tok_en-1')).toEqual({ code: 'ABC123', token: 'tok_en-1' })
    expect(parseTicketQr('  BMS|ABC123|tok  ')).toEqual({ code: 'ABC123', token: 'tok' })
  })
  it.each(['', null, 'hello', 'BMS|only-two', 'XYZ|a|b', 'BMS||tok', 'BMS|code|', 'BMS|a|b|c'])('rejects %j', (v) => {
    expect(parseTicketQr(v)).toBeNull()
  })
  it('sends every role to its own portal', () => {
    expect(portalFor('checkin')).toBe('/checkin')
    expect(portalFor('support')).toBe('/helpdesk')
    expect(portalFor('admin')).toBe('/admin')
    expect(portalFor('user')).toBe('/')
    expect(portalFor(undefined)).toBe('/')
  })
})
