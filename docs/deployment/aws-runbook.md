# AWS deployment runbook — Phase 1 (single instance)

Deploys AVRoom to one EC2 instance running the whole stack via docker-compose:
FastAPI + the AI pipeline, Postgres, Mailpit, and the built React SPA served
from the same origin.

**Region: `eu-central-1` (Frankfurt).** Quotas, key pairs, security groups,
Elastic IPs and instances are all per-region — check the region selector in the
console's top-right before every step below.

Design rationale for the choices here lives in
[`docs/superpowers/specs/2026-08-29-aws-integration-design.md`](../superpowers/specs/2026-08-29-aws-integration-design.md).

## Which path: CPU or GPU?

Two ways to run the exact same stack, differing only in instance type and
whether `docker-compose.gpu.yml` is included. The pipeline runs on CPU today —
your own dev machine has no CUDA and it works, just slowly (minutes per
operation instead of seconds) — so **the GPU path is a speed upgrade, not a
requirement.**

| | CPU path | GPU path |
|---|---|---|
| Instance | `m7i.xlarge` (4 vCPU/16GB) | `g4dn.xlarge` (4 vCPU/16GB + T4) |
| Quota needed | none (default EC2 quota covers it) | G-family vCPU quota, often 24-48h to approve |
| Inference speed | minutes per operation | seconds |
| Cost | ~$0.20/hr ≈ ~$145/mo if left running | ~$0.53/hr ≈ ~$380/mo if left running |
| Compose command | `-f docker-compose.yml -f docker-compose.deploy.yml` | same, **+** `-f docker-compose.gpu.yml` |

Every step below is identical between the two paths except where marked
**[CPU]** / **[GPU]**. Moving from CPU to GPU later means relaunching the
instance (type can't change on an EC2 instance already running with different
hardware) and adding one `-f` flag — nothing else changes, since both paths
build and push to the same named volumes.

**Do not use a `t3.*`/`t2.*` (burstable) instance for either path.** Burstable
instances run on CPU credits; a multi-minute inference job exhausts them and
gets throttled mid-request. `m7i`/`c7i` are not burstable. 16GB RAM is the
real floor — SAM + both depth models + SD-inpaint together are memory-hungry
enough to OOM an 8GB box.

---

## 💸 Cost, up front

| State | Billed | Data |
|---|---|---|
| **Running** | full hourly rate | — |
| **Stopped** | EBS disk only, ~$12/mo for 150GB | kept |
| **Terminated** | nothing | **destroyed, unrecoverable** |

There is no free tier for either instance type at this size.

**Stop the instance whenever you are not actively demoing** (EC2 console →
select instance → *Instance state* → *Stop instance*). Starting it again takes
about a minute and everything is preserved — including the Elastic IP, so the
URL does not change.

Set a billing alarm before you start: *Billing and Cost Management* → *Budgets*
→ create a monthly cost budget with an email alert at, say, $40.

---

## Prerequisite: GPU vCPU quota — **[GPU] only, skip entirely for CPU**

New accounts get **0** vCPUs for G-family instances, and the launch fails with
`VcpuLimitExceeded` until that is raised. Approval takes minutes to a couple of
days, so it must be requested first.

*Service Quotas* → *Amazon EC2* → **Running On-Demand G and VT instances** →
*Request increase at account level* → **16**.

16 covers `g4dn.xlarge` (4 vCPU, this deployment) plus `g5.2xlarge` (8 vCPU,
the Phase 2 Hunyuan3D box) running simultaneously. A quota is a ceiling, not a
reservation — raising it costs nothing.

Do not continue with the GPU path until the *Applied account-level quota
value* shows ≥ 4. The CPU path needs no quota action at all — standard
instance families ship with a non-zero default.

---

## 1. Launch the instance

EC2 console → **Launch instance**.

| Field | Value | Why |
|---|---|---|
| Name | `avroom` | |
| AMI | **[GPU]** Deep Learning OSS Nvidia Driver AMI (Ubuntu 22.04) — search "Deep Learning" in the AMI catalog. **[CPU]** plain **Ubuntu 22.04 LTS**. | The Deep Learning AMI ships NVIDIA drivers, Docker, and the NVIDIA Container Toolkit preinstalled — the most error-prone part of GPU setup, done for you. It works on a CPU box too (the driver just sits unused) but is a larger image for no benefit, so plain Ubuntu is cleaner for the CPU path. |
| Instance type | **[GPU]** `g4dn.xlarge`. **[CPU]** `m7i.xlarge`. | GPU: 1× NVIDIA T4, 16GB VRAM. CPU: no accelerator, same 4 vCPU/16GB shape so the app's memory needs are met either way. |
| Key pair | **Create new**, type RSA, format `.pem`, name `avroom-key` | Downloads once. **You cannot download it again** — lose it and you lose SSH access to the box. |
| Network → Firewall | **Create security group** (settings in step 2) | |
| Storage | **150 GiB, gp3** | The default 8GB fills instantly: image ≈ 8-15GB + model weights ≈ 10GB + uploads. |

