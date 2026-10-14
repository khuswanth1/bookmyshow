import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './context/providers'
import { PORTALS, SHARED_PATHS, portalFor } from './lib/roles'
import Layout from './components/layout/Layout'
import { PageSpinner } from './components/ui'
import Home from './pages/Home'
import Movies from './pages/Movies'
import MovieDetail from './pages/MovieDetail'
import SeatSelection from './pages/SeatSelection'
import Checkout from './pages/Checkout'
import BookingDetail from './pages/BookingDetail'
import Explore from './pages/Explore'
import EventDetail from './pages/EventDetail'
import { StreamHome, VideoPlayer } from './pages/Stream'
import { ForgotPassword, Login, RequireAuth, Signup } from './pages/Auth'
import Account from './pages/Account'
import { Corporates, Faqs, GiftCards, ListYourShow, NotFound, Offers, SearchPage, StaticDoc, SupportPage } from './pages/Misc'

const Organizer = lazy(() => import('./pages/organizer/Organizer'))
const Vendor = lazy(() => import('./pages/vendor/Vendor'))
const BecomeVendor = lazy(() => import('./pages/vendor/BecomeVendor'))
const Admin = lazy(() => import('./pages/admin/Admin'))
const CheckIn = lazy(() => import('./pages/checkin/CheckIn'))
const Helpdesk = lazy(() => import('./pages/helpdesk/Helpdesk'))

const PUBLIC_PATHS = ['/login', '/signup', '/forgot-password', '/become-a-vendor', '/terms', '/privacy']

/** Nothing but the sign-in page is shown until the visitor is authenticated. */
function Gate({ children }) {
  const { user, loading } = useAuth()
  const { pathname } = useLocation()
  if (loading) return <PageSpinner />
  if (!user && !PUBLIC_PATHS.includes(pathname)) return <Navigate to="/login" state={pathname !== '/' ? { from: pathname } : undefined} replace />
  const portal = PORTALS[user?.role]
  const allowed = [...Object.values(PORTALS), ...SHARED_PATHS]
  if (portal && !allowed.some((p) => pathname === p || pathname.startsWith(p + '/'))) return <Navigate to={portalFor(user.role)} replace />
  return children
}

export default function App() {
  return (
    <Gate><Suspense fallback={<PageSpinner />}>
      <Routes>
        <Route path="login" element={<Login />} />
        <Route path="signup" element={<Signup />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="movies" element={<Movies />} />
          <Route path="movies/:id" element={<MovieDetail />} />
          <Route path="shows/:showId/seats" element={<SeatSelection />} />
          <Route path="checkout/:kind/:id" element={<RequireAuth><Checkout /></RequireAuth>} />
          <Route path="bookings/:id" element={<RequireAuth><BookingDetail /></RequireAuth>} />
          <Route path="events" element={<Explore section="events" />} />
          <Route path="plays" element={<Explore section="plays" />} />
          <Route path="sports" element={<Explore section="sports" />} />
          <Route path="activities" element={<Explore section="activities" />} />
          <Route path="exclusives" element={<Explore exclusive title="BookMyShow Exclusives" />} />
          <Route path="event/:id" element={<EventDetail />} />
          <Route path="stream" element={<StreamHome />} />
          <Route path="stream/:id" element={<VideoPlayer />} />
          <Route path="offers" element={<Offers />} />
          <Route path="corporates" element={<Corporates />} />
          <Route path="gift-cards" element={<GiftCards />} />
          <Route path="list-your-show" element={<ListYourShow />} />
          <Route path="search" element={<SearchPage />} />
          <Route path="account/:tab?" element={<RequireAuth><Account /></RequireAuth>} />
          <Route path="support" element={<SupportPage />} />
          <Route path="faqs" element={<Faqs />} />
          {['about', 'careers', 'press', 'terms', 'privacy'].map((d) => <Route key={d} path={d} element={<StaticDoc doc={d} />} />)}
          <Route path="organizer/*" element={<RequireAuth roles={['organizer', 'admin']}><Organizer /></RequireAuth>} />
          <Route path="vendor/*" element={<RequireAuth roles={['vendor', 'manager', 'admin']}><Vendor /></RequireAuth>} />
          <Route path="become-a-vendor" element={<BecomeVendor />} />
          <Route path="checkin/*" element={<RequireAuth roles={['checkin', 'admin']}><CheckIn /></RequireAuth>} />
          <Route path="helpdesk/*" element={<RequireAuth roles={['support', 'admin']}><Helpdesk /></RequireAuth>} />
          <Route path="admin/*" element={<RequireAuth roles={['admin']}><Admin /></RequireAuth>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense></Gate>
  )
}
