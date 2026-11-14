// Copies Cesium's runtime assets (workers, widgets CSS, textures) into
// public/cesium so Vite serves them in dev and copies them into dist on build.
// window.CESIUM_BASE_URL (set in index.html) points at this folder.
import { cpSync, existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'node_modules', 'cesium', 'Build', 'Cesium');
const dest = join(root, 'public', 'cesium');
const version = JSON.parse(
  readFileSync(join(root, 'node_modules', 'cesium', 'package.json'), 'utf8'),
).version;
const stamp = join(dest, '.version');

if (existsSync(stamp) && readFileSync(stamp, 'utf8') === version) {
  console.log(`cesium ${version} assets already in public/cesium`);
  process.exit(0);
}
mkdirSync(dest, { recursive: true });
for (const dir of ['Workers', 'ThirdParty', 'Assets', 'Widgets']) {
  cpSync(join(src, dir), join(dest, dir), { recursive: true });
}
writeFileSync(stamp, version);
console.log(`copied cesium ${version} assets to public/cesium`);
