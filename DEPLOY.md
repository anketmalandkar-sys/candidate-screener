# Deploying the candidate screener

Three ways to run it:

| # | Where | TLS | Secrets | Use for |
|---|---|---|---|---|
| 1 | **Local — dev** | none (`http://localhost`) | `.env` file | working on the code (hot reload) |
| 2 | **Local — full stack** | none / Tailscale | `.env` file | testing the exact deploy image |
| 3 | **GCP `e2-micro` + Secret Manager** | Let's Encrypt via Caddy | GCP Secret Manager | the hosted `$0` demo |

The whole app is one `docker compose` stack:

| Service | Image | Exposed |
|---|---|---|
| `db` | `postgres:16` | container network only |
| `backend` | built from `backend/` | container network only |
| `web` | built from `frontend/` (Vite build → Caddy) | `:80` + `:443` |

`web` (Caddy) is the single public origin: `/api/*` is reverse-proxied to
`backend:8000`, everything else is the built SPA with HTML5-history fallback.
`docker-compose.yml` is dev-only (bind mounts + `--reload`);
`docker-compose.deploy.yml` is the self-contained production stack.

**`SITE_ADDRESS` controls TLS** (deploy stack only):

- unset / empty → Caddy serves plain HTTP on `:80`; terminate TLS upstream
  (Tailscale Funnel, a load balancer, `localhost`).
- `https://<host>` → Caddy fetches and auto-renews its own Let's Encrypt cert
  on `:443`.

---

## 1. Local — development

Hot-reloading backend + Vite dev server. This is what `README.md` covers.

```bash
cp .env.example .env
openssl rand -hex 32          # paste as APP_SECRET_KEY in .env

docker compose up --build     # Postgres + API on :8000, migrations run on start
```

Second terminal:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173  (proxies /api to :8000)
```

Open <http://localhost:5173>, register an account. API docs at
<http://localhost:8000/docs>. Tests: `docker compose exec backend pytest`.

Minimum `.env` for local dev:

```dotenv
POSTGRES_DB=candidate_screener
POSTGRES_USER=screener
POSTGRES_PASSWORD=local-only-change-me
APP_SECRET_KEY=<openssl rand -hex 32>
COOKIE_SECURE=false
TRUSTED_PROXY_COUNT=0
SCREENING_PROVIDER=stub        # `live` needs OPENAI_API_KEY + HF_TOKEN
SEED_DEMO_DATA=true
```

---

## 2. Local — full deploy stack

Runs the exact production images (multi-stage frontend build → Caddy) on your
machine, no cloud. Good for catching build/DB/migration problems before shipping.

```bash
cp .env.example .env
# edit .env: APP_SECRET_KEY, POSTGRES_PASSWORD, leave SITE_ADDRESS blank,
# SCREENING_PROVIDER=stub (or `live` + keys), COOKIE_SECURE=false

docker compose -f docker-compose.deploy.yml up -d --build
curl -s localhost/api/health          # {"status":"ok"}
```

Open <http://localhost>. Tear down with
`docker compose -f docker-compose.deploy.yml down` (add `-v` to wipe the DB).

To put it on a public HTTPS URL without a cloud account, add Tailscale Funnel —
see the appendix at the bottom.

---

## 3. GCP `e2-micro` + Secret Manager

Everything (Postgres + API + web) on **one Always-Free VM**. No domain: `sslip.io`
turns the VM's IP into a hostname Let's Encrypt will certify. Secrets live in
**GCP Secret Manager** — the VM fetches them at deploy time into the shell
environment; the on-disk `.env` holds only non-secret config.

### 3.0 This deployment

The live demo uses these names. Substitute your own if you rebuild from scratch.

| Thing | Value |
|---|---|
| Project | `candidate-screener-2c4010f0` |
| VM | `screener` — `e2-micro`, `us-central1-a`, 30 GB standard disk, 2 GB swap |
| Static IP | `screener-ip` = `34.29.84.124` |
| Firewall | `allow-web` (ingress `tcp:80,443`) |
| Service account | `799020763897-compute@developer.gserviceaccount.com` |
| SA roles | `roles/editor` (default) + `roles/secretmanager.secretAccessor` |
| SA access scope | `cloud-platform` |
| Secrets | `candidate-openai-api-key`, `candidate-hf-token`, `candidate-app-secret-key`, `candidate-postgres-password` |
| Public URL | <https://34-29-84-124.sslip.io> |
| App dir on VM | `~/candidate-screener` (contains `.env`, `secrets.sh`, `deploy.sh`) |

> **Free-tier rules:** one `e2-micro`, in `us-west1` / `us-central1` / `us-east1`,
> 30 GB **standard** (not SSD) disk, per billing account. 1 GB/month North-America
> egress. A static IP is free **only while attached to a running VM**.

### 3.1 One-time GCP setup

```bash
PROJ=candidate-screener              # pick a globally-unique id; a suffix is added below
ZONE=us-central1-a

