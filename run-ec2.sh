#!/usr/bin/env bash
# Start the full AVRoom stack on a deployed EC2 box, then follow the logs.
#
# The Linux counterpart to run.bat: that one starts infra and runs the API on
# the host for development; this one runs everything in containers.
#
#   ./run-ec2.sh            # CPU instance
#   GPU=1 ./run-ec2.sh      # instance with an NVIDIA GPU
#
# Ctrl+C stops following the logs. It does NOT stop the containers - they are
# `restart: unless-stopped` and are meant to keep running. To actually stop:
#   ./run-ec2.sh down
set -euo pipefail
cd "$(dirname "$0")"

# --profile full is required or the `api` service does not exist.
# docker-compose.deploy.yml adds port 80, restarts, and the named volumes that
# must outlive a rebuild; docker-compose.gpu.yml adds only the GPU reservation,
# which fails the container outright on a host with no NVIDIA runtime.
FILES="-f docker-compose.yml -f docker-compose.deploy.yml"
[ "${GPU:-0}" = "1" ] && FILES="$FILES -f docker-compose.gpu.yml"
COMPOSE="docker compose $FILES --profile full"

if [ ! -f fastApi-app/.env ]; then
  echo "[run-ec2] ERROR: fastApi-app/.env is missing."
  echo "          It is gitignored, so it is not in the clone - create it by"
  echo "          hand (see docs/deployment/aws-runbook.md step 5). compose"
  echo "          refuses to start the whole stack without it."
  exit 1
fi

# `down`/`ps`/`logs`/anything else: pass straight through.
if [ $# -gt 0 ]; then
  exec $COMPOSE "$@"
fi

echo "[run-ec2] Building and starting (first build takes 40-60 min on 2 vCPU)..."
$COMPOSE up -d --build

echo "[run-ec2] Up. Following logs - Ctrl+C detaches, containers keep running."
exec $COMPOSE logs -f
