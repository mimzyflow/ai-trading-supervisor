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
  --exclude=.venv \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='user_data/*.sqlite*' \
  --exclude=user_data/logs \
  --exclude=user_data/runtime \
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
  mkdir -p user_data/reports
  sudo -n install -d -o jarvis -g jarvis -m 750 /var/lib/jarvis/runtime/trading
  command -v docker >/dev/null || {
    echo 'Docker is required on Oracle.' >&2
    exit 20
  }
  docker compose version >/dev/null || {
    echo 'Docker Compose plugin is required on Oracle.' >&2
    exit 21
  }
  docker compose config >/dev/null
  docker compose pull
  docker volume create ai-trading-freqtrade-runtime >/dev/null
  docker run --rm --user 0:0 --entrypoint /bin/sh \
    -v ai-trading-freqtrade-runtime:/runtime \
    freqtradeorg/freqtrade:stable \
    -c 'chown -R 1000:1000 /runtime && chmod 700 /runtime'
  docker compose up -d
  docker compose ps
"

echo "Dry-run deployment requested successfully."
