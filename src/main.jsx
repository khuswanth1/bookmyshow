import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App'
import { AuthProvider, CityProvider, ToastProvider } from './context/providers'

// Catalogue changes (vendor shows, organizer events, admin approvals) must show up on public pages straight away,
// including when the public site is open in another tab, so every successful mutation refreshes the public lists.
const PUBLIC_KEYS = [['movies'], ['movies-all'], ['events'], ['videos'], ['offers']]
const refreshPublic = () => PUBLIC_KEYS.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }))
let channel = null
try {
  channel = new BroadcastChannel('catalogue-changed')
  channel.onmessage = refreshPublic
} catch { /* BroadcastChannel unavailable: window-focus and polling refetch still apply */ }

const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onSuccess: () => { refreshPublic(); try { channel?.postMessage(Date.now()) } catch { /* ignore */ } },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (n, err) => n < 2 && (!err.status || err.status >= 500 || err.status === 0),
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <CityProvider>
              <App />
            </CityProvider>
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
