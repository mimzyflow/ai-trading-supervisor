#!/bin/sh
set -eu
PRIVATE=${ORACLE_PRIVATE_HOST:-ubuntu@100.88.175.94}
PUBLIC=${ORACLE_PUBLIC_HOST:-ubuntu@141.253.98.135}
KEY=${ORACLE_KEY:-"$HOME/.ssh/jarvis-oracle.key"}
for HOST in "$PRIVATE" "$PUBLIC"; do
  if ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 -o ConnectionAttempts=1 "$HOST" 'exit 0' >/dev/null 2>&1; then
    printf '%s\n' "$HOST"
    exit 0
  fi
done
echo 'Oracle inaccessible sur les accès SSH connus.' >&2
exit 1
