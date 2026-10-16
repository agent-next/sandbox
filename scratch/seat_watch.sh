#!/bin/sh
# Patient GPU-seat watcher: tries one create every 3 min; on 201 writes
# /tmp/seat_ready.json and DELETES the lease it created (verified 404),
# because run.py must create its own. On 409/503 keeps waiting.
# Logs every reply for PRODUCT-FRICTION.md.
LOG=/tmp/seat_watch.log
: > "$LOG"
i=0
while [ $i -lt 200 ]; do
  i=$((i+1))
  out=$(curl -sS -m 220 -X POST "https://api.sbx.agent-next.com/sandboxes" \
    -H "X-API-Key: $GPU_API_KEY" -H "Content-Type: application/json" \
    -d '{"accel":{"vram_gb":6,"template":"omniverse","reserve":"exec"}}' \
    -w '|HTTP:%{http_code}|t=%{time_total}' 2>&1 | tail -1)
  echo "$(date -u +%FT%TZ) attempt=$i $out" >> "$LOG"
  code=$(printf '%s' "$out" | sed -n 's/.*|HTTP:\([0-9]*\)|.*/\1/p')
  if [ "$code" = "201" ]; then
    sid=$(printf '%s' "$out" | sed -n 's/.*"sandboxID":"\([^"]*\)".*/\1/p')
    echo "$out" > /tmp/seat_ready.json
    # the watcher must not hold the seat: delete and verify
    curl -sS -m 60 -X DELETE "https://api.sbx.agent-next.com/sandboxes/$sid" \
      -H "X-API-Key: $GPU_API_KEY" >> "$LOG" 2>&1
    n=0
    while [ $n -lt 20 ]; do
      n=$((n+1))
      st=$(curl -sS -m 60 -o /dev/null -w '%{http_code}' \
        "https://api.sbx.agent-next.com/sandboxes/$sid" \
        -H "X-API-Key: $GPU_API_KEY")
      [ "$st" = "404" ] && break
      sleep 3
    done
    echo "$(date -u +%FT%TZ) released $sid (GET $st)" >> "$LOG"
    exit 0
  fi
  sleep 170
done
exit 1
