# AVRoom API image: FastAPI + the avroom_object_removal AI pipeline, and the
# built React SPA served from the same origin.
#
# Build context is the REPO ROOT, not fastApi-app/ (requirements.txt and
# TestModules/ live there). docker-compose.yml's `api` service already sets
# `context: .` accordingly.

# ---------------------------------------------------------------------------
# Stage 1 - build the React SPA to static files.
#
# Vite is a build tool, not a runtime: it emits plain html/js/css into dist/
# and then exits. Node does not exist in the final image.
#
# VITE_API_BASE_URL="" makes react-front/src/api/images.ts emit *relative*
# fetch URLs ("/images/upload" rather than "http://127.0.0.1:8000/images/
# upload"). Since stage 2 serves this SPA from the same origin as the API,
# relative URLs mean no CORS at all and no server IP baked into the bundle.
# Note images.ts uses `??`, so an empty string correctly beats the localhost
# fallback (empty string is not nullish).
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend

WORKDIR /build
COPY react-front/package.json react-front/package-lock.json ./
RUN npm ci

COPY react-front/ ./
ENV VITE_API_BASE_URL=""
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 - Python runtime.
#
# Base is plain python:3.11-slim, NOT an nvidia/cuda image: the PyPI torch
# wheels bundle their own CUDA runtime as nvidia-*-cu12 pip dependencies, so
# only the host's NVIDIA *driver* matters, and that is injected by the NVIDIA
# Container Toolkit at run time (`--gpus all`). This keeps the image far
# smaller and removes any CUDA-version matching guesswork.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # pyrender needs an offscreen OpenGL context. OSMesa is pure software
    # rendering: unlike EGL it needs no NVIDIA_DRIVER_CAPABILITIES=graphics
    # negotiation with the container toolkit, and it behaves identically on a
    # CPU-only laptop and on the GPU box - so the local smoke test exercises
    # the real code path. Renders are only 512x512
    # (mesh_render_novel_view_strategy.py:36), so software rendering is fast
    # enough.
    # ponytail: OSMesa (CPU) for the novel-view rasterizer; switch to
    # PYOPENGL_PLATFORM=egl + NVIDIA_DRIVER_CAPABILITIES=all if 512px renders
    # ever show up as a bottleneck.
    PYOPENGL_PLATFORM=osmesa \
    # HF weights land in a named volume (see docker-compose.deploy.yml) so a
    # rebuild does not re-download ~10GB.
    HF_HOME=/root/.cache/huggingface

# System libraries, each for a specific dependency:
#   git             - requirements.txt has `geocalib @ git+...` and TestModules
#                     has `torchmcubes @ git+...`
#   build-essential - torchmcubes compiles a C++ extension at install time
#   libgl1, libglib2.0-0 - opencv-python
#   libosmesa6      - pyrender/PyOpenGL offscreen rendering (see PYOPENGL_PLATFORM)
#   libpq5          - psycopg[binary] runtime
#   curl            - container healthcheck
#   xvfb            - pyrender imports pyglet unconditionally (pyrender/__init__.py
#                     pulls in its Viewer class), and pyglet's Xlib backend probes
#                     for a real X display at *import* time, before OSMesa/EGL is
#                     ever chosen for the actual render. A host with literally no
#                     X server (any headless Linux box, unlike a dev machine with
#                     a real display) makes that probe crash with
#                     "'NoneType' object has no attribute 'XRenderFindVisualFormat'".
#                     A virtual framebuffer satisfies the probe; OSMesa still does
#                     the real off-screen rendering. Started directly by
#                     docker-entrypoint.sh, not via xvfb-run (no xauth needed).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        libosmesa6 \
        libpq5 \
        curl \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install torch first, on its own layer. torchmcubes' setup.py imports torch
# at build time, so torch must already be present; doing it here also means
# the ~3GB torch layer is cached and not re-downloaded when only application
# code changes.
RUN pip install --no-cache-dir \
        torch==2.10.0 \
        torchvision==0.25.0 \
        torchaudio==2.10.0

# Dependency layer: copy only what pip reads, so editing application code does
# not invalidate the (very slow) dependency install.
COPY requirements.txt ./
COPY TestModules/pyproject.toml ./TestModules/
COPY TestModules/src/ ./TestModules/src/
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY fastApi-app/ ./fastApi-app/

# The built SPA. main.py mounts this directory with StaticFiles when present.
COPY --from=frontend /build/dist/ ./react-front/dist/

WORKDIR /app/fastApi-app

COPY fastApi-app/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

# /healthz, not / - the latter serves the SPA's index.html here, which would
# still 200 even if the API itself were broken.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
