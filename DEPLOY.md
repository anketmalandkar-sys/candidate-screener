# Deploying a short public demo

The whole app is one `docker compose` stack. `docker-compose.deploy.yml` brings up
three containers:

| Service | Image | Exposed |
|---|---|---|
| `db` | `postgres:16` | no |
| `backend` | built from `backend/` | no |
| `web` | built from `frontend/` (Vite build → Caddy) | `:80` + `:443` |

`web` (Caddy) is the single origin: `/api/*` is reverse-proxied to `backend:8000`,
everything else is the built SPA with history-API fallback. `SITE_ADDRESS` decides
how TLS is handled:

- **unset** → Caddy serves plain HTTP on `:80`; put a tunnel in front (Tailscale Funnel).
- **`https://<host>`** → Caddy fetches and renews its own Let's Encrypt cert on `:443`.

Two ways to run it are documented below. The GCP VM is the simplest "all on one box,
no domain, real certificate, $0" option.

---

## Option A — one GCP `e2-micro` VM (Always Free)

Everything (Postgres + API + web) runs on a single free VM. No domain: `sslip.io`
turns the VM's IP into a hostname Let's Encrypt will issue a cert for.

> **Free-tier rules:** exactly one `e2-micro`, in `us-west1` / `us-central1` /
> `us-east1`, 30 GB **standard** (not SSD) disk, per billing account. Egress free
> tier is 1 GB/month from North America — plenty for a demo, not for real traffic.

### 1. Create the VM and open the firewall

```bash
gcloud compute instances create screener \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --image-family=debian-12 --image-project=debian-cloud \
  --tags=http-server,https-server

gcloud compute firewall-rules create allow-web \
  --allow=tcp:80,tcp:443 --target-tags=http-server,https-server

gcloud compute instances describe screener --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'   # note this IP
```

The external IP is free while it's attached to a running instance. To keep it across
a stop/start, reserve it: `gcloud compute addresses create screener-ip --region=us-central1`
then assign it — still free while attached.

### 2. Set up the box

```bash
gcloud compute ssh screener --zone=us-central1-a
```

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER" && exec sg docker newgrp

# 1 GB RAM is tight — 2 GB swap keeps Postgres and the image build from OOMing
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

git clone <repo-url> && cd candidate-screener
cp .env.example .env
```

### 3. Fill in `.env`

With VM IP `34.28.1.2`, the sslip.io host is `34-28-1-2.sslip.io`:

| Var | Value |
|---|---|
| `SITE_ADDRESS` | `https://34-28-1-2.sslip.io` |
| `EXTRA_ORIGINS` | `https://34-28-1-2.sslip.io` (same value) |
| `APP_SECRET_KEY` | output of `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | a strong random string |
| `COOKIE_SECURE` | `true` |
| `TRUSTED_PROXY_COUNT` | `1` |
| `SEED_DEMO_DATA` | `true` |
| `SCREENING_PROVIDER` | `live` (or `stub` for a zero-cost demo) |
| `SCREENING_LOG_PROMPTS` | `false` |
| `OPENAI_API_KEY`, `HF_TOKEN` | your keys |

### 4. Bring it up

```bash
docker compose -f docker-compose.deploy.yml up -d --build
curl -s https://34-28-1-2.sslip.io/api/health      # {"status":"ok"}
```

First request may take ~30 s while Caddy gets the certificate. Share the
`https://34-28-1-2.sslip.io` URL.

> **If `npm run build` gets OOM-killed** even with swap: build the images on your
> laptop (`docker compose -f docker-compose.deploy.yml build`), `docker save | ssh …
> docker load`, then `up -d` without `--build`. Or use Cloud Build (free: 120
> build-min/day) → Artifact Registry → `docker compose pull`.

---

## Option B — any box + Tailscale Funnel (no cloud account, no open ports)

Same stack, but leave `SITE_ADDRESS` **blank** and let Tailscale terminate TLS.
Works on a Raspberry Pi, a laptop, or any free VM.

### One-time Tailscale setup

1. Admin console → **DNS**: enable **MagicDNS** and **HTTPS Certificates**.
2. Admin console → **Access controls**: give the host the `funnel` node attribute
   (or run `tailscale funnel 80` once and follow the link it prints).

### Deploy

```bash
git clone <repo-url> && cd candidate-screener
cp .env.example .env
```

Edit `.env`: set `APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `COOKIE_SECURE=true`,
`TRUSTED_PROXY_COUNT=2`, `SEED_DEMO_DATA=true`, `SCREENING_PROVIDER=live`, your keys.
Leave `SITE_ADDRESS` and `EXTRA_ORIGINS` blank.

```bash
docker compose -f docker-compose.deploy.yml up -d --build
curl -s localhost/api/health          # {"status":"ok"}
tailscale funnel --bg 80              # prints the public https://<host>.ts.net URL
tailscale funnel status
```

`tailscale serve 80` instead of `funnel` keeps it reachable only from your own
tailnet devices.

---

## Update after a code change

```bash
git pull
docker compose -f docker-compose.deploy.yml up -d --build
```

Alembic migrations run automatically on `backend` start; the `pgdata` volume persists.

## Tear down

```bash
tailscale funnel --bg off                             # Option B only
docker compose -f docker-compose.deploy.yml down      # add -v to also delete the database
gcloud compute instances delete screener --zone=us-central1-a   # Option A
```

## Notes

- **Cost exposure:** registration is open and `SCREENING_PROVIDER=live` calls OpenAI +
  Hugging Face. Anyone with the URL can spend your credits — set a hard spend cap on both
  keys before sharing. `SCREENING_PROVIDER=stub` disables all outbound calls.
- `SCREENING_LOG_PROMPTS=true` (default) writes résumé text to `docker compose logs
  backend`. Set `false` in `.env` to quiet it.
