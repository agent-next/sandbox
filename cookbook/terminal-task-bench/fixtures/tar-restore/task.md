# Task: restore the archive

`work/archive.tar.gz` holds a small release, and `work/manifest.json`
records what every extracted path must look like: its sha256, its mode and
its size. The `work/restore/` directory is a partial, partly wrong attempt
— one file has the wrong contents and a stale file is left over.

Make `work/restore/` match the manifest exactly:

- every path in `manifest.json` exists under `restore/`, with exactly the
  recorded contents and mode;
- nothing else exists under `restore/` — remove leftovers;
- `archive.tar.gz` and `manifest.json` are unchanged.

Verify with `bash verify.sh "$PWD/work"` (from this directory).
