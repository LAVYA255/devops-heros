#!/usr/bin/env bash
# Creates the database password Secret, once.
#
#   ./kubernetes/create-db-secret.sh [namespace]
#
# Why a script and not a YAML file in git: a Secret manifest in the repo is a
# password in the repo, base64 or not (Session 12). Here the value is generated
# on the spot and only ever exists inside the cluster.
#
# Why "only if missing": Postgres stores the password when it first initialises
# its data volume. Regenerating the Secret on every deploy would leave the
# database with the old password and every backend pod unable to log in. This
# exact mistake is one of the troubleshooting scenarios in this project.
set -euo pipefail

NS="${1:-kharcha}"
NAME="kharcha-db"

if kubectl get secret "$NAME" -n "$NS" >/dev/null 2>&1; then
  echo "secret/$NAME already exists in $NS, leaving it alone"
  exit 0
fi

# Hex only: the password is embedded in a database URL, so it must not
# contain characters like @ : / that would break URL parsing.
PASSWORD="$(openssl rand -hex 24)"

kubectl create secret generic "$NAME" -n "$NS" \
  --from-literal=password="$PASSWORD" \
  --dry-run=client -o yaml \
  | kubectl label --local -f - app.kubernetes.io/part-of=kharcha -o yaml \
  | kubectl apply -f -

echo "secret/$NAME created in $NS (value not printed)"
