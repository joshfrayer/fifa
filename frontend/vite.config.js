import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  root: resolve(__dirname, 'src'),
  build: {
    manifest: 'manifest.json',
    outDir: resolve(__dirname, '../backend/static/assets'),
    assetsDir: '',
    publicDir: false,
    rollupOptions: {
      input: {
        bracket: resolve(__dirname, 'src/js/bracket_page.js'),
        channel_41_player: resolve(__dirname, 'src/js/channel_41_player_page.js')
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