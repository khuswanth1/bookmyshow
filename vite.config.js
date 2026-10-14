import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API = process.env.VITE_PROXY_TARGET || 'http://localhost:8080'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true, // Google OAuth only allows the 5173 origin; fail instead of silently moving to 5174
    proxy: {
      '/api': { target: API, changeOrigin: true, ws: true },
    },
  },
  test: { environment: 'node' },
})
