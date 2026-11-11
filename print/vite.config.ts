import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'
export default defineConfig({
  plugins: [vue()],
  build: {
    ssr: fileURLToPath(new URL('./src/document.ts', import.meta.url)),
    outDir: fileURLToPath(new URL('./dist', import.meta.url)),
    emptyOutDir: true,
    cssCodeSplit: false,
    ssrEmitAssets: true,
    rollupOptions: { output: { entryFileNames: 'document.mjs', assetFileNames: '[name][extname]' } },
  },
})
