#!/usr/bin/env bash
# Controlled load for demos: enough traffic to make the HPA scale and the
# Grafana graphs move, nothing more. Only needs bash and curl.
#
#   ./scripts/load-test.sh [seconds] [workers] [base-url] [host-header]
#   ./scripts/load-test.sh 180 40 http://$(minikube ip) kharcha.local
#   ./scripts/load-test.sh 60 4 http://localhost:3000          # Docker Compose
#
# Each worker loops over the API's read endpoints (the monthly summary does
# an aggregate query, so it costs real CPU) and adds an expense every 25th
# round. Added expenses are marked "load test" in the note so they are easy
# to find and delete afterwards.
set -euo pipefail

SECONDS_TO_RUN="${1:-120}"
WORKERS="${2:-20}"
BASE="${3:-http://localhost:3000}"
HOST="${4:-}"
MONTH="$(date +%Y-%m)"
TODAY="$(date +%Y-%m-%d)"

hdr=()
[ -n "$HOST" ] && hdr=(-H "Host: $HOST")

worker() {
  local id=$1 end=$((SECONDS + SECONDS_TO_RUN)) n=0 ok=0 bad=0
  local cats=(food transport utilities shopping health entertainment education other)
  while [ $SECONDS -lt $end ]; do
    n=$((n + 1))
    for path in "/api/expenses/summary?month=$MONTH" "/api/expenses?month=$MONTH" "/api/categories"; do
      code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "${hdr[@]}" "$BASE$path" || true)
      [ "$code" = 200 ] && ok=$((ok + 1)) || bad=$((bad + 1))
    done
    if [ $((n % 25)) -eq 0 ]; then
      c=${cats[$((RANDOM % ${#cats[@]}))]}
      curl -s -m 5 -o /dev/null "${hdr[@]}" -H 'Content-Type: application/json' -X POST "$BASE/api/expenses" \
        -d "{\"title\":\"Load test $id-$n\",\"amount\":\"$((RANDOM % 400 + 40)).00\",\"category\":\"$c\",\"spent_on\":\"$TODAY\",\"note\":\"load test\"}" || true
    fi
  done
  echo "$ok $bad"
}

echo "load: ${WORKERS} workers for ${SECONDS_TO_RUN}s against ${BASE}${HOST:+ (Host: $HOST)}"
start=$SECONDS
for i in $(seq 1 "$WORKERS"); do worker "$i" > "/tmp/kharcha-load-$i.txt" & done
wait
ok=0; bad=0
for i in $(seq 1 "$WORKERS"); do read -r o b < "/tmp/kharcha-load-$i.txt"; ok=$((ok + o)); bad=$((bad + b)); rm -f "/tmp/kharcha-load-$i.txt"; done
elapsed=$((SECONDS - start))
echo "done: $((ok + bad)) requests in ${elapsed}s (~$(( (ok + bad) / (elapsed > 0 ? elapsed : 1) )) req/s), ok=$ok failed=$bad"
