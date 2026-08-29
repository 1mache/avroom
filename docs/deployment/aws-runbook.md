# AWS deployment runbook — Phase 1 (single GPU instance)

Deploys AVRoom to one EC2 GPU instance running the whole stack via
docker-compose: FastAPI + the AI pipeline, Postgres, Mailpit, and the built
React SPA served from the same origin.

**Region: `eu-central-1` (Frankfurt).** Quotas, key pairs, security groups,
Elastic IPs and instances are all per-region — check the region selector in the
console's top-right before every step below.

Design rationale for the choices here lives in
[`docs/superpowers/specs/2026-08-29-aws-integration-design.md`](../superpowers/specs/2026-08-29-aws-integration-design.md).

---

## 💸 Cost, up front

`g4dn.xlarge` is roughly **$0.53/hour ≈ $380/month** if left running. There is
no free tier for GPU instances.

| State | Billed | Data |
|---|---|---|
| **Running** | full hourly rate | — |
| **Stopped** | EBS disk only, ~$12/mo for 150GB | kept |
| **Terminated** | nothing | **destroyed, unrecoverable** |

**Stop the instance whenever you are not actively demoing** (EC2 console →
select instance → *Instance state* → *Stop instance*). Starting it again takes
about a minute and everything is preserved — including the Elastic IP, so the
URL does not change.

Set a billing alarm before you start: *Billing and Cost Management* → *Budgets*
→ create a monthly cost budget with an email alert at, say, $40.

---

## Prerequisite: GPU vCPU quota

New accounts get **0** vCPUs for G-family instances, and the launch fails with
`VcpuLimitExceeded` until that is raised. Approval takes minutes to a couple of
days, so it must be requested first.

*Service Quotas* → *Amazon EC2* → **Running On-Demand G and VT instances** →
*Request increase at account level* → **16**.

16 covers `g4dn.xlarge` (4 vCPU, this deployment) plus `g5.2xlarge` (8 vCPU,
the Phase 2 Hunyuan3D box) running simultaneously. A quota is a ceiling, not a
reservation — raising it costs nothing.

Do not continue until the *Applied account-level quota value* shows ≥ 4.

---

## 1. Launch the instance

EC2 console → **Launch instance**.

| Field | Value | Why |
|---|---|---|
| Name | `avroom` | |
| AMI | **Deep Learning OSS Nvidia Driver AMI (Ubuntu 22.04)** — search "Deep Learning" in the AMI catalog | Ships NVIDIA drivers, Docker, and the NVIDIA Container Toolkit preinstalled. Plain Ubuntu means installing all three by hand, which is the most error-prone part of this setup. |
| Instance type | `g4dn.xlarge` | 1× NVIDIA T4, 16GB VRAM, 4 vCPU, 16GB RAM. Comfortably fits SAM + both depth models + SD-inpaint together. |
| Key pair | **Create new**, type RSA, format `.pem`, name `avroom-key` | Downloads once. **You cannot download it again** — lose it and you lose SSH access to the box. |
| Network → Firewall | **Create security group** (settings in step 2) | |
| Storage | **150 GiB, gp3** | The default 8GB fills instantly: image ≈ 8GB + model weights ≈ 10GB + uploads. |

Then **Launch instance**.

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

Confirm the AMI gave you working GPU + Docker before going further:

```bash
nvidia-smi          # must print a table showing a Tesla T4
docker --version    # must print a version
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
  `docker-compose.gpu.yml`, not here.

Save with `Ctrl+O`, `Enter`, `Ctrl+X`.

## 6. Build and start

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  --profile full up -d --build
```

First build takes **15–30 minutes** (torch alone is ~3GB). Watch it with:

```bash
docker compose logs -f api
```

The entrypoint runs `alembic upgrade head` before starting uvicorn, so the
schema is created automatically — no manual migration step.

## 7. Verify

**GPU is actually in use** — the single most important check, because failure
here is silent and just makes everything ~50× slower:

```bash
docker compose exec api python -c "import torch; print(torch.cuda.is_available())"
```

Must print `True`. If it prints `False`, see Troubleshooting.

**The app responds:**

```bash
curl -I http://localhost
```

**End to end:** open `http://<ELASTIC_IP>` in your browser and run a full
cycle — upload a photo, segment an object, inpaint it, rotate it.

The **first** segment is slow: the container is downloading ~10GB of model
weights into the `hf-cache` volume. Later requests are fast, and the weights
persist across restarts and rebuilds.

---

## Day-to-day

```bash
# logs
docker compose logs -f api

# restart after changing .env
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile full up -d

# deploy new code
git pull
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
  --profile full up -d --build
```

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

**`torch.cuda.is_available()` is `False`** — the container is not getting the
GPU. Check `nvidia-smi` works on the host; if it does, the NVIDIA Container
Toolkit is the issue. Test it directly:
`docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`.
Also confirm you passed **both** `-f` files — dropping
`docker-compose.gpu.yml` silently starts a CPU-only container.

**`VcpuLimitExceeded` at launch** — the quota request from the prerequisite
section has not been approved yet, or was approved in a different region.

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
