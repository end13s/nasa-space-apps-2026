/**
 * Two Cesium viewers: the target body (Moon or Mars) on the left, Earth on
 * the right. No Cesium ion token: every imagery layer is a public NASA
 * service added explicitly.
 *
 * Imagery notes (checked Sat Nov 14 2026):
 * - Moon/Mars Trek tiles are a 2x1 equirectangular grid at level 0, 256 px,
 *   so Cesium's standard GeographicTilingScheme matches them.
 *   Max level: Moon WAC 8, Mars Viking MDIM2.1 7.
 * - GIBS EPSG:4326 *WMTS* tiles are 288 degrees wide at level 0 (not 180), so
 *   they do not line up with GeographicTilingScheme. We use GIBS *WMS*
 *   instead, which renders whatever bounding box Cesium asks for.
 */
import * as Cesium from 'cesium';

const TREK = 'https://trek.nasa.gov/tiles';

export const BODIES = {
  moon: {
    id: 'moon',
    name: 'Moon',
    ellipsoid: Cesium.Ellipsoid.MOON,
    imagery: () =>
      new Cesium.UrlTemplateImageryProvider({
        url: `${TREK}/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`,
        tilingScheme: new Cesium.GeographicTilingScheme({ ellipsoid: Cesium.Ellipsoid.MOON }),
        maximumLevel: 8,
        credit: new Cesium.Credit('NASA Moon Trek: LRO WAC global mosaic'),
      }),
  },
  mars: {
    id: 'mars',
    name: 'Mars',
    ellipsoid: Cesium.Ellipsoid.MARS,
    imagery: () =>
      new Cesium.UrlTemplateImageryProvider({
        url: `${TREK}/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`,
        tilingScheme: new Cesium.GeographicTilingScheme({ ellipsoid: Cesium.Ellipsoid.MARS }),
        maximumLevel: 7,
        credit: new Cesium.Credit('NASA Mars Trek: Viking MDIM2.1 color mosaic'),
      }),
  },
  earth: {
    id: 'earth',
    name: 'Earth',
    ellipsoid: Cesium.Ellipsoid.WGS84,
    imagery: () =>
      new Cesium.WebMapServiceImageryProvider({
        url: 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi',
        layers: 'BlueMarble_ShadedRelief_Bathymetry',
        parameters: { format: 'image/jpeg', transparent: false, styles: '' },
        tilingScheme: new Cesium.GeographicTilingScheme(),
        maximumLevel: 8,
        credit: new Cesium.Credit('NASA GIBS: Blue Marble shaded relief'),
      }),
  },
};

const VIEWER_OPTIONS = {
  animation: false,
  timeline: false,
  baseLayerPicker: false,
  geocoder: false,
  homeButton: false,
  sceneModePicker: false,
  navigationHelpButton: false,
  fullscreenButton: false,
  infoBox: false,
  selectionIndicator: false,
};

/**
 * Put the camera far enough out that the whole body fits the pane, whichever
 * way round the pane is (portrait panes on phones are narrow horizontally).
 */
export function homeView(viewer, body, lon = 0, lat = 15) {
  const r = body.ellipsoid.maximumRadius;
  const { frustum } = viewer.camera;
  const aspect = viewer.canvas.clientWidth / Math.max(1, viewer.canvas.clientHeight);
  const fovy = frustum.fovy ?? frustum.fov;
  const fovx = 2 * Math.atan(Math.tan(fovy / 2) * aspect);
  const halfFov = Math.min(fovx, fovy) / 2;
  let distance = (1.08 * r) / Math.sin(halfFov);
  // A pane with no size yet (hidden tab, 0x0 iframe) gives Cesium a NaN
  // aspect ratio; setView would then throw and stop the app from starting.
  if (!Number.isFinite(distance)) distance = 3 * r;
  viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(lon, lat, distance - r, body.ellipsoid),
  });
}

export function createViewer(container, bodyId) {
  const body = BODIES[bodyId];
  const isEarth = bodyId === 'earth';
  const viewer = new Cesium.Viewer(container, {
    ...VIEWER_OPTIONS,
    ellipsoid: body.ellipsoid,
    baseLayer: new Cesium.ImageryLayer(body.imagery()),
    // No air on the Moon; Mars' thin haze is not worth Earth's blue halo.
    skyAtmosphere: isEarth ? new Cesium.SkyAtmosphere(body.ellipsoid) : false,
  });
  const { scene } = viewer;
  scene.globe.showGroundAtmosphere = isEarth;
  scene.globe.enableLighting = false;
  scene.fog.enabled = isEarth;
  // Cesium's default sun/moon sprites are Earth-sky decorations; drop them.
  if (scene.sun) scene.sun.show = false;
  if (scene.moon) scene.moon.show = false;
  scene.globe.baseColor = Cesium.Color.fromCssColorString('#1a1d24');
  homeView(viewer, body);
  viewer.analogBody = bodyId;
  return viewer;
}

/**
 * The left globe can switch between Moon and Mars. Swapping the ellipsoid on
 * a live viewer is unreliable, so we destroy and rebuild it.
 */
export class TargetGlobe {
  constructor(container, bodyId = 'moon') {
    this.container = container;
    this.viewer = createViewer(container, bodyId);
    this.listeners = [];
  }

  get body() {
    return this.viewer.analogBody;
  }

  setBody(bodyId) {
    if (bodyId === this.body) return this.viewer;
    this.viewer.destroy();
    this.viewer = createViewer(this.container, bodyId);
    this.listeners.forEach((fn) => fn(this.viewer, bodyId));
    return this.viewer;
  }

  /** Called with (viewer, bodyId) every time the viewer is rebuilt. */
  onRebuild(fn) {
    this.listeners.push(fn);
  }
}
