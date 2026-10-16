# Deploying KampungCart to Cloud Run

One container on Cloud Run (`asia-southeast1`) serves the REST API, `/mcp`, the UCP routes and
the built dashboard. It is built from the root [`Dockerfile`](../Dockerfile) by Cloud Build via
`gcloud run deploy --source .`. There is no CI/CD pipeline.

```
gcloud run deploy --source .
  └─ uploads the repo (minus .gcloudignore) ─> Cloud Build builds the Dockerfile
       └─ image pushed to Artifact Registry (cloud-run-source-deploy)
            └─ new Cloud Run revision, 100% traffic
                 ├─ runs as  kampungcart-run@PROJECT.iam.gserviceaccount.com
                 ├─ env      GEMINI_MODEL, BASE_URL, STORE_BACKEND, GCP_*
                 └─ secrets  GEMINI_API_KEY, OWNER_KEY  (from Secret Manager)
```

## Image

| Stage | Base | What it does |
|---|---|---|
| `dashboard` | `node:22-slim` | `npm ci` + `npm run build` -> `dashboard/dist` |
| `python-deps` | `python:3.12-slim` + uv | `uv sync --frozen --no-dev` from `uv.lock` -> `/app/.venv` |
| `runtime` | `python:3.12-slim` | venv + `agents/` + `backend/` + `dashboard/dist`, non-root user `app`, `uvicorn` on `$PORT` |

Build and run it locally (needs Docker):

```bash
docker build -t kampungcart:local .
docker run --rm -p 8080:8080 --env-file .env -e BASE_URL=http://localhost:8080 kampungcart:local
# http://localhost:8080  (dashboard)   http://localhost:8080/api/health
```

## One-time project setup

Run once per project. Shell variables are shown in bash/zsh syntax; in PowerShell use
`$PROJECT_ID = "..."` etc.

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION=asia-southeast1
SA=kampungcart-run@$PROJECT_ID.iam.gserviceaccount.com
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
```

**1. Enable APIs**

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

**2. Runtime service account.** The app runs as this account, not the default compute account
(which has broad Editor rights).

```bash
gcloud iam service-accounts create kampungcart-run --display-name="KampungCart Cloud Run runtime"
```

**3. Secrets.** Values must have no trailing newline (`OWNER_KEY` is compared byte for byte).

```bash
# Gemini API key (from Google AI Studio)
printf '%s' 'PASTE_KEY_HERE' | gcloud secrets create gemini-api-key --data-file=- --replication-policy=automatic
# Owner dashboard key: random; share it with the owner, it goes in the X-Owner-Key header
python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" \
  | gcloud secrets create owner-key --data-file=- --replication-policy=automatic

# The runtime account can read exactly these two secrets, nothing else
for s in gemini-api-key owner-key; do
  gcloud secrets add-iam-policy-binding $s --member="serviceAccount:$SA" \
    --role=roles/secretmanager.secretAccessor
done
```

PowerShell: write the value to a file with `Set-Content -NoNewline -Path key.txt -Value '...'`,
then `--data-file=key.txt`, and delete the file afterwards. Piping in PowerShell adds a newline.

To rotate a secret: `gcloud secrets versions add owner-key --data-file=-`, then redeploy
(the service pins `:latest` at deploy time).

**4. Build permissions.** `--source` deploys build as the default compute service account. If
the first deploy fails with a permission error on the build, grant it the builder role:

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role=roles/run.builder
```

The person deploying needs `roles/run.admin`, `roles/iam.serviceAccountUser` on the runtime
account, and permission to create builds and Artifact Registry repositories (Owner/Editor covers it).

## Deploy

```bash
uv run python scripts/deploy.py --dry-run   # shows the exact gcloud command
uv run python scripts/deploy.py
```

[`scripts/deploy.py`](../scripts/deploy.py) works out `BASE_URL` before deploying
(`https://kampungcart-PROJECT_NUMBER.asia-southeast1.run.app`). The MCP server only accepts
that host (DNS-rebinding protection), and the UCP profile advertises it. If you add a custom
domain, pass `--base-url https://your.domain`.

Settings and the reasons for them:

| Flag | Why |
|---|---|
| `--allow-unauthenticated` | AI agents and shoppers call it without Google auth. Owner routes need `X-Owner-Key`. |
| `--set-secrets` | `GEMINI_API_KEY`, `OWNER_KEY` come from Secret Manager, never from env files or the image. |
| `--no-cpu-throttling` | Risk explanations run as background tasks after the response; throttled CPU would stall them. |
| `--min-instances 1 --max-instances 1` | Required while `STORE_BACKEND=local` (see below). Also no cold start in the demo. |
| `--cpu-boost` | Faster startup. |
| `--timeout 120` | Gemini catalog extraction is the slowest call; it has its own shorter deadline. |

## Check a deploy

```bash
URL=$(gcloud run services describe kampungcart --region $REGION --format='value(status.url)')
curl -s $URL/api/health                 # {"ok":true}
curl -s $URL/.well-known/ucp | head     # UCP profile, endpoints must use $URL
curl -s -o /dev/null -w '%{http_code}\n' $URL/api/shops   # 401 without X-Owner-Key
gcloud run services logs read kampungcart --region $REGION --limit 50
```

## Roll back

Every deploy is a new revision; the old ones stay.

```bash
gcloud run revisions list --service kampungcart --region $REGION
gcloud run services update-traffic kampungcart --region $REGION --to-revisions=REVISION_NAME=100
```

## Known limits (read before the demo)

> **Data is not persistent yet.** `FirestoreStore` and `GcsImageStore` are stubs, so the service
> runs with `STORE_BACKEND=local`. Shops, orders, the audit log and uploaded photos live on the
> instance's in-memory disk. They are **lost on every redeploy or instance restart**, and they
> count against the instance's memory. Seed demo data after the final deploy, and don't redeploy
> after that.

- **One instance only**, for the same reason, and because the order rate limiter (10/min per
  client) is in memory.
- **Rate-limit key** is the rightmost `X-Forwarded-For` entry, which Cloud Run's front end adds.
  If an external load balancer is put in front, `backend/external.py:client_key` must change.
- **Single shared `OWNER_KEY`** for all shops: fine for the demo, not for real users.
- **Gemini via API key**, not Vertex AI with the service account. Simpler, but it is a long-lived
  key: keep it in Secret Manager and restrict it to the Generative Language API in AI Studio / APIs & Services.
- No custom startup probe: Cloud Run's default TCP probe on `$PORT` is used. `/api/health` is
  available for an HTTP probe.

When Firestore and GCS are implemented, grant the runtime account `roles/datastore.user` and
`roles/storage.objectUser` on the bucket, deploy with `STORE_BACKEND=firestore` and
`GCS_BUCKET=...`, and raise `--max-instances`.
