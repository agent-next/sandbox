# Reviewing the gpu-kernel demo media

All media in this directory is generated. Nothing is edited by hand; if
an output disagrees with the data, the data or the generator is wrong —
do not patch the PNG/MP4.

## Source data

| file | provenance |
|---|---|
| `data/gpu-run.log` | verbatim stdout of `python3 cookbook/gpu-kernel/run.py --gpu` on a 1 GiB RTX 5090 slice lease |
| `data/report.json` | the raw exec `report` dict from the same run, written by `run.py --gpu --report-json <path>` (good verdict incl. timing + per-mutant failed gates) |

`data/report.json` is produced only by a real GPU run. If it is absent,
`make_media.sh` exits non-zero with the command needed to produce it.

## Regenerating

```bash
bash cookbook/gpu-kernel/media/make_media.sh
```

- creates `media/.venv` (pinned `matplotlib==3.10.8`, `numpy==2.4.3`),
- requires `ffmpeg` + `ffprobe` on PATH,
- runs `make_figures.py` (result.png, loop.png) then `make_video.py`
  (demo.mp4, 1920x1080, 30 fps, libx264 CRF 18, ~30-45 s),
- writes `MANIFEST.json`: sha256 of every output and of each output's
  source data.

Outputs (`*.png`, `*.mp4`), `.venv/` and `.frames/` are gitignored; the
manifest and this file are committed.

## Reviewer checklist

1. `data/` files unchanged since the lead's GPU run (`git log data/`).
2. `bash make_media.sh` exits 0 and rewrites `MANIFEST.json`; the
   recorded sha256s reproduce bit-for-bit on re-run with unchanged data
   (PNG/MP4 bytes are deterministic for fixed inputs and tool versions).
3. `result.png`: every `max_abs_err` point sits below the 1e-5 tolerance
   line; the GB/s label equals `2*4096*4096*4 / kernel_ms / 1e9`.
4. `loop.png`: one red cell per mutant row, and the red cell's gate name
   matches the `failed` list in `data/report.json` (10/10 killed).
5. `demo.mp4`: `ffprobe` shows 1920x1080, ~30 fps, 30-45 s; the terminal
   section is `data/gpu-run.log` verbatim (lease create -> exec ->
   verdict -> destroy/verified); captions repeat `data/report.json`
   numbers only.
6. `media/.venv/bin/python media/test_make_figures.py` passes.

## Fail-loudly contract

`make_figures.py` and `make_video.py` exit non-zero and name the missing
dotted field (e.g. `good.verdict.timing.kernel_ms`) or required log line
rather than rendering a partial figure.
