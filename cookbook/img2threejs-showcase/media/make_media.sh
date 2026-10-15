#!/usr/bin/env bash
# Regenerate media/ from run.py output directories, oldest first: media/make_media.sh RUN_DIR [RUN_DIR ...]
exec python3 "$(dirname "$0")/make_media.py" "$@"
