/**
 * Main-thread client for Eduard's scoring worker (task F5).
 *
 * Wraps the {type: ...} message protocol in promises:
 *   const scorer = createScorer(dataUrl);
 *   const meta = await scorer.ready;
 *   const res  = await scorer.score({ target, weights, ... });
 *   const card = await scorer.cell(cellIndex);
 *
 * Scoring is "latest wins": if the user drags a slider while a score is in
 * flight, only the newest request is sent next, and older promises resolve
 * with { stale: true } so callers can ignore them.
 */

export function createScorer(dataUrl, body = 'earth') {
  // The worker resolves relative URLs against its own script location, so it
  // must get an absolute data URL.
  const base = new URL(dataUrl, document.baseURI).href;
  const worker = new Worker(new URL('./worker/score.worker.js', import.meta.url), {
    type: 'module',
  });

  let readyResolve;
  let readyReject;
  const ready = new Promise((res, rej) => {
    readyResolve = res;
    readyReject = rej;
  });

  // One request of each kind in flight at a time; the worker answers in order.
  let inflight = null; // { kind: 'score' | 'cell', resolve, reject }
  let pendingScore = null; // { msg, resolve, reject } waiting for the worker
  const cellQueue = [];

  function pump() {
    if (inflight) return;
    if (pendingScore) {
      const { msg, resolve, reject } = pendingScore;
      pendingScore = null;
      inflight = { kind: 'score', resolve, reject, t0: performance.now() };
      worker.postMessage(msg);
      return;
    }
    if (cellQueue.length) {
      const { msg, resolve, reject } = cellQueue.shift();
      inflight = { kind: 'cell', resolve, reject };
      worker.postMessage(msg);
    }
  }

  worker.onmessage = (e) => {
    const msg = e.data;
    if (msg.type === 'ready') {
      readyResolve(msg.meta);
      return;
    }
    const req = inflight;
    inflight = null;
    if (msg.type === 'error') {
      const err = new Error(msg.error);
      if (req) req.reject(err);
      else readyReject(err);
    } else if (msg.type === 'scored' && req?.kind === 'score') {
      req.resolve({ ...msg, roundTripMs: performance.now() - req.t0 });
    } else if (msg.type === 'cellInfo' && req?.kind === 'cell') {
      req.resolve(msg.card);
    }
    pump();
  };

  worker.onerror = (e) => {
    const err = new Error(e.message || 'score worker crashed');
    readyReject(err);
    if (inflight) inflight.reject(err);
    inflight = null;
  };

  worker.postMessage({ type: 'init', dataUrl: base, body });

  // The heatmap needs cell ids on the main thread to place pixels.
  const index = fetch(`${base}${body}_index.bin`)
    .then((r) => {
      if (!r.ok) throw new Error(`${body}_index.bin: ${r.status}`);
      return r.arrayBuffer();
    })
    .then((buf) => new Uint32Array(buf));
  // Callers that await index see the error; this only stops the browser from
  // also reporting it as an unhandled rejection when nobody has awaited yet.
  index.catch(() => {});

  return {
    ready,
    index,

    /**
     * opts: { target, weights, gravityScaling, filters, k, minSepKm }
     * See web/README.md "Worker protocol" for the fields.
     */
    async score(opts) {
      await ready;
      return new Promise((resolve, reject) => {
        if (pendingScore) pendingScore.resolve({ stale: true });
        pendingScore = {
          msg: {
            type: 'score',
            body: opts.target?.body,
            k: 20,
            minSepKm: 200,
            ...opts,
          },
          resolve,
          reject,
        };
        pump();
      });
    },

    /** Everything a site card needs for one cell (index into scores[]). */
    async cell(cellIndex) {
      await ready;
      return new Promise((resolve, reject) => {
        cellQueue.push({ msg: { type: 'cell', cellIndex }, resolve, reject });
        pump();
      });
    },

    terminate() {
      worker.terminate();
    },
  };
}
