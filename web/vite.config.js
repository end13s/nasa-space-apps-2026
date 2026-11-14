import { defineConfig } from 'vite';

// base './' so the build works under GitHub Pages' /<repo>/ path without
// knowing the repo name. Cesium's static assets are copied into
// public/cesium by scripts/copy-cesium.mjs (predev / prebuild).
export default defineConfig({
  base: './',
  worker: { format: 'es' },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 6000,
  },
});
