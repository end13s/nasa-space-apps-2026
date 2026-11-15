/**
 * Site card (task F11): the panel a judge sees after clicking an Earth hotspot.
 *
 *   import { renderSiteCard } from './ui/siteCard.js';
 *   const handle = renderSiteCard(container, {
 *     card, target, weights, meta, breaksText, regolith, onClose,
 *   });
 *   handle.destroy();
 *
 * The card is appended to `container` (nothing already in it is removed), so
 * destroy the previous handle before rendering the next one.
 *
 * Dimensions whose weight is 0 are hidden everywhere on the card, including the
 * Construction panel when C has weight 0.
 *
 * Pure DOM + Chart.js. All text from data files goes in through textContent,
 * never innerHTML.
 */
import {
  Chart,
  RadarController,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from 'chart.js';
import { colorFor } from '../heatmap.js';
import { GRADE_LABELS } from '../worker/score_core.js';
import './siteCard.css';

Chart.register(RadarController, RadialLinearScale, PointElement, LineElement, Filler, Tooltip);

/**
 * Construction test claims. Finn fills these from the expert call; any line
 * that starts with "TODO" renders as a dashed placeholder.
 */
export const CONSTRUCTION_TESTS = {
  could: [
    'TODO (Finn): what a foundation or landing-pad test on this ground would prove.',
    'TODO (Finn): second claim from the expert call.',
  ],
  couldnt: [
    'TODO (Finn): what this ground cannot tell you about building at the target.',
    'TODO (Finn): second limit from the expert call.',
  ],
};

const DIM_FALLBACK_ORDER = ['T', 'H', 'M', 'W', 'B', 'C', 'A', 'I'];
const SITE_COLOR = '#5ab0f0';
const BODY_COLOR = { mars: '#e8835a', moon: '#c3cbd8' };
const BODY_NAME = { mars: 'Mars', moon: 'Moon', earth: 'Earth' };
const MARKER = { strong: '✅', partial: '◐', breaks: '❌', nodata: '○' };

// ---------------------------------------------------------------- helpers

const fin = (x) => typeof x === 'number' && Number.isFinite(x);
const num = (x) => (fin(x) ? x : NaN);
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const fmt = (x, digits = 2) => (fin(x) ? x.toFixed(digits) : 'n/a');

function fmtPct(frac) {
  if (!fin(frac)) return 'n/a';
  const p = frac * 100;
  return `${p > 0 && p < 10 ? p.toFixed(1) : Math.round(p)}%`;
}

function fmtLat(lat) {
  return `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? 'N' : 'S'}`;
}

function fmtLon(lon) {
  return `${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? 'E' : 'W'}`;
}

/** Minutes as "X h Y min". At or above the data cap: "over X h". */
function fmtTravel(min, cap) {
  if (fin(cap) && min >= cap) return `over ${Math.round(cap / 60)} h`;
  let h = Math.floor(min / 60);
  let m = Math.round(min - h * 60);
  if (m === 60) {
    h += 1;
    m = 0;
  }
  return h > 0 ? `${h} h ${m} min` : `${m} min`;
}

function fmtKm(km, cap) {
  const s = Math.round(km).toLocaleString('en-US');
  return fin(cap) && km >= cap ? `over ${s} km` : `${s} km`;
}

function hexToRgba(hex, a) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.replace(/./g, '$&$&') : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

/** Dark or light ink for text on a colorFor() background. */
function inkFor(rgb) {
  const m = rgb.match(/\d+/g);
  if (!m) return '#fff';
  const [r, g, b] = m.map(Number);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 ? '#0b0e14' : '#ffffff';
}

/** Two-line radar label for long names, split at the space nearest the middle. */
function wrapLabel(name) {
  if (name.length <= 10 || !name.includes(' ')) return name;
  const mid = name.length / 2;
  let best = -1;
  for (let i = 0; i < name.length; i++) {
    if (name[i] === ' ' && (best < 0 || Math.abs(i - mid) < Math.abs(best - mid))) best = i;
  }
  return [name.slice(0, best), name.slice(best + 1)];
}

/** Tiny element builder. attrs: class, text, title, style, data-*, aria-*, etc. */
function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function sectionTitle(text) {
  return h('h3', { class: 'sc-h', text });
}

function chip(text, kind, title) {
  return h('span', { class: `sc-chip${kind ? ` sc-chip-${kind}` : ''}`, title, text });
}

function unverifiedTag() {
  return h('span', {
    class: 'sc-unverified',
    title: 'Placeholder value from regolith_constants.json, not yet checked against a source.',
    text: 'unverified',
  });
}

function cssVar(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

// ---------------------------------------------------------------- sections

function renderHeader(ctx) {
  const { card, target, meta, onClose } = ctx;
  const strength = num(card.proxy?.proxy_strength ?? card.overall);

  const chips = h('div', { class: 'sc-chips' });
  if (card.country && card.country !== '---') chips.append(chip(card.country, 'country', 'Country code'));
  if (card.partial) {
    chips.append(
      chip('partial data', 'warn', 'Some inputs are missing for this cell, so the score uses fewer features.'),
    );
  }
  if (target?.synthetic || meta?.synthetic) {
    chips.append(chip('synthetic data', 'synthetic', 'Built from placeholder data, not real measurements.'));
  }

  let closeBtn = null;
  if (typeof onClose === 'function') {
    closeBtn = h('button', { class: 'sc-close', type: 'button', 'aria-label': 'Close site card', text: '×' });
    closeBtn.addEventListener('click', onClose);
    ctx.cleanups.push(() => closeBtn.removeEventListener('click', onClose));
  }

  const bodyName = BODY_NAME[target?.body] ?? target?.body ?? '';
  const header = h(
    'header',
    { class: 'sc-head' },
    h(
      'div',
      { class: 'sc-head-top' },
      h('span', { class: 'sc-eyebrow', text: 'Earth site' }),
      closeBtn,
    ),
    h(
      'div',
      { class: 'sc-head-main' },
      h(
        'div',
        { class: 'sc-head-text' },
        h('div', { class: 'sc-coords', text: `${fmtLat(card.lat)}, ${fmtLon(card.lon)}` }),
        h('div', {
          class: 'sc-vs',
          text: `Compared with ${target?.name ?? 'the target'}${bodyName ? `, ${bodyName}` : ''}`,
        }),
        chips.childElementCount ? chips : null,
      ),
    ),
  );

  // Secondary field, not the headline: the columns below are the claim.
  const band = fin(card.p10) && fin(card.p90) ? ` (P10 to P90: ${fmt(card.p10)} to ${fmt(card.p90)})` : '';
  header.append(
    h(
      'div',
      {
        class: 'sc-strength',
        'data-slot': 'uncertainty',
        title: 'Weighted similarity for this experiment, 0 to 1, same colour as the heatmap',
      },
      h('span', { class: 'sc-strength-dot', style: { background: colorFor(strength) } }),
      `Proxy strength ${fmt(strength)}${band}`,
    ),
  );
  return header;
}

function renderRadar(ctx) {
  const { card, target, dims, dimName, root } = ctx;
  const section = h('section', { class: 'sc-section' }, sectionTitle('Similarity by dimension'));
  const targetColor = BODY_COLOR[target?.body] ?? '#c3cbd8';
  const targetName = target?.name ?? 'Target';

  // A radar needs at least three axes; fewer get simple bars.
  if (dims.length < 3) {
    const list = h('div', { class: 'sc-dimbars' });
    for (const d of dims) {
      const v = num(card.dims?.[d]);
      list.append(
        h(
          'div',
          { class: 'sc-dimbar' },
          h('span', { class: 'sc-dimbar-name', text: dimName(d) }),
          h(
            'span',
            { class: 'sc-track' },
            h('span', {
              class: 'sc-fill',
              style: { width: `${fin(v) ? clamp01(v) * 100 : 0}%`, background: SITE_COLOR },
            }),
          ),
          h('span', { class: 'sc-val', text: fmt(v) }),
        ),
      );
    }
    section.append(list, h('p', { class: 'sc-note', text: `1.00 is a perfect match to ${targetName}.` }));
    return section;
  }

  const wrap = h('div', { class: 'sc-radar' });
  const canvas = h('canvas', {
    role: 'img',
    'aria-label': `Similarity of this site to ${targetName} by dimension: ${dims
      .map((d) => `${dimName(d)} ${fmt(num(card.dims?.[d]))}`)
      .join(', ')}`,
  });
  wrap.append(canvas);

  const legend = h(
    'div',
    { class: 'sc-legend' },
    h(
      'span',
      { class: 'sc-legend-item' },
      h('span', { class: 'sc-swatch', style: { background: SITE_COLOR } }),
      'This site',
    ),
    h(
      'span',
      { class: 'sc-legend-item' },
      h('span', { class: 'sc-swatch sc-swatch-ring', style: { borderColor: targetColor } }),
      `${targetName} (perfect match)`,
    ),
  );
  section.append(wrap, legend);

  // Build the chart once the section is in the document, so it can size itself.
  ctx.afterMount.push(() => {
    const grid = cssVar(root, '--border', '#2a3242');
    const text = cssVar(root, '--text', '#e6e9ef');
    const family = getComputedStyle(root).fontFamily;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const values = dims.map((d) => {
      const v = num(card.dims?.[d]);
      return fin(v) ? clamp01(v) : null;
    });

    ctx.chart = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: dims.map((d, i) => {
          const label = wrapLabel(dimName(d));
          return values[i] === null ? [label, '(no data)'].flat() : label;
        }),
        datasets: [
          {
            label: 'This site',
            data: values,
            borderColor: SITE_COLOR,
            backgroundColor: hexToRgba(SITE_COLOR, 0.28),
            borderWidth: 2,
            pointRadius: 3,
            pointHoverRadius: 5,
            pointBackgroundColor: SITE_COLOR,
            pointBorderColor: SITE_COLOR,
            fill: true,
            spanGaps: true,
            order: 1,
          },
          {
            label: `${targetName} (perfect match)`,
            data: dims.map(() => 1),
            borderColor: hexToRgba(targetColor, 0.6),
            backgroundColor: hexToRgba(targetColor, 0.05),
            borderDash: [4, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            pointHoverRadius: 0,
            pointHitRadius: 0,
            fill: true,
            order: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reduced ? false : { duration: 350 },
        layout: { padding: 0 },
        scales: {
          r: {
            min: 0,
            max: 1,
            beginAtZero: true,
            ticks: { display: false, stepSize: 0.25 },
            grid: { color: grid },
            angleLines: { color: grid },
            pointLabels: { color: text, padding: 4, font: { size: 11, family } },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: (item) => item.datasetIndex === 0,
            titleFont: { family },
            bodyFont: { family },
            callbacks: {
              title: (items) => dimName(dims[items[0].dataIndex]),
              label: (item) => `This site: ${fmt(item.raw)}`,
            },
          },
        },
      },
    });
  });
  return section;
}

/** Evidence chip for one variable. DEF (exact by definition) is a dash, not a grade. */
function gradeChip(grade) {
  if (!grade) return null;
  const g = String(grade).toUpperCase();
  const title = `Evidence: ${GRADE_LABELS[g] ?? 'not graded'}`;
  if (g === 'DEF') return h('span', { class: 'sc-grade sc-grade-def', title, text: '–' });
  return h('span', { class: `sc-grade sc-grade-${g.toLowerCase()}`, title, text: g });
}

/** One proxy row: name, evidence chip, score, then its note/correction/reason verbatim. */
function proxyRow(row, { showScore = true, text } = {}) {
  return h(
    'li',
    { class: 'sc-prow' },
    h(
      'div',
      { class: 'sc-prow-head' },
      h('strong', { class: 'sc-prow-name', text: row.label ?? row.id }),
      gradeChip(row.grade),
      showScore && fin(row.score) ? h('span', { class: 'sc-prow-score', text: fmt(row.score) }) : null,
    ),
    text ? h('p', { class: 'sc-prow-text', text }) : null,
  );
}

function proxyColumn(kind, title, rows, opts) {
  const col = h(
    'div',
    { class: `sc-pcol sc-pcol-${kind}` },
    h(
      'h4',
      { class: 'sc-ptitle' },
      h('span', { text: title }),
      h('span', { class: 'sc-count', text: String(rows.length) }),
    ),
  );
  if (rows.length) {
    col.append(h('ul', { class: 'sc-plist' }, rows.map((r) => proxyRow(r, opts(r)))));
  } else {
    col.append(h('p', { class: 'sc-note', text: 'None for this site.' }));
  }
  return col;
}

/**
 * Proxy card: Supports / Conditional / Cannot test, straight from card.proxy
 * (worker, score_core.js proxyCard). All text comes from the worker rows;
 * Cannot test is the most prominent block and never collapses.
 */
function renderProxy(ctx) {
  const p = ctx.card.proxy;
  if (!p) {
    return h(
      'section',
      { class: 'sc-section' },
      h('p', { class: 'sc-note', text: 'No proxy breakdown in this data bundle. Rebuild it with the current engine.' }),
    );
  }
  const supports = p.supports ?? [];
  const conditional = p.conditional ?? [];
  const cannot = p.cannot_test ?? [];
  const notMatched = p.not_matched ?? [];

  const supportsCol = proxyColumn('supports', 'Supports', supports, (r) => ({ text: r.note }));
  if (notMatched.length) {
    supportsCol.append(
      h(
        'div',
        { class: 'sc-pdim' },
        h('h5', { class: 'sc-pdim-title', text: `Measured, no match (${notMatched.length})` }),
        h('ul', { class: 'sc-plist' }, notMatched.map((r) => proxyRow(r))),
      ),
    );
  }

  const top = h(
    'div',
    { class: 'sc-ptop' },
    supportsCol,
    proxyColumn('conditional', 'Conditional', conditional, (r) => ({ text: r.correction })),
  );

  const cannotBlock = h(
    'section',
    { class: 'sc-cannot', 'aria-label': 'Cannot test here' },
    h(
      'h4',
      { class: 'sc-cannot-title' },
      h('span', { text: 'Cannot test here' }),
      h('span', { class: 'sc-count', text: String(cannot.length) }),
    ),
    cannot.length
      ? h('ul', { class: 'sc-plist' }, cannot.map((r) => proxyRow(r, { showScore: false, text: r.reason })))
      : h('p', { class: 'sc-note', text: 'Nothing flagged for this target.' }),
  );

  const legend = h(
    'p',
    { class: 'sc-glegend' },
    'Evidence: ',
    ['A', 'B', 'C', 'D', 'DEF'].flatMap((g, i) => [
      i ? ' · ' : null,
      gradeChip(g),
      ` ${GRADE_LABELS[g] ?? ''}`,
    ]),
  );

  return h('div', { class: 'sc-proxy' }, h('section', { class: 'sc-section' }, top), cannotBlock, legend);
}

function renderAlwaysOn(ctx) {
  const { target, breaksText } = ctx;
  const always = breaksText?.always_on ?? {};
  const bodyItems = always[target?.body] ?? [];
  const earthItems = always.earth_side ?? [];
  if (!bodyItems.length && !earthItems.length) return null;

  const bodyName = BODY_NAME[target?.body] ?? 'Target';
  const details = h(
    'details',
    { class: 'sc-section sc-details' },
    h(
      'summary',
      { class: 'sc-summary' },
      h('span', { text: 'Never reproducible on Earth' }),
      h('span', { class: 'sc-count', text: String(bodyItems.length + earthItems.length) }),
    ),
  );
  if (bodyItems.length) {
    details.append(
      h('h4', { class: 'sc-subh', text: `${bodyName} conditions` }),
      h('ul', { class: 'sc-blist' }, bodyItems.map((t) => h('li', { text: t }))),
    );
  }
  if (earthItems.length) {
    details.append(
      h('h4', { class: 'sc-subh', text: 'On the Earth side' }),
      h('ul', { class: 'sc-blist' }, earthItems.map((t) => h('li', { text: t }))),
    );
  }
  return details;
}

/** One paired-bar row: target vs this site on the same scale. */
function pairRow({ label, hint, tag, lo, hi, target, site, format, band, targetColor }) {
  const pos = (v) => (fin(v) && hi > lo ? clamp01((v - lo) / (hi - lo)) * 100 : 0);
  const bar = (v, color, cls, bandRange) => {
    const track = h('span', { class: 'sc-track' });
    if (bandRange && fin(bandRange.min) && fin(bandRange.max)) {
      const a = pos(bandRange.min);
      const b = pos(bandRange.max);
      track.append(
        h('span', {
          class: 'sc-band',
          title: `Typical range ${format(bandRange.min)} to ${format(bandRange.max)}`,
          style: { left: `${a}%`, width: `${Math.max(0, b - a)}%`, background: hexToRgba(color, 0.28) },
        }),
      );
    }
    if (fin(v)) {
      track.append(
        h('span', { class: 'sc-fill', style: { width: `max(3px, ${pos(v)}%)`, background: color } }),
      );
    }
    return h('div', { class: `sc-bar ${cls}` }, track, h('span', { class: 'sc-val', text: fin(v) ? format(v) : 'n/a' }));
  };

  return h(
    'div',
    { class: 'sc-pair' },
    h(
      'div',
      { class: 'sc-pair-label' },
      h('span', { class: 'sc-pair-name', text: label }),
      hint ? h('span', { class: 'sc-pair-hint', text: hint }) : null,
      tag,
    ),
    bar(target, targetColor, 'sc-bar-target', band),
    bar(site, SITE_COLOR, 'sc-bar-site'),
  );
}

function featureRange(meta, id, lo, hi) {
  const f = meta?.features?.find((x) => x.id === id);
  return { lo: fin(f?.lo) ? f.lo : lo, hi: fin(f?.hi) ? f.hi : hi };
}

function renderConstruction(ctx) {
  const { card, target, meta, weights, breaksText, regolith } = ctx;
  const body = target?.body;
  const targetName = target?.name ?? 'Target';
  const targetColor = BODY_COLOR[body] ?? '#c3cbd8';
  const tf = target?.features ?? {};
  const sv = card.values ?? {};
  const reg = regolith?.[body] ?? null;
  const score = num(card.dims?.C);
  const verdict = card.verdict?.C ?? 'nodata';
  const bg = colorFor(score);

  const section = h('section', { class: 'sc-section sc-construct' });

  section.append(
    h(
      'div',
      { class: 'sc-chead' },
      h(
        'div',
        { class: 'sc-chead-text' },
        h('span', { class: 'sc-eyebrow sc-accent', text: 'Building a base' }),
        h('h3', { class: 'sc-ctitle', text: 'Construction' }),
      ),
      h(
        'span',
        { class: 'sc-cscore', style: { background: bg, color: inkFor(bg) }, title: 'Construction similarity, 0 to 1' },
        h('span', { 'aria-hidden': 'true', text: MARKER[verdict] ?? '' }),
        fmt(score),
      ),
    ),
  );
  const why = breaksText?.dimensions?.C?.why;
  if (why) section.append(h('p', { class: 'sc-cwhy', text: why }));

  // Paired bars: ground, target vs this site.
  const pairs = h(
    'div',
    { class: 'sc-pairs' },
    h(
      'div',
      { class: 'sc-legend sc-legend-tight' },
      h('span', { class: 'sc-legend-item' }, h('span', { class: 'sc-swatch', style: { background: targetColor } }), targetName),
      h('span', { class: 'sc-legend-item' }, h('span', { class: 'sc-swatch', style: { background: SITE_COLOR } }), 'This site'),
    ),
  );

  const flat = featureRange(meta, 'flat_frac', 0, 1);
  pairs.append(
    pairRow({
      label: 'Flat ground',
      hint: 'share under 5° slope',
      ...flat,
      target: num(tf.flat_frac),
      site: num(sv.flat_frac),
      format: fmtPct,
      targetColor,
    }),
  );
  const steep = featureRange(meta, 'steep_frac', 0, 1);
  pairs.append(
    pairRow({
      label: 'Steep ground',
      hint: 'share over 25° slope',
      ...steep,
      target: num(tf.steep_frac),
      site: num(sv.steep_frac),
      format: fmtPct,
      targetColor,
    }),
  );

  // Bulk density: the target's value is copied from regolith_constants, so it
  // inherits that entry's verified flag. Fall back to the typical value.
  const bd = reg?.bulk_density_g_cm3 ?? null;
  let bdTarget = num(tf.bulk_density);
  let bdHint = 'g/cm³';
  if (!fin(bdTarget) && fin(bd?.typical)) {
    bdTarget = bd.typical;
    bdHint = 'g/cm³, typical regolith';
  }
  const dens = featureRange(meta, 'bulk_density', 0.5, 3);
  pairs.append(
    pairRow({
      label: 'Bulk density',
      hint: bdHint,
      tag: bd && bd.verified === false ? unverifiedTag() : null,
      ...dens,
      target: bdTarget,
      site: num(sv.bulk_density),
      format: (v) => v.toFixed(2),
      band: bd ? { min: bd.min, max: bd.max } : null,
      targetColor,
    }),
  );
  section.append(pairs);

  // Thermal cycling: same feature as dimension H, shown here, not scored twice.
  const amp = featureRange(meta, 'diurnal_amp_k', 0, 300);
  const hWeighted = (weights?.H ?? 0) > 0;
  section.append(
    h(
      'div',
      { class: 'sc-block' },
      h('h4', { class: 'sc-subh', text: 'Thermal cycling' }),
      pairRow({
        label: 'Day to night swing',
        hint: 'K',
        ...amp,
        target: num(tf.diurnal_amp_k),
        site: num(sv.diurnal_amp_k),
        format: (v) => `${Math.round(v)} K`,
        targetColor,
      }),
      h('p', {
        class: 'sc-note',
        text: hWeighted
          ? 'Already scored under Thermal. Shown here for structures, not counted twice.'
          : 'Context for structures, not scored.',
      }),
    ),
  );

  // Earth-only context.
  section.append(
    h(
      'div',
      { class: 'sc-block' },
      h('h4', { class: 'sc-subh', text: 'Earth-only context (not scored)' }),
      h(
        'div',
        { class: 'sc-tiles' },
        tile('Sand in soil', fin(num(sv.sand_frac)) ? `${Math.round(sv.sand_frac)}%` : 'n/a'),
        tile('Depth to bedrock', fin(num(sv.bedrock_depth_m)) ? `${Math.round(sv.bedrock_depth_m)} m` : 'n/a'),
      ),
    ),
  );

  // Target regolith context from regolith_constants.json. One "unverified"
  // tag on the heading when every value is unverified, else one per row.
  const regRows = regolithRows(reg);
  if (regRows.length) {
    const allUnverified = regRows.every((r) => r.entry?.verified === false);
    for (const r of regRows) {
      if (!allUnverified && r.entry?.verified === false) r.tag = unverifiedTag();
    }
    section.append(
      h(
        'div',
        { class: 'sc-block' },
        h(
          'h4',
          { class: 'sc-subh' },
          `${BODY_NAME[body] ?? 'Target'} regolith (typical, not scored)`,
          allUnverified ? unverifiedTag() : null,
        ),
        kvList(regRows),
      ),
    );
  }

  // Test claims (Finn fills these in CONSTRUCTION_TESTS).
  section.append(
    h(
      'div',
      { class: 'sc-claims' },
      claimBox('A test here could prove', CONSTRUCTION_TESTS.could, 'could'),
      claimBox("A test here couldn't prove", CONSTRUCTION_TESTS.couldnt, 'couldnt'),
    ),
  );

  const notes = breaksText?.always_on?.construction_note ?? [];
  if (notes.length) {
    section.append(
      h(
        'div',
        { class: 'sc-block sc-cnotes' },
        h('h4', { class: 'sc-subh', text: 'True of every Earth site' }),
        h('ul', { class: 'sc-blist' }, notes.map((t) => h('li', { text: t }))),
      ),
    );
  }
  return section;
}

function tile(label, value) {
  return h(
    'div',
    { class: 'sc-tile' },
    h('span', { class: 'sc-tile-label', text: label }),
    h('span', { class: 'sc-tile-val', text: value }),
  );
}

/** Label / value rows. Each row: { label, value, tag? }. */
function kvList(rows) {
  return h(
    'div',
    { class: 'sc-kv' },
    rows.map((r) =>
      h(
        'div',
        { class: 'sc-kv-row' },
        h('span', { class: 'sc-kv-label' }, r.label, r.tag ? ' ' : null, r.tag ?? null),
        h('span', { class: 'sc-kv-val', text: r.value }),
      ),
    ),
  );
}

/** Typical target regolith properties; each row keeps its regolith entry. */
function regolithRows(reg) {
  if (!reg) return [];
  const rows = [];
  const c = reg.cohesion_kpa;
  if (fin(c?.typical)) rows.push({ label: 'Cohesion', value: `${c.typical} kPa`, entry: c });
  const f = reg.friction_angle_deg;
  if (fin(f?.typical)) rows.push({ label: 'Friction angle', value: `${f.typical}°`, entry: f });
  const t = reg.regolith_thickness_m;
  if (fin(t?.typical)) rows.push({ label: 'Regolith depth', value: `${t.typical} m`, entry: t });
  else if (fin(t?.mare) && fin(t?.highland)) {
    rows.push({ label: 'Regolith depth', value: `${t.mare} m mare, ${t.highland} m highland`, entry: t });
  }
  return rows;
}

function claimBox(title, items, kind) {
  return h(
    'div',
    { class: `sc-claim sc-claim-${kind}` },
    h('h4', { class: 'sc-subh', text: title }),
    h(
      'ul',
      { class: 'sc-blist' },
      (items ?? []).map((t) => {
        const todo = /^TODO\b/.test(t);
        return h('li', { class: todo ? 'sc-todo' : null, text: t });
      }),
    ),
  );
}

function renderLogistics(ctx) {
  const { card, meta } = ctx;
  const lg = card.logistics ?? {};
  const caps = meta?.logistics ?? {};
  const rows = [];
  const travel = num(lg.travel_min);
  if (fin(travel)) rows.push({ label: 'Travel to nearest city', value: fmtTravel(travel, caps.travel_min?.hi) });
  const prot = num(lg.protected_frac);
  if (fin(prot)) rows.push({ label: 'Protected area', value: fmtPct(prot) });
  const analog = num(lg.known_analog_km);
  if (fin(analog)) {
    rows.push({ label: 'Nearest known analog', value: fmtKm(analog, caps.known_analog_km?.hi) });
  }
  if (!rows.length) return null;
  return h('section', { class: 'sc-section' }, sectionTitle('Getting there'), kvList(rows));
}

function renderLinks(ctx) {
  const { lat, lon } = ctx.card;
  if (!fin(lat) || !fin(lon)) return null;
  const s = Math.max(-90, lat - 2).toFixed(2);
  const n = Math.min(90, lat + 2).toFixed(2);
  const url = `https://worldview.earthdata.nasa.gov/?v=${(lon - 2).toFixed(2)},${s},${(lon + 2).toFixed(2)},${n}`;
  return h(
    'a',
    { class: 'sc-link', href: url, target: '_blank', rel: 'noopener' },
    'Open in NASA Worldview',
    h('span', { class: 'sc-link-arrow', 'aria-hidden': 'true', text: '↗' }),
  );
}

function renderTerrainSlot() {
  return h(
    'div',
    { class: 'sc-slot', 'data-slot': 'terrain-profile' },
    h('p', { class: 'sc-note', text: 'Terrain profile coming from Sofia' }),
  );
}

// ---------------------------------------------------------------- entry

/**
 * Render a site card into `container`.
 *
 * @param {HTMLElement} container
 * @param {object} opts
 * @param {object} opts.card        worker cellInfo card
 * @param {object} opts.target      Moon/Mars target from targets.json
 * @param {object} opts.weights     {T,H,M,W,B,C,A,I}; weight 0 hides that dimension
 * @param {object} opts.meta        earth_meta.json
 * @param {object} opts.breaksText  breaks_text.json
 * @param {object} [opts.regolith]  regolith_constants.json, or null
 * @param {Function} [opts.onClose] adds a close button that calls this
 * @returns {{ el: HTMLElement, destroy: () => void }}
 */
export function renderSiteCard(container, opts = {}) {
  const { card, target = null, meta = null, breaksText = null, regolith = null, onClose } = opts;
  if (!card) throw new Error('renderSiteCard: card is required');

  const dimMeta = meta?.dimensions ?? {};
  const order = Object.keys(dimMeta).length ? Object.keys(dimMeta) : DIM_FALLBACK_ORDER;
  const weights =
    opts.weights ?? Object.fromEntries(order.map((d) => [d, dimMeta[d]?.default_weight ?? 1]));
  const dims = order.filter((d) => (weights[d] ?? 0) > 0);

  const root = h('article', {
    class: 'site-card',
    'aria-label': `Site card for ${fmtLat(card.lat)}, ${fmtLon(card.lon)}`,
  });

  const ctx = {
    card,
    target,
    meta,
    weights,
    breaksText,
    regolith,
    onClose,
    dims,
    dimName: (d) => dimMeta[d]?.name ?? d,
    root,
    chart: null,
    afterMount: [],
    cleanups: [],
  };

  root.append(
    ...[
      renderHeader(ctx),
      dims.length ? renderRadar(ctx) : null,
      renderProxy(ctx),
      renderAlwaysOn(ctx),
      (weights.C ?? 0) > 0 ? renderConstruction(ctx) : null,
      renderLogistics(ctx),
      renderLinks(ctx),
      renderTerrainSlot(),
    ].filter(Boolean),
  );

  container.append(root);
  for (const fn of ctx.afterMount) fn();

  let destroyed = false;
  return {
    el: root,
    destroy() {
      if (destroyed) return;
      destroyed = true;
      ctx.chart?.destroy();
      ctx.chart = null;
      for (const fn of ctx.cleanups) fn();
      root.remove();
    },
  };
}
