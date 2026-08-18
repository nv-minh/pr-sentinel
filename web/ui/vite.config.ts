import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard is served by FastAPI in production; in dev, proxy the API to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // Cap the diff chunk: swap lowlight's `all` grammars for `common`.
      lowlight: path.resolve(__dirname, './src/shims/lowlight-common-only.ts'),
    },
  },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:6789' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
