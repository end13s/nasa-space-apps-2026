/**
 * Target picking on the Moon/Mars globe (task F7).
 *
 * - show(target): draws the fingerprint circle (target.radius_km), a marker
 *   and the name on the left globe.
 * - Clicking the left globe reports the clicked lat/lon through onPick, so
 *   main.js can snap to the nearest preset (click-anywhere fingerprints need
 *   Michal's global Moon/Mars grids, a stretch goal).
 *
 * The left viewer is rebuilt when the user switches Moon <-> Mars, so all
 * entities and the click handler are re-attached through TargetGlobe.onRebuild.
 */
import * as Cesium from 'cesium';
import { BODIES } from './globes.js';

const TARGET_COLOR = Cesium.Color.fromCssColorString('#f4b740');

/** Points on a small circle of radiusKm around (lat, lon), on a sphere of radius R. */
function circlePositions(lat, lon, radiusKm, ellipsoid, n = 128) {
  const R = ellipsoid.maximumRadius;
  const d = (radiusKm * 1000) / R;
  const p1 = Cesium.Math.toRadians(lat);
  const l1 = Cesium.Math.toRadians(lon);
  const out = [];
  for (let k = 0; k <= n; k++) {
    const th = (2 * Math.PI * k) / n;
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(th));
    const l2 =
      l1 +
      Math.atan2(
        Math.sin(th) * Math.sin(d) * Math.cos(p1),
        Math.cos(d) - Math.sin(p1) * Math.sin(p2),
      );
    out.push(Cesium.Cartesian3.fromRadians(l2, p2, 150, ellipsoid));
  }
  return out;
}

/** Great-circle distance on a body, km. */
export function distanceKm(lat1, lon1, lat2, lon2, radiusM) {
  const r = Math.PI / 180;
  const dLat = (lat2 - lat1) * r;
  const dLon = (lon2 - lon1) * r;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
  return (2 * radiusM * Math.asin(Math.min(1, Math.sqrt(a)))) / 1000;
}

export class TargetPicker {
  /**
   * @param {import('./globes.js').TargetGlobe} targetGlobe
   * @param {{onPick: (lat: number, lon: number) => void}} opts
   */
  constructor(targetGlobe, { onPick }) {
    this.globe = targetGlobe;
    this.onPick = onPick;
    this.current = null;
    this.handler = null;
    this.attach(targetGlobe.viewer);
    targetGlobe.onRebuild((viewer) => {
      this.attach(viewer);
      if (this.current?.body === targetGlobe.body) this.show(this.current, { fly: false });
      else this.current = null;
    });
  }

  attach(viewer) {
    if (this.handler && !this.handler.isDestroyed()) this.handler.destroy();
    this.viewer = viewer;
    this.ds = new Cesium.CustomDataSource('target');
    viewer.dataSources.add(this.ds);
    // No zoom-to-entity on double click; it fights the synced fly-to.
    viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(
      Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
    );
    this.handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    this.handler.setInputAction((click) => {
      const { ellipsoid } = BODIES[this.globe.body];
      const cart = viewer.camera.pickEllipsoid(click.position, ellipsoid);
      if (!cart) return;
      const c = Cesium.Cartographic.fromCartesian(cart, ellipsoid);
      this.onPick(Cesium.Math.toDegrees(c.latitude), Cesium.Math.toDegrees(c.longitude));
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  }

  /** Draw the target and (by default) fly the left camera to it. */
  show(target, { fly = true } = {}) {
    this.current = target;
    const { ellipsoid } = BODIES[target.body];
    const { entities } = this.ds;
    entities.removeAll();
    entities.add({
      polyline: {
        positions: circlePositions(target.lat, target.lon, target.radius_km ?? 15, ellipsoid),
        width: 2.5,
        material: TARGET_COLOR,
        arcType: Cesium.ArcType.NONE,
      },
    });
    entities.add({
      position: Cesium.Cartesian3.fromDegrees(target.lon, target.lat, 300, ellipsoid),
      point: {
        pixelSize: 9,
        color: TARGET_COLOR,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
      },
      label: {
        text: target.name,
        font: '600 13px system-ui, sans-serif',
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -18),
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      },
    });
    if (fly) flyToPoint(this.viewer, target.body, target.lat, target.lon, 0.25);
  }

  clear() {
    this.current = null;
    this.ds.entities.removeAll();
  }
}

/**
 * Fly a viewer to (lat, lon) with the camera at `ratio` body radii above the
 * surface, tilted a little so polar targets don't hit the straight-down
 * singularity. Using the same ratio on both globes is what makes the synced
 * fly-to (F12) show the two sites at matching scale.
 */
export function flyToPoint(viewer, bodyId, lat, lon, ratio = 0.08, duration = 1.6) {
  const { ellipsoid } = BODIES[bodyId];
  const R = ellipsoid.maximumRadius;
  const center = Cesium.Cartesian3.fromDegrees(lon, lat, 0, ellipsoid);
  viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(center, 1), {
    offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-70), ratio * R),
    duration,
  });
}
