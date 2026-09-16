import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  envDir: '..',
  plugins: [vue()],
  server: { port: 5177, proxy: { '/api': 'http://127.0.0.1:8007' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8007' } },
})
