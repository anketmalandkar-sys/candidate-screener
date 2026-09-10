import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Read the single root .env, so there is no second copy of configuration.
  envDir: '..',
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
  server: {
    port: 5173,
    // Proxying /api makes dev same-origin with the API. That matters: the
    // session cookie is SameSite=Lax, so without the proxy the browser would
    // withhold it on cross-origin XHR and dev would behave unlike production.
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
