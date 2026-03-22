import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': 'http://localhost:8000',
      '/campaigns': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/embed': 'http://localhost:8000',
      '/webhooks': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
