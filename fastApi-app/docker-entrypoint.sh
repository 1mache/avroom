#!/usr/bin/env sh
# Container entrypoint: bring the schema up to date, then serve.
#
# Deliberately does NOT run scripts/migrate_local_sidecars_to_db.py (which
# run.bat does locally) - that imports legacy JSON sidecars from a developer
# machine and is meaningless on a fresh deployment.
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Starting uvicorn on 0.0.0.0:8000..."
# --host 0.0.0.0 (not the 127.0.0.1 default) so the port is reachable from
# outside the container. No --reload: that is a dev-only file watcher.
exec uvicorn main:app --host 0.0.0.0 --port 8000
