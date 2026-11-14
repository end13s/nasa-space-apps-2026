# web/public/data/ - the packed bundle the browser loads

These files are produced by `engine/pack_web.py`, not written by hand.

While the bundle is **synthetic**, it is kept out of git: it is ~16 MB that
regenerates in two commands, and committing a fake copy now plus a real copy
later would double the repository for nothing.

```bash
python engine/fake_data.py --out data_work
python engine/pack_web.py --grid data_work/earth_grid.parquet \
    --targets data_work/targets.json --out web/public/data
```

When the real Earth grid and the real `targets.json` are in place, Eduard
commits the bundle once so GitHub Pages can serve it:

```bash
git add -f web/public/data
```

Every bundle carries `"synthetic": true/false` in `earth_meta.json`. The About
modal must surface that flag, so a fake build can never be demoed as real.
