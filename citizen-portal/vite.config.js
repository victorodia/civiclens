import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/public/',
  server: {
    port: 5175,
    strictPort: true,
  },
  plugins: [
    react(),
      ]
})


