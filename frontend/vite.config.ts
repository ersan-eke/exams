import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  server: {
    // the Cloudflare tunnel used for Slack sends its own Host; Vite answers 403 to unknown hosts before proxying
    allowedHosts: ['.trycloudflare.com'],
    // keep the browser's Host: the backend builds OAuth callback URLs from it and checks Origin against it
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
      '/mcp': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
})
