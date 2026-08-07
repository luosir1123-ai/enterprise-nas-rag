import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/internal/',
  plugins: [react()],
  server: {
    port: 4173,
    proxy: {
      '/api': 'http://127.0.0.1',
      '/internal-api': 'http://127.0.0.1',
    },
  },
});