Then **Launch instance**.

Plain Ubuntu (CPU path) needs Docker installed by hand once connected:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# log out and back in for the group change to take effect
```

## 2. Security group

Exactly two inbound rules. Everything else stays closed.

| Type | Port | Source | Why |
|---|---|---|---|
| SSH | 22 | **My IP** | Admin access, restricted to your address. |
| HTTP | 80 | `0.0.0.0/0` | The app itself, public. |

**Do not add a Postgres rule.** The database is reachable only from inside the
Docker network; nothing outside the box needs it. (The base compose file
publishes 5433 on the host, but with no security-group rule for it that port is
unreachable from the internet.)

## 3. Elastic IP

An instance's default public IP **changes every time you stop and start it**.
An Elastic IP does not, so the demo URL stays stable.

EC2 console → *Network & Security* → **Elastic IPs** → *Allocate Elastic IP
address* → *Allocate* → select it → *Actions* → *Associate Elastic IP address*
→ pick the `avroom` instance → *Associate*.

Write the address down; it is referred to as `<ELASTIC_IP>` below.

> An Elastic IP is free while associated with a *running* instance, and billed
> at ~$0.005/hr (~$3.50/mo) while the instance is stopped. That is the price of
> keeping the address stable.

## 4. Connect

From PowerShell on Windows, in the folder holding `avroom-key.pem`:

```powershell
# SSH refuses to use a key that other Windows accounts can read. This makes the
# file readable only by you.
icacls avroom-key.pem /inheritance:r
icacls avroom-key.pem /grant:r "$($env:USERNAME):(R)"

ssh -i avroom-key.pem ubuntu@<ELASTIC_IP>
```

Confirm the box is ready before going further:

```bash
docker --version    # must print a version
nvidia-smi          # [GPU only] must print a table showing a Tesla T4
```

## 5. Clone and configure

```bash
git clone https://github.com/1mache/avroom.git
cd avroom
git checkout aws-integration   # omit once this is merged to main
```

The deployment files live on the `aws-integration` branch until it is merged,
and `git clone` checks out `main` by default — skipping this line gets you a
tree with no `fastApi-app/Dockerfile`, and a confusing build failure.

Whatever you deploy must be **pushed** first: the box builds from the GitHub
remote, not from your laptop. Check with `git status -sb` locally — it must not
say `ahead N`.

`.env` is gitignored, so it is not in the clone — create it by hand:

```bash
nano fastApi-app/.env
```

Paste, substituting your two real secrets:

```ini
# --- Secrets (copy the values from your local fastApi-app/.env) ---
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-3.5-flash-lite

# --- 3D reconstruction: still the public HuggingFace Space (Phase 1) ---
HUNYUAN3D_SPACE_ID=tencent/Hunyuan3D-2.1
TRELLIS_SPACE_ID=microsoft/TRELLIS.2

# --- Inference concurrency ---
# 0 = inline mode: one process-wide GPU lock, requests serialized. Correct for
# a single 16GB T4 - two workers would each load their own copy of every model
# and exhaust VRAM. Raise only on a bigger card.
INFERENCE_WORKERS=0
INFERENCE_JOB_TIMEOUT=true
```

Notes on what is deliberately **absent**:

- `DATABASE_URL` — `docker-compose.yml` sets it to the internal `db` service,
  which overrides anything in `.env`.
- `CORS_ALLOW_ORIGINS` — not needed. The SPA is built with
  `VITE_API_BASE_URL=""` and served by FastAPI itself, so every request is
  same-origin and never triggers CORS.
- `STORAGE_BACKEND` / `AUTH_MODE` — the defaults (`local`, `single_user`) are
  what Phase 1 wants.
- `SAM_AUTO_DOWNLOAD`, `LOG_DIR`, `DEBUG_IMAGE_SAVE` — set in
  `docker-compose.deploy.yml`, not here.

Save with `Ctrl+O`, `Enter`, `Ctrl+X`.

## 6. Build and start

```bash
# CPU path
docker compose -f docker-compose.yml -f docker-compose.deploy.yml \
  --profile full up -d --build

# GPU path (same, plus the GPU overlay)
docker compose -f docker-compose.yml -f docker-compose.deploy.yml \
  -f docker-compose.gpu.yml --profile full up -d --build
```

First build takes **15–30 minutes** (torch alone is ~3GB). Watch it with:

```bash
docker compose logs -f api
```

The entrypoint runs `alembic upgrade head` before starting uvicorn, so the
schema is created automatically — no manual migration step.

## 7. Verify

**[GPU only] GPU is actually in use** — the single most important check on
this path, because failure here is silent and just makes everything ~50×
slower:

```bash
docker compose exec api python -c "import torch; print(torch.cuda.is_available())"
```

Must print `True`. If it prints `False`, see Troubleshooting. **[CPU]** this
prints `False` correctly on the CPU path — that is not a problem, skip this
check.

**The app responds:**

```bash
curl -I http://localhost
```

**End to end:** open `http://<ELASTIC_IP>` in your browser and run a full
cycle — upload a photo, segment an object, inpaint it, rotate it.

