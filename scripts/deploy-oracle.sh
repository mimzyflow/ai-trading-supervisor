#!/bin/sh
set -eu

HOST=${ORACLE_HOST:-ubuntu@100.88.175.94}
KEY=${ORACLE_KEY:-"$HOME/.ssh/jarvis-oracle.key"}
REMOTE_DIR=${REMOTE_DIR:-/home/ubuntu/ai-trading-supervisor}
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
ARCHIVE=$(mktemp -t ai-trading-supervisor.XXXXXX.tar.gz)
trap 'rm -f "$ARCHIVE"' EXIT INT TERM

cd "$ROOT"
tar -czf "$ARCHIVE" \
  --exclude=.git \
  --exclude=.env \
  --exclude='user_data/*.sqlite*' \
  --exclude=user_data/logs \
  --exclude=user_data/reports \
  .

echo "Uploading project to Oracle..."
ssh -i "$KEY" "$HOST" "mkdir -p '$REMOTE_DIR'"
scp -i "$KEY" "$ARCHIVE" "$HOST:$REMOTE_DIR/release.tar.gz"
ssh -i "$KEY" "$HOST" "
  set -eu
  cd '$REMOTE_DIR'
  tar -xzf release.tar.gz
  rm -f release.tar.gz
  mkdir -p user_data/logs user_data/reports
  command -v docker >/dev/null || {
    echo 'Docker is required on Oracle.' >&2
    exit 20
  }
  docker compose version >/dev/null || {
    echo 'Docker Compose plugin is required on Oracle.' >&2
    exit 21
  }
  docker compose pull
  docker compose up -d
  docker compose ps
"

echo "Dry-run deployment requested successfully."
