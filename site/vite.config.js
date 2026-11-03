import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import publicDataCompression from './scripts/public-data-compression.js';
import inlineEntryCss from './scripts/inline-entry-css.js';
export default defineConfig({
  base: process.env.ATLAS_BASE || '/agent-memory/', plugins: [react(), publicDataCompression(), inlineEntryCss()],
  server: { host: 'localhost', proxy: {'/agent-memory/api': {target: 'http://localhost:18086', changeOrigin: true, rewrite: path => path.replace(/^\/agent-memory\/api/, '')}}},
  preview: {host: 'localhost'}, build: {sourcemap: false},
});
