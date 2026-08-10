import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// ブース来場者の古い端末(iOS 15系Safari/WebKit)でも動くよう、配信コードをES2020相当に下げる。
// static class blocks(ES2022, Safari 16.4+)等が変換対象。
// Vite 8はRolldown/Oxcベースのため esbuildOptions ではなく oxc / rolldownOptions.transform で指定する
const LEGACY_TARGET = 'es2020'

export default defineConfig({
  plugins: [react()],
  oxc: { target: LEGACY_TARGET },
  optimizeDeps: { rolldownOptions: { transform: { target: LEGACY_TARGET } } },
  build: { target: LEGACY_TARGET },
  server: {
    // コントローラ画面(/controller)は同一LANのスマホから開く前提のため、全アドレスで待ち受ける
    host: true,
    proxy: {
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/api': { target: 'http://localhost:8000' },
    },
  },
})
