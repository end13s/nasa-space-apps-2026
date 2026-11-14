import { defineConfig } from 'vite';

// base './' so the build works under GitHub Pages' /<repo>/ path without
// knowing the repo name. Cesium's static assets are copied into
// public/cesium by scripts/copy-cesium.mjs (predev / prebuild).
export default defineConfig({
  base: './',
  worker: { format: 'es' },
  // main.js imports construction/regolith_constants.json from outside web/
  // (Julia's file, one source of truth), so the dev server must allow ../.
  server: { fs: { allow: ['..'] } },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 6000,
  },
});
