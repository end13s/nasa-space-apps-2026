/**
 * Earth heatmap painter (task F6).
 *
 * One 1440 x 720 canvas, one pixel per 0.25 degree cell, row 0 = 90N,
 * col 0 = -180. Cell id === pixel index, because id = row * ncols + col.
 *
 * How it reaches the globe: a tiny imagery provider whose single level-0 tile
 * covers the whole globe and *is* the canvas. Cesium uploads the canvas
 * straight to a texture, so there is no PNG encode/decode and no network.
 * Geographic tiling means Cesium skips its reprojection pass too.
 *
 * Swapping without flicker: every update() adds a new layer at alpha 0 just
 * above the visible one. Cesium loads imagery for alpha-0 layers but does not
 * draw them. Once every rendered tile has the new texture, a postRender hook
 * sets the new layer's alpha and removes the old layer in the same frame, so
 * the next frame shows exactly one heatmap: no gap, no double draw.
 */
import * as Cesium from 'cesium';

/** Scores below this are transparent. The colormap spans [MIN_SCORE, 1]. */
export const MIN_SCORE = 0.2;

// Alpha ramp: dim at MIN_SCORE, near-opaque at 1 so the best matches pop.
const ALPHA_LO = 140;
const ALPHA_HI = 235;
const ALPHA_GAMMA = 1.3;

// If the readiness check cannot confirm the new layer, swap anyway after this.
const SWAP_TIMEOUT_MS = 2500;
const FALLBACK_SWAP_MS = 400;

// matplotlib viridis at t = 0, 0.1, ..., 1 (exact matplotlib values).
const VIRIDIS_STOPS = [
  [68, 1, 84],
  [72, 37, 118],
  [65, 68, 135],
  [53, 96, 141],
  [42, 120, 142],
  [33, 144, 140],
  [34, 168, 132],
  [67, 191, 113],
  [122, 209, 81],
  [187, 223, 39],
  [253, 231, 37],
];

function viridis(t) {
  const x = Math.min(1, Math.max(0, t)) * (VIRIDIS_STOPS.length - 1);
  const i = Math.min(VIRIDIS_STOPS.length - 2, Math.floor(x));
  const f = x - i;
  const a = VIRIDIS_STOPS[i];
  const b = VIRIDIS_STOPS[i + 1];
  return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
}

/**
 * 256-entry viridis LUT, RGBA (alpha 255). COLORMAP[4k..4k+3] = viridis(k/255).
 * Palette position t maps to score MIN_SCORE + t * (1 - MIN_SCORE).
 */
export const COLORMAP = (() => {
  const lut = new Uint8Array(256 * 4);
  for (let k = 0; k < 256; k++) {
    const [r, g, b] = viridis(k / 255);
    lut.set([r, g, b, 255], k * 4);
  }
  return lut;
})();

/** Palette position (0..1) for a score, clamped to the visible band. */
function paletteT(score) {
  return Math.min(1, Math.max(0, (score - MIN_SCORE) / (1 - MIN_SCORE)));
}

/**
 * CSS colour for a score, the same colour the heatmap paints (minus alpha).
 * Scores below MIN_SCORE get the bottom colour; NaN gets neutral grey.
 */
export function colorFor(score) {
  if (!Number.isFinite(score)) return 'rgb(128, 128, 128)';
  const k = Math.round(paletteT(score) * 255) * 4;
  return `rgb(${COLORMAP[k]}, ${COLORMAP[k + 1]}, ${COLORMAP[k + 2]})`;
}

/** CSS linear-gradient for a legend bar running MIN_SCORE (left) to 1 (right). */
export function legendGradient(direction = 'to right', steps = 11) {
  const stops = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    stops.push(`${colorFor(MIN_SCORE + t * (1 - MIN_SCORE))} ${(t * 100).toFixed(1)}%`);
  }
  return `linear-gradient(${direction}, ${stops.join(', ')})`;
}

/**
 * Paint LUT indexed by quantised score (k = round(score * 1023)), packed as
 * Uint32 in platform byte order so one write sets a whole RGBA pixel.
 */
