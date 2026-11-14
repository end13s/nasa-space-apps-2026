/**
 * Panel tabs (task F13): Explore, Site, Validation, Discoveries.
 *
 * Validation reads Eduard's validation.json (engine/validate.py, task E9).
 * Discoveries reads deep_dives/index.json when Sofia's write-ups land, and
 * until then lists the current top matches so the tab is never empty.
 */
import { colorFor } from '../heatmap.js';

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export function createTabs(root, onChange) {
  const buttons = [...root.querySelectorAll('[role="tab"]')];
  const panels = [...root.querySelectorAll('[role="tabpanel"]')];
  let current = 'explore';

  function show(name) {
    current = name;
    for (const b of buttons) {
      const on = b.dataset.tab === name;
      b.setAttribute('aria-selected', String(on));
      b.tabIndex = on ? 0 : -1;
    }
    for (const p of panels) p.hidden = p.dataset.panel !== name;
    onChange?.(name);
  }

  root.querySelector('[role="tablist"]').addEventListener('click', (e) => {
    const b = e.target.closest('[role="tab"]');
    if (b && !b.disabled) show(b.dataset.tab);
  });

  return {
    show,
    get current() {
      return current;
    },
    panel: (name) => panels.find((p) => p.dataset.panel === name),
    enable(name, on = true) {
      const b = buttons.find((x) => x.dataset.tab === name);
      if (b) b.disabled = !on;
    },
  };
}

const pct = (x) => `${Math.round(x)}`;

/** 81 -> "81st", 12 -> "12th". */
function ordinal(x) {
  const n = Math.round(x);
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] ?? 'th');
  return `${n}${suffix}`;
}

/** Validation tab for one body. */
export function renderValidation(el, validation, body) {
  if (!validation) {
    el.innerHTML = `<p class="hint">Validation results appear here once Eduard's run (E9) is in the data bundle.</p>`;
    return;
  }
  const h = validation.headline?.[body];
  const abl = validation.ablation?.[body] ?? {};
  if (!h) {
    el.innerHTML = `<p class="hint">No known ${esc(body)} analogs in the validation set yet.</p>`;
    return;
  }
  const bodyName = body === 'moon' ? 'Moon' : 'Mars';
  const sites = [...h.sites].sort((a, b) => b.percentile - a.percentile);
  const ablRows = Object.entries(abl)
    .filter(([, v]) => v !== 0)
    .map(([k, v]) => {
      const label = k.startsWith('without_')
        ? `Without ${k.slice(8)}`
        : k === 'gravity_scaling_on'
          ? 'Gravity scaling on'
          : k;
      return `<tr><td>${esc(label)}</td><td class="num ${v < 0 ? 'neg' : 'pos'}">${v > 0 ? '+' : ''}${v.toFixed(1)}</td></tr>`;
    })
    .join('');

  el.innerHTML = `
    ${validation.synthetic ? '<p class="chip synthetic inline">Synthetic data: these numbers are placeholders</p>' : ''}
    <p class="lead">Without being told where they are, the method ranks known ${bodyName} analogs
      at the <b>${ordinal(h.median_percentile)} percentile</b> of all land cells
      (random cells: ${ordinal(h.null_median_percentile)}).</p>
    <div class="stats">
      <div><b>${pct(h.recall_top5 * 100)}%</b><span>in the top 5%</span></div>
      <div><b>${pct(h.recall_top10 * 100)}%</b><span>in the top 10%</span></div>
      <div><b>${h.n_sites}</b><span>known sites</span></div>
    </div>
    <h3 class="ctl-title">Known analog sites</h3>
    <ul class="rank-list">
      ${sites
        .map(
          (s) => `
        <li>
          <span class="rank-name">${esc(s.name)}${s.accessible_by_design ? ' <small title="Famous partly because it is easy to reach">accessible by design</small>' : ''}</span>
          <span class="rank-bar"><i style="width:${Math.max(2, s.percentile)}%;background:${colorFor(s.percentile / 100)}"></i></span>
          <span class="num">${pct(s.percentile)}</span>
        </li>`,
        )
        .join('')}
    </ul>
    <h3 class="ctl-title">What drives it</h3>
    <p class="hint">Change in median percentile when one dimension is removed. A negative number means that dimension helps.</p>
    <table class="abl">${ablRows || '<tr><td>No ablation data</td></tr>'}</table>
  `;
}

/**
 * Discoveries tab. deepDives: [{id, name, lat, lon, body, summary}] or null.
 * hotspots: current worker hotspots (fallback list).
 */
export function renderDiscoveries(el, deepDives, hotspots, onOpen) {
  if (deepDives?.length) {
    el.innerHTML = deepDives
      .map(
        (d, k) => `
      <article class="discovery">
        <h3>${esc(d.name)}</h3>
        <p class="hint">${d.lat.toFixed(2)}, ${d.lon.toFixed(2)}${d.body ? ` · analog for ${esc(d.body)}` : ''}</p>
        <p>${esc(d.summary)}</p>
        <button type="button" class="btn" data-k="${k}">Open site</button>
      </article>`,
      )
      .join('');
    el.querySelectorAll('button[data-k]').forEach((b) =>
      b.addEventListener('click', () => onOpen(deepDives[Number(b.dataset.k)])),
    );
    return;
  }
  const top = (hotspots ?? []).slice(0, 3);
  el.innerHTML = `
    <p class="hint">Our three deep-dive discoveries (new sites, not known analogs) land here on Sunday.
      Meanwhile, the current top matches:</p>
    ${
      top.length
        ? top
            .map(
              (h, k) => `
      <article class="discovery">
        <h3>#${k + 1} · score ${h.score.toFixed(2)}</h3>
        <p class="hint">${h.lat.toFixed(2)}, ${h.lon.toFixed(2)}</p>
        <button type="button" class="btn" data-k="${k}">Open site</button>
      </article>`,
            )
            .join('')
        : '<p class="hint">Pick a target first.</p>'
    }
  `;
  el.querySelectorAll('button[data-k]').forEach((b) =>
    b.addEventListener('click', () => onOpen(top[Number(b.dataset.k)])),
  );
}
