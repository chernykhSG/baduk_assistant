import { defineConfig } from 'vitest/config'
import preact from '@preact/preset-vite'
import path from 'node:path'

export default defineConfig({
  plugins: [preact()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}'],
  },
  resolve: {
    alias: {
      '@renderer': path.resolve(__dirname, 'src/renderer/src'),
    },
  },
})
