import { defineConfig } from 'electron-vite'
import preact from '@preact/preset-vite'

export default defineConfig({
  main: {},
  preload: {},
  renderer: {
    plugins: [preact()]
  }
})
