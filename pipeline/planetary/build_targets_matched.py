"""Rebuild the target fingerprints at the ETOPO-matched slope baseline.

    python pipeline/planetary/build_targets_matched.py

The shipped web bundle uses these targets, because the shipped Earth grid is
ETOPO 60 arc-second (~1855 m). If Michal's builder gains a --grid-m flag, this
file can be deleted.

Does NOT modify pipeline/planetary/build_targets.py (Michal's file) and does NOT
write contract/targets.json. It imports Michal's builder, swaps the terrain
function for the same shared function at grid_m=1855, and writes the result to
data_work/targets_1855.json so validation can run before Michal commits the
official rebuild.
"""
import functools, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "pipeline" / "planetary"))

import terrain_features as tf
import build_targets as bt

bt.terrain_features = functools.partial(tf.terrain_features, grid_m=1855.0)

targets = bt.build()
for t in targets:
    t.setdefault("notes", []).append("terrain at grid_m=1855 m to match the ETOPO 60 arc-second Earth grid")
out = ROOT / "data_work" / "targets_1855.json"
out.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(targets)} targets)")
