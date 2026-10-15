#!/bin/bash
# new-demo.sh <name> — scaffold cookbook/<name>/ from cookbook/_template/.
# <name>: lowercase letters, digits and dashes, no leading/trailing dash
# (e.g. `tank-level`). Substitutes __NAME__ in the copied files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="$ROOT/cookbook/_template"

name="${1:-}"
if [ -z "$name" ]; then
    echo "usage: $0 <name>" >&2
    exit 2
fi
case "$name" in
    *[!a-z0-9-]* | -* | *-)
        echo "new-demo: <name> must be [a-z0-9-]+ with no leading/trailing dash" >&2
        exit 2
        ;;
esac

dest="$ROOT/cookbook/$name"
if [ -e "$dest" ]; then
    echo "new-demo: cookbook/$name already exists" >&2
    exit 1
fi

cp -R "$TEMPLATE" "$dest"
grep -rl '__NAME__' "$dest" | while IFS= read -r f; do
    sed -i "s/__NAME__/$name/g" "$f"
done
chmod +x "$dest/run.py" "$dest/judge/"*.sh "$dest/media/make_media.sh"

echo "created cookbook/$name:"
(cd "$dest" && find . -type f | sort)
