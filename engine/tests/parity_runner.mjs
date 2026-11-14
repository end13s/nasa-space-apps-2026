// Node harness for engine/tests/test_parity.py.
// Reads a JSON job on argv[2], scores it with the same module the browser
// worker uses, prints {scores: [...], dims: {...}} as JSON on stdout.
//
//   node engine/tests/parity_runner.mjs job.json

import { readFileSync } from 'node:fs';
import { scoreAll } from '../../web/src/worker/score_core.js';

const job = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const features = Uint8Array.from(job.features);
const res = scoreAll(job.meta, features, job.target, job.weights, {
  gravityScaling: job.gravityScaling ?? false,
  body: job.body ?? null,
});

const dims = {};
for (const [d, arr] of Object.entries(res.dims)) dims[d] = Array.from(arr);
process.stdout.write(
  JSON.stringify({ scores: Array.from(res.scores), dims, partial: Array.from(res.partial) })
);
