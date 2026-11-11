import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
const apiTarget = process.env.PAPR_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': apiTarget, '/admin/api': apiTarget } },
})