const PAINT_BINS = 1024;
const PAINT_LUT = (() => {
  const lut = new Uint32Array(PAINT_BINS);
  const bytes = new Uint8Array(lut.buffer);
  for (let k = 0; k < PAINT_BINS; k++) {
    const score = k / (PAINT_BINS - 1);
    if (score < MIN_SCORE) continue; // stays 0: transparent
    const t = paletteT(score);
    const [r, g, b] = viridis(t);
    const a = Math.round(ALPHA_LO + (ALPHA_HI - ALPHA_LO) * t ** ALPHA_GAMMA);
    bytes.set([r, g, b, a], k * 4);
  }
  return lut;
})();

/**
 * Minimal ImageryProvider: one tile, the whole globe, the canvas itself.
 * Cesium only reads the properties below (checked against engine 26.1.0).
 */
class CanvasImageryProvider {
  constructor(canvas, ellipsoid) {
    this._canvas = canvas;
    this.tilingScheme = new Cesium.GeographicTilingScheme({
      ellipsoid,
      numberOfLevelZeroTilesX: 1,
      numberOfLevelZeroTilesY: 1,
    });
    this.rectangle = Cesium.Rectangle.fromDegrees(-180, -90, 180, 90);
    this.tileWidth = canvas.width;
    this.tileHeight = canvas.height;
    this.minimumLevel = 0;
    this.maximumLevel = 0;
    this.tileDiscardPolicy = undefined;
    this.errorEvent = new Cesium.Event();
    this.credit = undefined;
    this.proxy = undefined;
    this.hasAlphaChannel = true;
  }

  getTileCredits() {
    return undefined;
  }

  requestImage() {
    return Promise.resolve(this._canvas);
  }

  pickFeatures() {
    return undefined;
  }
}

/**
 * True when every tile Cesium rendered this frame already has this layer's
 * texture, so making it visible now cannot leave a hole. Reads Cesium
 * internals (QuadtreePrimitive._tilesToRender, TileImagery.readyImagery);
 * returns undefined if they are missing so the caller can fall back.
 */
function layerReadyOnAllTiles(globe, layer) {
  try {
    const tiles = globe._surface?._tilesToRender;
    if (!Array.isArray(tiles)) return undefined;
    if (tiles.length === 0) return false;
    for (const tile of tiles) {
      const list = tile.data?.imagery;
      if (!list) return false;
      let ok = false;
      for (let i = 0; i < list.length; i++) {
        const img = list[i].readyImagery;
        if (img && img.imageryLayer === layer && img.state === Cesium.ImageryState.READY) {
          ok = true;
          break;
        }
      }
      if (!ok) return false;
    }
    return true;
  } catch {
    return undefined;
  }
}

/**
 * @param {Cesium.Viewer} viewer  the Earth viewer
 * @param {object} meta           earth_meta.json (needs meta.grid.ncols/nrows)
 */
