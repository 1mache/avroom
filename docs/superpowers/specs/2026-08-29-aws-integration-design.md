# AWS Integration — Phase 1 (single-instance demo deploy)

## Context

AVRoom currently runs local-only: FastAPI (fastApi-app) + AI pipeline
(TestModules) + Postgres via docker-compose + React frontend, all on the
developer's machine. The user now has an AWS account and wants the app
reachable on the internet, at demo/portfolio scale (not production traffic).

The repo already has partial cloud prep that was started but never finished:

- `settings.py::get_storage_backend()` — `STORAGE_BACKEND=local|s3` switch for
  blob storage (cutouts, GLBs, novel-view caches).
- `settings.py::get_notify_backend()` — auto-picks SES when storage is `s3`,
  else SMTP/Mailpit.
- `settings.py` has an `AUTH_MODE=single_user|jwt` switch; `jwt` is not wired
  up (schema supports it, route-level auth resolution does not).
- `fastApi-app/.env.example` has an "AWS deployment prep" section referencing
  `docs/deployment/aws-runbook.md`, which does not exist.
- No `fastApi-app/Dockerfile` exists yet, despite `docker-compose.yml`'s `api`
  service already referencing one.
- 3D reconstruction (`Reconstruction3DFacade` /
  `Hunyuan3D2ReconstructionStrategy`) already calls a public Hugging Face
  Space (`es3d-fi/hunyuan3d-2-1`) rather than local GPU — this is independent
  of the main object-removal pipeline's GPU needs.

## Goal

Get the app running on AWS, reachable over the internet, with the smallest
amount of new infrastructure and AWS-specific knowledge required — a single
instance running everything, matching the user's current beginner familiarity
with AWS. Explicitly deferred to a later phase: managed DB (RDS), S3 blob
storage, self-hosted 3D generation, domain name + HTTPS, multi-instance
scaling.

## Decisions made (with rejected alternatives)

### Compute: single EC2 GPU instance, not ECS/Fargate

**Decision:** One EC2 instance, type `g4dn.xlarge` (1x NVIDIA T4, 16GB VRAM,
~$0.53/hr on-demand). Ubuntu + Docker + `nvidia-container-toolkit`. The
existing `docker-compose.yml` runs on this box largely as-is.

**Why not ECS+Fargate:** Fargate does not support GPU compute at all. The AI
pipeline (SAM, depth models, LaMa, Stable Diffusion) requires CUDA — this
alone rules Fargate out for the inference workload.

**Why not EC2-backed ECS:** ECS task/service orchestration exists to manage
*multiple* instances/tasks. At one-instance demo scale it adds AWS concepts
(task definitions, services, clusters) with no operational benefit over
plain EC2 + docker-compose. Revisit only if/when horizontal scaling is
actually needed.

### Database: Postgres container on the same EC2 box, not RDS

**Decision:** Reuse the existing `db` service in `docker-compose.yml`
(Postgres 16 container) on the same instance. No new AWS service.

**Why not RDS:** RDS is the "right" long-term answer (managed backups,
survives instance replacement) but requires learning VPC subnet groups,
security groups for a second resource, and adds a recurring cost — more new
AWS surface than warranted for a demo. Accepted downside: no automated
backups; DB dies if the instance dies or is intentionally replaced.

**Future trigger to revisit:** move to RDS before this app holds any data the
user isn't willing to lose (i.e. before real users, not before submission).

### Blob storage: local disk on the instance, not S3

**Decision:** `STORAGE_BACKEND=local` (already the default — no code change).
Cutouts, GLBs, and novel-view caches live on the EC2 instance's disk.

**Why not S3:** The `s3` backend switch already exists in `settings.py` but
using it means creating a bucket, IAM permissions, and testing a second code
path — deferred until either the instance needs to be disposable/replaceable
or storage needs exceed one instance's disk.

### 3D reconstruction: keep the HF Space, self-host later as a distinct phase

**Decision:** No change — keep calling the public Hugging Face Space via
`Hunyuan3D2ReconstructionStrategy` (already the default primary strategy,
with `TriposrReconstructionStrategy` as the existing local-PyTorch fallback).

**Why not self-host now:** Hunyuan3D-2.1 needs significantly more VRAM
(24GB+) than the `g4dn.xlarge` chosen for the main pipeline (16GB), so it
cannot share that instance. Self-hosting would mean a second, bigger, more
expensive GPU instance running continuously.

**Known problem with the current default:** the free HF Space is flaky
(intermittent unavailability) and rate-limited (reportedly ~1 generation/day)
— a real constraint before a submission/demo day where many rooms need to be
pre-generated/cached.

