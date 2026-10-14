/** Where each role lands after sign-in. Customers use the storefront. */
export const PORTALS = {
  admin: '/admin',
  vendor: '/vendor',
  organizer: '/organizer',
  checkin: '/checkin',
  support: '/helpdesk',
  manager: '/vendor',
}

export const portalFor = (role) => PORTALS[role] || '/'

export const ROLE_LABELS = {
  user: 'Customer', vendor: 'Theater vendor', organizer: 'Event organizer', admin: 'Super admin',
  checkin: 'Check-in staff', support: 'Support agent', manager: 'Theater manager',
}

/** Routes a signed-in staff role may open besides its own portal. */
export const SHARED_PATHS = ['/account', '/bookings', '/terms', '/privacy', '/support', '/faqs']