export function createHeatmap(viewer, meta) {
  const { ncols, nrows } = meta.grid;
  const { scene } = viewer;
  const layers = viewer.imageryLayers;

  const canvas = document.createElement('canvas');
  canvas.width = ncols;
  canvas.height = nrows;
  const ctx = canvas.getContext('2d');
  const imageData = ctx.createImageData(ncols, nrows);
  const pixels = new Uint32Array(imageData.data.buffer);

  let opacity = 1;
  let visible = null; // layer on screen
  let pending = null; // { layer, t0, paintMs, painted, resolve, swapped }
  let shownFrame = null; // pending entry waiting for its first drawn frame

  function makeLayer() {
    return new Cesium.ImageryLayer(new CanvasImageryProvider(canvas, scene.globe.ellipsoid), {
      alpha: 0, // loads, but Cesium skips drawing alpha-0 layers
      magnificationFilter: Cesium.TextureMagnificationFilter.NEAREST,
      minificationFilter: Cesium.TextureMinificationFilter.NEAREST,
    });
  }

  function dropLayer(layer) {
    if (layer && layers.contains(layer)) layers.remove(layer, true);
  }

  function finishPending(entry) {
    entry.showMs = performance.now() - entry.t0;
    api.lastShowMs = entry.showMs;
    entry.resolve({ paintMs: entry.paintMs, showMs: entry.showMs, painted: entry.painted });
  }

  function onPostRender() {
    // The frame after the swap is the first one that shows the new heatmap.
    if (shownFrame) {
      finishPending(shownFrame);
      shownFrame = null;
    }
    if (!pending) return;

    const elapsed = performance.now() - pending.t0;
    let ready = layerReadyOnAllTiles(scene.globe, pending.layer);
    if (ready === undefined) ready = scene.globe.tilesLoaded || elapsed > FALLBACK_SWAP_MS;
    if (!ready && elapsed > SWAP_TIMEOUT_MS) ready = true;

    if (ready) {
      pending.layer.alpha = opacity;
      dropLayer(visible);
      visible = pending.layer;
      shownFrame = pending;
      pending = null;
    }
    scene.requestRender();
  }

  const removePostRender = scene.postRender.addEventListener(onPostRender);

  const api = {
    /** Wall time of the last paint (buffer fill + putImageData), ms. */
    lastPaintMs: 0,
    /** Time from the last update() call to its first frame on screen, ms. */
    lastShowMs: 0,
    /** Cells painted (non-transparent) by the last update(). */
    lastPainted: 0,

    /**
     * Repaint from scores. Resolves once the new heatmap is on screen with
     * { paintMs, showMs, painted }. A newer update() supersedes an older one
     * that has not reached the screen yet; the older promise then resolves
     * with showMs = NaN.
     *
     * @param {Float32Array} scores  0..1 per land cell, NaN = unscored
     * @param {Uint32Array} index    cell id per entry, same order as scores
     * @param {Uint8Array} [mask]    0 = hidden by filters
     */
    update(scores, index, mask) {
      const t0 = performance.now();
      const n = Math.min(scores.length, index.length);
      const maxBin = PAINT_BINS - 1;
      const lo = MIN_SCORE;
      let painted = 0;

      pixels.fill(0);
      if (mask) {
        for (let i = 0; i < n; i++) {
          const s = scores[i];
          if (!(s >= lo) || mask[i] === 0) continue; // also skips NaN
          const k = s >= 1 ? maxBin : (s * maxBin + 0.5) | 0;
          pixels[index[i]] = PAINT_LUT[k];
          painted++;
        }
      } else {
        for (let i = 0; i < n; i++) {
          const s = scores[i];
          if (!(s >= lo)) continue;
          const k = s >= 1 ? maxBin : (s * maxBin + 0.5) | 0;
          pixels[index[i]] = PAINT_LUT[k];
          painted++;
        }
      }
      ctx.putImageData(imageData, 0, 0);
      const paintMs = performance.now() - t0;
      api.lastPaintMs = paintMs;
      api.lastPainted = painted;

      // A newer paint replaces a layer that never became visible.
      if (pending) {
        dropLayer(pending.layer);
        pending.resolve({ paintMs: pending.paintMs, showMs: NaN, painted: pending.painted });
        pending = null;
      }

      const layer = makeLayer();
      const at = visible && layers.contains(visible) ? layers.indexOf(visible) + 1 : layers.length;
      layers.add(layer, at);

      return new Promise((resolve) => {
        pending = { layer, t0, paintMs, painted, resolve };
        scene.requestRender();
      });
    },

    /** Remove the heatmap from the globe. */
    clear() {
      if (pending) {
        dropLayer(pending.layer);
        pending.resolve({ paintMs: pending.paintMs, showMs: NaN, painted: pending.painted });
        pending = null;
      }
      if (shownFrame) {
        finishPending(shownFrame);
        shownFrame = null;
      }
      dropLayer(visible);
      visible = null;
      pixels.fill(0);
      ctx.putImageData(imageData, 0, 0);
      scene.requestRender();
    },

    /** Layer-wide opacity multiplier, 0..1, on top of the per-pixel ramp. */
    setOpacity(a) {
      opacity = Math.min(1, Math.max(0, Number(a) || 0));
      if (visible) visible.alpha = opacity;
      scene.requestRender();
    },

    /** The heatmap layer currently on screen, or null. */
    get layer() {
      return visible;
    },

    /** The 1440 x 720 paint canvas (handy for debugging or a minimap). */
    get canvas() {
      return canvas;
    },

    destroy() {
      api.clear();
      removePostRender();
    },
  };

  return api;
}
