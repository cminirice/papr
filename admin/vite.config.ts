import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
const apiTarget = process.env.PAPR_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
export default defineConfig({
  plugins: [vue()],
  build: { rollupOptions: { input: { main: fileURLToPath(new URL('./index.html', import.meta.url)), feed: fileURLToPath(new URL('./template-feed.html', import.meta.url)) } } },
  server: { proxy: { '/api': apiTarget, '/admin/api': apiTarget } },
})
