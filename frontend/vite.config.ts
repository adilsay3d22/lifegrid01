import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

declare const process: { env: Record<string, string | undefined> } // Node global; avoids adding @types/node for one line

export default defineConfig({
  // Same origin for SPA and API in dev too, so the SameSite=Strict refresh cookie works (SEC-12).
  server: { proxy: { '/api': process.env.API_PROXY ?? 'http://localhost:8000' } },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'LifeGrid',
        short_name: 'LifeGrid',
        start_url: '/app',
        scope: '/app',
        display: 'standalone',
        background_color: '#fafafa',
        theme_color: '#8f1d2c',
        icons: [{ src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
    }),
  ],
})