**Planned phase 2 (not part of this spec's implementation):** stand up a
second, larger GPU instance (e.g. `g5.2xlarge` or bigger, 24GB+ VRAM) running
self-hosted Hunyuan3D-2.1 weights as a new strategy, used only in a
time-boxed window around submission day, then torn down to stop the cost.
The existing `Reconstruction3DFacade` strategy pattern already makes this a
new strategy class, not a rewrite — `Reconstruction3DFacade` already has a
primary/fallback structure to build on.

### Networking: raw public IP, HTTP, no domain yet

**Decision:** One Elastic IP attached to the instance (so the address is
stable across reboots). Security group open on port 22 (SSH, restricted to
the user's IP) and port 80 (HTTP, open). No domain name, no TLS/HTTPS.
`CORS_ALLOW_ORIGINS` and the frontend's `VITE_API_BASE_URL` point at
`http://<elastic-ip>`.

**Why not a domain + HTTPS now:** no domain owned yet; adding DNS + certbot/
Let's Encrypt is a separable step that doesn't block getting the app
reachable. Can be layered on later without touching application code (only
env config and an nginx cert config change).

## Architecture

```
                         Internet
                            |
                     Elastic IP : 80
                            |
                 ┌──────────────────────┐
                 │   EC2 g4dn.xlarge     │
                 │  (Ubuntu + Docker +   │
                 │  nvidia-container-    │
                 │  toolkit)             │
                 │                       │
                 │  docker-compose:      │
                 │   - nginx  (new)      │  → serves React build,
                 │                       │    reverse-proxies /api
                 │   - api    (fastapi,  │  → GPU pipeline, needs
                 │             new       │    new CUDA Dockerfile
                 │             Dockerfile)│
                 │   - db     (postgres, │  → existing service,
                 │             existing) │    unchanged
                 │   - mailpit(existing) │  → unchanged, local
                 │                       │    notification transport
                 └──────────────────────┘
                            |
                    (outbound only)
                            |
                 Hugging Face Space
              (Hunyuan3D-2.1, unchanged)
```

## Implementation components

1. **`fastApi-app/Dockerfile`** (new) — CUDA-capable base image (matching
   the pinned `torch==2.10.0`/CUDA build already in `requirements.txt`),
   installs `-e ./TestModules` and the rest of `requirements.txt`, runs
   uvicorn. This is the piece the `docker-compose.yml` `api` service already
   references but that has never existed.
2. **`docker-compose.yml`** — add an `nginx` service (or fold static serving
   into the existing `api` service if simpler) that serves the React
   production build at `/` and reverse-proxies backend route prefixes
   (`/images`, `/3d`, `/jobs`, `/debug` — confirmed against
   `react-front/src/api/images.ts`, which has no `/api` prefix, just
   `${VITE_API_BASE_URL}/images/...` etc.) to the `api` container.
   `VITE_API_BASE_URL` at build time becomes `http://<elastic-ip>` (same
   origin as the served frontend, since nginx proxies both from port 80).
3. **`.env` on the instance** — `STORAGE_BACKEND=local`,
   `AUTH_MODE=single_user`, `LOG_DIR=disabled` (stdout only, no rotating file
   handler in a container), `DEBUG_IMAGE_SAVE=false`,
   `CORS_ALLOW_ORIGINS=http://<elastic-ip>`. `DATABASE_URL` stays the
   docker-compose default (`db` service hostname, not `localhost`).
4. **Manual AWS console steps** (not code): launch the EC2 instance, allocate
   + associate the Elastic IP, configure the security group, generate/attach
   an SSH key pair. Good fit for the `wizard` skill at implementation time —
   these are steps only the user can click through in the AWS console, not
   something to script blind.

## Testing / verification

- `docker compose --profile full up -d` on the instance comes up clean;
  `alembic upgrade head` runs against the containerized Postgres.
- End-to-end smoke test from a browser against `http://<elastic-ip>`: upload
  a photo, segment, inpaint, rotate an object — the full existing local
  workflow, now over the network.
- Confirm GPU is actually visible inside the `api` container
  (`nvidia-smi` inside the container, or a quick `torch.cuda.is_available()`
  check) — the most likely failure point given `nvidia-container-toolkit` is
  new setup.

## Explicitly deferred (future phases, not this spec)

- RDS for Postgres (managed backups, survives instance replacement).
- S3 for blob storage (`STORAGE_BACKEND=s3`, already switch-ready).
- Domain name + HTTPS (Let's Encrypt/certbot via nginx).
- Self-hosted Hunyuan3D-2.1 on a second, larger GPU instance for
  submission-day volume (see "3D reconstruction" decision above).
- `AUTH_MODE=jwt` (multi-user auth) — schema-ready, route-level work not
  started; irrelevant at single-user demo scale.
- Any horizontal scaling / ECS / load balancing.