# ---- project + billing + APIs ----
PROJ="${PROJ}-$(openssl rand -hex 4)"
gcloud projects create "$PROJ" --name="candidate-screener"
gcloud config set project "$PROJ"
gcloud billing projects link "$PROJ" --billing-account=<YOUR_BILLING_ACCOUNT_ID>
gcloud services enable compute.googleapis.com secretmanager.googleapis.com

# ---- VM + firewall ----
gcloud compute instances create screener --zone="$ZONE" \
  --machine-type=e2-micro \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --image-family=debian-12 --image-project=debian-cloud \
  --tags=http-server,https-server
gcloud compute firewall-rules create allow-web \
  --allow=tcp:80,tcp:443 --target-tags=http-server,https-server

# ---- pin the IP (promotes the one it already has; no downtime) ----
IP=$(gcloud compute instances describe screener --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
gcloud compute addresses create screener-ip --addresses="$IP" --region="${ZONE%-*}"
echo "sslip.io host: ${IP//./-}.sslip.io"

# ---- let the VM read Secret Manager ----
# The default compute SA needs the accessor role AND the cloud-platform scope.
# roles/editor can WRITE secrets but GCP withholds payload READ from primitive
# roles, so the explicit binding is required.
SA=$(gcloud compute instances describe screener --zone="$ZONE" \
  --format='get(serviceAccounts[0].email)')
gcloud projects add-iam-policy-binding "$PROJ" \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor" --condition=None

gcloud compute instances stop screener --zone="$ZONE"
gcloud compute instances set-service-account screener --zone="$ZONE" --scopes=cloud-platform
gcloud compute instances start screener --zone="$ZONE"
```

### 3.2 Box setup

```bash
gcloud compute ssh screener --zone=us-central1-a
```

On the VM:

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"        # or just use `sudo docker` (deploy.sh does)

# 2 GB swap — 1 GB RAM alone OOMs Postgres and the Vite build
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# the app + the two helper scripts (kept next to docker-compose.deploy.yml)
git clone <repo-url> && cd candidate-screener
cp deploy/gcp/secrets.sh deploy/gcp/deploy.sh .
chmod +x secrets.sh deploy.sh
```

If `secrets.sh`'s project id differs from yours, either edit the `PROJ=` line or
run `deploy.sh` with `GCP_PROJECT=<your-project> ./deploy.sh ...`.

### 3.3 Create the secrets

Generate the app/DB secrets and store all four in Secret Manager. Run from your
workstation (gcloud authed) **or** the VM:

```bash
PROJ=candidate-screener-2c4010f0

printf %s "$(openssl rand -hex 32)" | gcloud secrets create candidate-app-secret-key    --project="$PROJ" --data-file=-
printf %s "$(openssl rand -hex 24)" | gcloud secrets create candidate-postgres-password --project="$PROJ" --data-file=-
printf %s "sk-...your-openai-key..." | gcloud secrets create candidate-openai-api-key   --project="$PROJ" --data-file=-
printf %s "hf_...your-hf-token..."   | gcloud secrets create candidate-hf-token         --project="$PROJ" --data-file=-
```

`candidate-hf-token` is exposed to the container as both `HF_TOKEN` and
`HF_API_TOKEN`. `SCREENING_PROVIDER=stub` needs neither the OpenAI nor HF secret.

### 3.4 `.env` on the VM — non-secret config only

```bash
cd ~/candidate-screener
cp .env.example .env
```

Set (IP `34.29.84.124` → host `34-29-84-124.sslip.io`):

| Var | Value |
|---|---|
| `SITE_ADDRESS` | `https://34-29-84-124.sslip.io` |
| `EXTRA_ORIGINS` | `https://34-29-84-124.sslip.io` |
| `COOKIE_SECURE` | `true` |
| `TRUSTED_PROXY_COUNT` | `1` |
| `POSTGRES_DB` | `candidate_screener` |
| `POSTGRES_USER` | `screener` |
| `SEED_DEMO_DATA` | `true` |
| `SCREENING_PROVIDER` | `live` (or `stub` for zero outbound spend) |
| `SCREENING_LOG_PROMPTS` | `false` |

**Do not put** `APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `OPENAI_API_KEY`,
`HF_TOKEN`, or `HF_API_TOKEN` in `.env` — `secrets.sh` supplies them. If any are
present they are ignored (compose env vars from `deploy.sh` win), but keep the
file clean:

```bash
sed -i -E '/^(OPENAI_API_KEY|HF_API_TOKEN|HF_TOKEN|APP_SECRET_KEY|POSTGRES_PASSWORD)=/d' .env
chmod 600 .env
```

### 3.5 Deploy

```bash
./deploy.sh up -d --build      # first time: builds images
curl -s https://34-29-84-124.sslip.io/api/health     # {"status":"ok"}
```

`deploy.sh` prints `secrets loaded (164/37/64/20 chars)` — four non-zero lengths
means Secret Manager is wired up. First HTTPS request takes ~10-30 s while Caddy
gets the certificate.

> **If `npm run build` is OOM-killed** even with swap: build images on your laptop
> (`docker compose -f docker-compose.deploy.yml build`), `docker save | ssh …
> docker load`, then `./deploy.sh up -d` (no `--build`). Or Cloud Build (free:
> 120 build-min/day) → Artifact Registry → `./deploy.sh pull`.

### 3.6 Day-to-day

```bash
cd ~/candidate-screener

./deploy.sh up -d              # (re)start
./deploy.sh down              # stop  (DB volume persists; add -v to wipe)
./deploy.sh logs -f backend
./deploy.sh ps

# deploy a code change
git pull && ./deploy.sh up -d --build    # alembic migrations run on backend start

# rotate a key: add a new version, then bounce the stack
printf %s 'NEW_VALUE' | gcloud secrets versions add candidate-openai-api-key \
  --project=candidate-screener-2c4010f0 --data-file=-
./deploy.sh down && ./deploy.sh up -d
```

⚠️ Never run `sudo docker compose -f docker-compose.deploy.yml up -d` directly —
it starts with blank secrets and the backend won't boot. Always `./deploy.sh`.

Note: once containers are running, Docker keeps the injected values in its
root-only state under `/var/lib/docker`, so a VM reboot brings the app back
(`restart: unless-stopped`) without re-running `deploy.sh`. What Secret Manager
buys you: no plaintext key file in the repo dir, and central, versioned,
audit-logged, revocable secrets.

### 3.7 Tear down

```bash
./deploy.sh down                                              # on the VM
gcloud compute instances delete screener --zone=us-central1-a
gcloud compute addresses delete screener-ip --region=us-central1
gcloud compute firewall-rules delete allow-web
# secrets, if abandoning the project:
for s in candidate-openai-api-key candidate-hf-token candidate-app-secret-key candidate-postgres-password; do
  gcloud secrets delete "$s" --project=candidate-screener-2c4010f0 --quiet
done
```

If you only **stop** the VM long-term, also delete `screener-ip` — an unattached
static IP bills ~\$0.0075/hr (~\$5/mo).

---

## Notes (all deploy modes)

- **Cost / abuse exposure:** registration is open and `SCREENING_PROVIDER=live`
  calls OpenAI + Hugging Face. Anyone with the URL can spend your credits — set a
  hard spend cap on both keys before sharing. `SCREENING_PROVIDER=stub` disables
  all outbound calls.
- `SCREENING_LOG_PROMPTS=true` (default) writes résumé text to the backend logs.
  The GCP deploy sets it `false`.
- The backend still starts uvicorn with `--reload` (from `backend/start.sh`).
  Harmless but uses extra memory on the 1 GB VM; drop the flag if you want the
  headroom.

---

## Appendix — Tailscale Funnel (public HTTPS, no cloud account)

Works with mode 2 (or any box: Raspberry Pi, laptop, free VM). Leave
`SITE_ADDRESS` blank so Caddy stays on `:80` and Tailscale terminates TLS.

One-time: Tailscale admin console → **DNS** → enable MagicDNS + HTTPS
Certificates; give the host the `funnel` node attribute (or run
`tailscale funnel 80` once and follow the link).

```bash
docker compose -f docker-compose.deploy.yml up -d --build
tailscale funnel --bg 80        # prints https://<host>.<tailnet>.ts.net
tailscale funnel status
tailscale funnel --bg off       # stop publishing
```

`tailscale serve 80` instead keeps it private to your tailnet.
