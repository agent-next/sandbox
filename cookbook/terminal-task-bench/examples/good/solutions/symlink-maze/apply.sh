#!/usr/bin/env bash
# symlink-maze: point `current` at the release RELEASE.txt names, and get
# rid of the self-referential link.
#
# The target is read from RELEASE.txt rather than guessed, and the new link
# is written relative to the links/ directory so the tree survives a move.
# The payload is resolved through the link before the script reports
# success.
set -euo pipefail

WORK="${WORK:?WORK must point at the task work directory}"
cd "$WORK"

release="$(sed -n 's/^release:[[:space:]]*//p' RELEASE.txt | head -1)"
if [ -z "$release" ]; then
    echo "symlink-maze: RELEASE.txt does not name a release" >&2
    exit 1
fi
if [ ! -d "releases/$release" ]; then
    echo "symlink-maze: releases/$release does not exist" >&2
    exit 1
fi

# a cycle is not usable: drop it
rm -f links/loop

# relative target, from inside links/
ln -sfn "../releases/$release" links/current

# resolve it the way a consumer would, and fail here if it does not
if [ ! -f "links/current/payload/data.txt" ]; then
    echo "symlink-maze: links/current/payload/data.txt does not resolve" >&2
    exit 1
fi
if [ -L links/loop ]; then
    echo "symlink-maze: links/loop still exists" >&2
    exit 1
fi
echo "symlink-maze: links/current -> $(readlink links/current) "\
"(resolves to releases/$release)"
