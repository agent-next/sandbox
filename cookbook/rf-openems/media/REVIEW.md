# Media review — rf-openems

Built by `bash media/make_media.sh` in a fresh sandbox after `judge/setup.sh`
(exit 0). Every plotted number is read from `media/data/` (verdict JSONs from
`judge/grade.sh --json --trace`, seed 42, and one `judge/selftest.sh` log).
`fig_result.py` and `fig_loop.py` fail the build if two text boxes overlap.

## demo.mp4

```
codec_name=h264  pix_fmt=yuv420p  1920x1080  30/1 fps
duration=35.966667 s  size=533619 bytes
```

## What was checked

- `result.png`: the grader trace dips below the −10 dB line inside the G5
  band (2.401–2.499 GHz); min −18.5 dB at 2.44 GHz from
  `traces/good__s11_artifact.csv`. The verdict box quotes the G4/G5/G6/G8
  details from `verdicts/good.json`. The trace reads −17.1 dB at 2.45 GHz
  while G4 reports −17.0 dB: the verdict rounds dB to a 1 dB grid
  (`Q_DB` in `judge/grade.py`) and the figure says so. The fine-mesh curve
  reaches −10.4 dB at 2.45 GHz, which is why G8 passes with little margin.
- `result.png` right panel: probe phases from `good.json` `oracle`, ε_eff
  3.24 vs Hammerstad-Jensen 3.33, Δ 2.8 % (limit 4 %).
- `loop.png`: one row per known-bad variant with the first failing gate and
  its measured value from that variant's verdict JSON; good row PASS;
  footer from `data/selftest.txt` (7/7 killed, deterministic).
- Video frames at 2, 8, 14, 20, 26 and 33 s at full size: each FAIL scene
  names the killing gate and value; sanity-gate kills show no curve and say
  why; legends sit in the empty lower right; no text overlaps.

Two vision models from different families reviewed the PNGs and frames
(round 1 layout defects fixed; round 2 found none remaining that a zoom crop
confirmed).

## sha256

```
02f11c050c6f62605f2ef3d6a9bb9039ccbdcdac69d3109f364943de300ce7ea  result.png
eac87745d5073ed7486bda14554fde17591b812759874e6825c68c44a1bf688a  loop.png
69a42efa20916541f83edb86955b17459bf5769d813a9959872e738e46f15ac4  demo.mp4
```
