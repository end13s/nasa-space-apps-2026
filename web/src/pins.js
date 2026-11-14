/**
 * Earth-side markers and clicks (task F8).
 *
 * - setHotspots(hotspots): numbered pins for the top matches (worker output).
 * - setKnownAnalogs(rows): grey markers for the known analog sites, toggleable.
 * - Clicking a pin or anywhere on land reports a cell index (into scores[])
 *   through onSelect, so main.js can open the site card.
 */
import * as Cesium from 'cesium';

const PIN_COLOR = Cesium.Color.fromCssColorString('#ff5a36');
const PIN_SELECTED = Cesium.Color.fromCssColorString('#f4b740');
const KNOWN_COLOR = Cesium.Color.fromCssColorString('#c7ccd6');

/**
 * @param {Cesium.Viewer} viewer   Earth viewer
 * @param {object} meta            earth_meta.json (grid geometry)
 * @param {Uint32Array} index      cell id per scores[] entry
 * @param {{onSelect: (cellIndex: number, source: 'pin'|'click') => void,
 *          onMiss?: (lat: number, lon: number) => void}} handlers
 */
export function createPins(viewer, meta, index, { onSelect, onMiss }) {
  const pinBuilder = new Cesium.PinBuilder();
  const hot = new Cesium.CustomDataSource('hotspots');
  const known = new Cesium.CustomDataSource('known-analogs');
  viewer.dataSources.add(known);
  viewer.dataSources.add(hot);
  viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(
    Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK,
  );

  // cell id -> position in scores[], for click-anywhere.
  const { ncols, nrows, res_deg: res, lat0, lon0 } = meta.grid;
  const cellToIndex = new Int32Array(ncols * nrows).fill(-1);
  for (let i = 0; i < index.length; i++) cellToIndex[index[i]] = i;

  let selectedRank = -1;
  let hotspots = [];

  function pinImage(rank, selected) {
    return pinBuilder.fromText(String(rank + 1), selected ? PIN_SELECTED : PIN_COLOR, 38);
  }

  function setHotspots(list) {
    hotspots = list;
    selectedRank = -1;
    hot.entities.removeAll();
    list.forEach((h, rank) => {
      hot.entities.add({
        id: `hotspot-${rank}`,
        position: Cesium.Cartesian3.fromDegrees(h.lon, h.lat),
        billboard: {
          image: pinImage(rank, false),
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          // Keep pins clickable even where the globe surface is close.
          eyeOffset: new Cesium.Cartesian3(0, 0, -50),
        },
        properties: { kind: 'hotspot', rank, cellIndex: h.i },
      });
    });
  }

  function highlight(cellIndex) {
    const rank = hotspots.findIndex((h) => h.i === cellIndex);
    if (selectedRank >= 0) {
      const prev = hot.entities.getById(`hotspot-${selectedRank}`);
      if (prev) prev.billboard.image = pinImage(selectedRank, false);
    }
    selectedRank = rank;
    if (rank >= 0) {
      const e = hot.entities.getById(`hotspot-${rank}`);
      if (e) e.billboard.image = pinImage(rank, true);
    }
  }

  function setKnownAnalogs(rows) {
    known.entities.removeAll();
    for (const r of rows) {
      if (!Number.isFinite(r.lat) || !Number.isFinite(r.lon)) continue;
      known.entities.add({
        position: Cesium.Cartesian3.fromDegrees(r.lon, r.lat),
        point: {
          pixelSize: 7,
          color: KNOWN_COLOR,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 1.5,
        },
        label: {
          text: r.name,
          font: '12px system-ui, sans-serif',
          fillColor: KNOWN_COLOR,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(8, 0),
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          // Names only once you zoom in, or the globe turns into text.
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 4.0e6),
        },
        properties: { kind: 'known', id: r.id },
      });
    }
  }

  function cellIndexAt(lat, lon) {
    const row = Math.floor((lat0 - lat) / res);
    const col = Math.floor((lon - lon0) / res);
    if (row < 0 || row >= nrows || col < 0 || col >= ncols) return -1;
    return cellToIndex[row * ncols + col];
  }

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((click) => {
    const picked = viewer.scene.pick(click.position);
    const props = picked?.id?.properties;
    if (props?.kind?.getValue() === 'hotspot') {
      onSelect(props.cellIndex.getValue(), 'pin');
      return;
    }
    const cart = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid);
    if (!cart) return;
    const c = Cesium.Cartographic.fromCartesian(cart);
    const lat = Cesium.Math.toDegrees(c.latitude);
    const lon = Cesium.Math.toDegrees(c.longitude);
    const i = cellIndexAt(lat, lon);
    if (i >= 0) onSelect(i, 'click');
    else onMiss?.(lat, lon);
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  return {
    setHotspots,
    setKnownAnalogs,
    highlight,
    cellIndexAt,
    showKnown(on) {
      known.show = Boolean(on);
    },
    clear() {
      hotspots = [];
      selectedRank = -1;
      hot.entities.removeAll();
    },
  };
}
