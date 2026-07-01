import { defineConfig } from 'vite'
import { resolve } from 'path'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  root: resolve(__dirname, 'src'),
  build: {
    manifest: 'manifest.json',
    outDir: resolve(__dirname, '../backend/static/assets'),
    assetsDir: '',
    publicDir: false,
    rollupOptions: {
      input: {
        bracket: resolve(__dirname, 'src/js/bracket_page.jsx'),
        live_tv_player: resolve(__dirname, 'src/js/live_tv_player_page.jsx')
      },
      output: {
        entryFileNames: '[name].[hash].js',
        assetFileNames: '[name].[hash][extname]'
      }
    }
  },
  base: './',
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: resolve(__dirname, 'src/test/setup.js')
  }
})