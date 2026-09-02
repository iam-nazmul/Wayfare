import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // The dev server sits behind compose's nginx, which forwards the original Host. Browsers
    // arrive as `localhost`; anything driving it from inside the network arrives as `nginx`,
    // and Vite's host check rejects an unlisted name with a 403 before React ever loads.
    allowedHosts: ['localhost', 'nginx'],
    // Bind-mounted source in Docker does not emit inotify events on every host.
    watch: { usePolling: true },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
