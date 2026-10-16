#!/usr/bin/env bash
# Makes the Postgres user's password match the kharcha-db Secret again.
#
#   ./troubleshooting/sync-db-password.sh [namespace]
#
# When you need it: someone re-created the Secret (or ran create-db-secret.sh
# after deleting it), so it now holds a new password, but Postgres still has
# the old one from when its volume was first initialised. New backend pods
# then fail with "password authentication failed for user kharcha".
#
# The password travels Secret -> stdin -> psql variable. It is never printed,
# never put on a command line (where `ps` would show it) and never written to
# a file.
set -euo pipefail

NS="${1:-kharcha}"
POD="kharcha-postgres-0"

kubectl get secret kharcha-db -n "$NS" -o jsonpath='{.data.password}' | base64 -d \
  | kubectl exec -i -n "$NS" "$POD" -c postgres -- sh -c '
      read -r pw
      # psql only interpolates :'"'"'var'"'"' in scripts read from stdin, not in -c.
      printf "%s\n" "ALTER USER kharcha PASSWORD :'"'"'pw'"'"';" \
        | psql -v ON_ERROR_STOP=1 -q -U kharcha -d kharcha -v pw="$pw"
    '
echo "postgres password for user kharcha now matches secret/kharcha-db in $NS"
