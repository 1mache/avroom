#!/usr/bin/env sh
# Container entrypoint: bring the schema up to date, then serve.
#
# Deliberately does NOT run scripts/migrate_local_sidecars_to_db.py (which
# run.bat does locally) - that imports legacy JSON sidecars from a developer
# machine and is meaningless on a fresh deployment.
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

# pyrender imports pyglet unconditionally (pyrender/__init__.py pulls in its
# Viewer class), and pyglet's Xlib backend probes for a real X server at
# *import* time regardless of PYOPENGL_PLATFORM=osmesa (which only governs
# the actual off-screen render, done later). A truly display-less host makes
# that probe crash outright ("XRenderFindVisualFormat" on a null screen). A
# 1x1 virtual framebuffer satisfies the probe; OSMesa still does the real
# render. Started directly (not via xvfb-run, whose wrapper script can hang
# indefinitely with no error if Xvfb is slow to come up) so we control the wait.
echo "[entrypoint] Starting virtual X display on :99..."
Xvfb :99 -screen 0 1x1x24 -nolisten tcp &
export DISPLAY=:99
for _ in $(seq 1 50); do
    [ -e /tmp/.X11-unix/X99 ] && break
    sleep 0.1
done

echo "[entrypoint] Starting uvicorn on 0.0.0.0:8000..."
# --host 0.0.0.0 (not the 127.0.0.1 default) so the port is reachable from
# outside the container. No --reload: that is a dev-only file watcher.
exec uvicorn main:app --host 0.0.0.0 --port 8000
