#!/usr/bin/env bash
# Caps the ingress-nginx controller at a fixed number of worker processes.
#
#   ./kubernetes/tune-ingress-nginx.sh [workers]
#
# Why this exists: by default nginx starts one worker per CPU it can see. On my
# laptop the Minikube node sees 24 CPUs, so nginx opened 24 reuseport sockets on
# port 80. The container's pids cgroup limit is 1400, and during the reload my
# helm install triggered, 7 of those 24 workers failed pthread_create() with
# EAGAIN and were never respawned. Their sockets stayed open with nobody calling
# accept(), so the kernel kept handing about 29% of new connections to a dead
# socket and those requests hung until the client gave up.
#
# A reload does not clean this up (the orphaned sockets belong to the master),
# so the script restarts the controller after patching its ConfigMap.
# Full write-up: troubleshooting/README.md, "Ingress hangs on 1 in 4 requests".
set -euo pipefail

WORKERS="${1:-4}"
NS=ingress-nginx
CM=ingress-nginx-controller
DEPLOY=ingress-nginx-controller

current=$(kubectl get configmap "$CM" -n "$NS" -o jsonpath='{.data.worker-processes}' 2>/dev/null || true)
if [ "$current" = "$WORKERS" ]; then
  echo "worker-processes is already $WORKERS, nothing to do"
  exit 0
fi

kubectl patch configmap "$CM" -n "$NS" --type merge \
  -p "{\"data\":{\"worker-processes\":\"$WORKERS\"}}"
kubectl rollout restart deployment/"$DEPLOY" -n "$NS"
kubectl rollout status deployment/"$DEPLOY" -n "$NS" --timeout=180s
echo "ingress-nginx now runs $WORKERS workers"
