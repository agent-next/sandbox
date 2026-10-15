#!/usr/bin/env bash
# push.sh <sandbox-id> <local-file> <remote-path> -- write a file into the sandbox by base64.
set -euo pipefail
sid="$1"; src="$2"; dst="$3"
b64="$(base64 -w0 "$src")"
sbx exec "$sid" --timeout 60 -- "mkdir -p '$(dirname "$dst")' && printf '%s' '$b64' | base64 -d > '$dst' && echo wrote $dst"
