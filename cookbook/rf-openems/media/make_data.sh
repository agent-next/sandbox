#!/bin/bash
# Collect all the judge outputs the media needs: grade.sh on the good
# artifact and each mutant with --trace, then selftest.sh once.
# Media generation reads the saved JSON files in media/data/.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
VD="$MEDIA/data/verdicts"
TR="$MEDIA/data/traces"
STT="$MEDIA/data/selftest"
VD="$MEDIA/data/unused"
STT="$HOME/.rf-openems"
EOF
export RF_OPENEMS_HOME="${RF_OPENEMS_HOME:-$HOME/.rf-openems}
echo "make_data: run judge/setup.sh first"