The **first** segment is slow regardless of path: the container is
downloading ~10GB of model weights into the `hf-cache` volume. Later requests
reuse them. **[CPU]** every request stays on the order of minutes, not
seconds — that is the expected cost of this path, not a bug.

---

## Day-to-day

```bash
# logs
docker compose logs -f api

# restart after changing .env (CPU path; add -f docker-compose.gpu.yml for GPU)
docker compose -f docker-compose.yml -f docker-compose.deploy.yml --profile full up -d

# deploy new code (CPU path; add -f docker-compose.gpu.yml for GPU)
git pull
docker compose -f docker-compose.yml -f docker-compose.deploy.yml \
  --profile full up -d --build
```

**Moving from the CPU path to the GPU path once the quota clears:** the app's
data doesn't move because it never lived on the CPU instance — Postgres and
the blobs are in named Docker volumes, and volumes live with the daemon, not
transparently across instances. Practically: launch the new `g4dn.xlarge` per
step 1, then either restore from an EBS snapshot of the old instance's volumes
(if you took one) or just re-run steps 4-6 fresh and re-upload — Phase 1 has
no cross-instance backup by design (see "What survives what" below). Then
terminate the CPU instance once the GPU one is verified.

**Stopping for the day:** just stop the instance from the EC2 console. Both
compose services are `restart: unless-stopped`, so they come back on their own
when you start it again.

### What survives what

| Action | Postgres | Blobs (cutouts/GLBs) | Model weights |
|---|---|---|---|
| Instance stop/start | ✅ | ✅ | ✅ |
| `docker compose down` | ✅ | ✅ | ✅ |
| `docker compose down -v` | ❌ | ❌ | ❌ |
| Instance **terminate** | ❌ | ❌ | ❌ |

Everything durable lives in named volumes (`avroom-db`, `avroom-blobs`,
`hf-cache`, `sam-checkpoints`) on the instance's EBS disk. **There are no
backups in Phase 1** — this is the accepted trade for skipping RDS and S3. Do
not put anything here you would be upset to lose, and take a manual EBS
snapshot before demo day if the session data matters.

---

## Troubleshooting

**`torch.cuda.is_available()` is `False`** — on the CPU path, this is correct
and expected; skip it. On the GPU path, the container is not getting the GPU.
Check `nvidia-smi` works on the host; if it does, the NVIDIA Container Toolkit
is the issue. Test it directly:
`docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`.
Also confirm you passed **all three** `-f` files — dropping
`docker-compose.gpu.yml` silently starts a CPU-only container, which behaves
identically to the CPU path except you're paying GPU-instance prices for it.

**`VcpuLimitExceeded` at launch** — GPU path only. The quota request from the
prerequisite section has not been approved yet, or was approved in a
different region. Not applicable to the CPU path.

**Build killed / out of memory** — `g4dn.xlarge` has 16GB RAM and the torch
install is memory-hungry. Retry; the layer cache means it resumes rather than
restarting.

**Disk full** — `df -h`. Old images accumulate on rebuilds: `docker image
prune -a` reclaims them. Never `docker system prune --volumes`, which deletes
your data.

**Browser can't reach `http://<ELASTIC_IP>`** — check the security group has
port 80 open to `0.0.0.0/0`, and that you typed `http://`, not `https://`.
There is no TLS in Phase 1; some browsers silently upgrade and then fail.

**`docker compose exec api ...` says no such service** — the `api` service is
behind a profile; include `--profile full`.

**3D generation fails with a `torchmcubes` message** — expected, not a broken
install. The TripoSR *fallback* backend is intentionally unavailable in this
image (`torchmcubes` needs a full CUDA toolkit to compile, which the slim base
does not carry). It only surfaces when the **primary** Hunyuan3D Space backend
has already failed — so the real problem is the Space being down or
rate-limited, not this. All TripoSR code is retained; restore the fallback with
`pip install "torchmcubes @ git+https://github.com/tatsy/torchmcubes.git"` if you
ever switch to a CUDA-devel base image.

---

## Not in Phase 1

Deferred deliberately, each with the trigger for revisiting it:

- **HTTPS + domain** — raw IP over HTTP for now. Adding it later touches nginx/
  certbot and env config, not application code.
- **RDS** — revisit before the app holds data worth backups.
- **S3 blob storage** — `STORAGE_BACKEND=s3` already exists in `settings.py`,
  unused. Revisit when the instance needs to be disposable.
- **Self-hosted Hunyuan3D** — still calling the public HF Space, which is flaky
  and rate-limited. Phase 2: a second `g5.2xlarge`, up only around demo day.
- **`AUTH_MODE=jwt`** — irrelevant while the app is single-user.
- **The GPU path itself**, until the vCPU quota clears — the CPU path is the
  interim, not a dead end; see "Which path: CPU or GPU?" above.
