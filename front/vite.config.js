import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev: vite on 5180 proxies the API/websockets to the backend; build: served by the backend under /media/dist/
const BACK = process.env.BACK_URL || 'http://127.0.0.1:8470'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/media/dist/' : '/',
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': { target: BACK, ws: true, changeOrigin: true },
      '/media': { target: BACK, changeOrigin: true },
    },
  },
}))
