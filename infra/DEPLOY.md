# Deploy to Cloud Run (from Google Cloud Shell)

> **`kampungcart-prod` is managed by Terraform and GitHub Actions**. See [README.md](README.md).
> Merging to `main` deploys. Use this guide only to stand up a separate project by hand; running
> its commands against `kampungcart-prod` would drift from the Terraform state.

One container on Cloud Run (asia-southeast1) serves the API, `/mcp`, the UCP routes and the
dashboard. `gcloud run deploy --source .` sends the repo to Cloud Build, which builds the root
`Dockerfile`. There is no CI/CD pipeline.

## How it runs (read first)
- **Data is in Firestore** (Native mode, `(default)` database, asia-southeast1) with
  `STORE_BACKEND=firestore`. Shops, menus, orders, the audit log, sign-in links, sessions,
  idempotency keys and rate-limit counters all live there, so they survive restarts and
  redeploys, and every instance sees the same data. That is why there is **no
  `--max-instances=1`** any more.
- **Menu photos** go to a private Cloud Storage bucket (`GCS_BUCKET`).
- **Credentials**: the Cloud Run service account, through Application Default Credentials. No key
  files. It needs `roles/datastore.user` (Firestore), `roles/storage.objectCreator` on the photo
  bucket, `roles/aiplatform.user` (Gemini) and `roles/secretmanager.secretAccessor` on the secrets.
- **The sample shop `mak-kuih`** is created at startup only if it doesn't exist
  (`scripts/seed_shop.py`). A redeploy never overwrites it. Only its owner key follows `OWNER_KEY`.
- **Gemini runs through Vertex AI**, with no API key: `GOOGLE_GENAI_USE_VERTEXAI=true`, the project
  from `GCP_PROJECT_ID`, and the service account's credentials. The location is
  `GEMINI_LOCATION=global`: the Gemini Interactions API that the app uses is served from `global`
  only on Vertex AI (preview). Cloud Run itself stays in asia-southeast1, but Gemini requests can
  be served outside Singapore. `GEMINI_API_KEY` is only for local development.
- **`OWNER_KEY` is the owner key of the sample shop `mak-kuih` only.** Use it at "Shop owner
  login" to manage that shop. Every other shop gets its own random key when it goes live. Pick a
  long random value, e.g. `kc_` followed by `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **Email** goes through Gmail SMTP: `SMTP_USER` is the Gmail address and `SMTP_PASSWORD` a Gmail
  **app password** (Google account → Security → 2-Step Verification → App passwords). Gmail allows a
  limited number of messages per day, which is enough for a demo. Without them, emails are only
  logged and orders still work.
- **`ADMIN_EMAIL`** gets "Report this shop" messages and is shown on `/privacy` for deletion
  requests.
- **Secrets** (`OWNER_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `ADMIN_EMAIL`) live in Secret Manager
  and are injected at runtime. Nothing secret is in the image: `.env` is excluded by
  `.gcloudignore` and `.dockerignore`.
- **`BASE_URL` must be the service URL** (`https://SERVICE-PROJECT_NUMBER.REGION.run.app`). The
  MCP server rejects requests whose Host doesn't match it (HTTP 421).
- **Background jobs** (expiring held orders after the shop's timeout, erasing customer details 90
  days after pickup) run every 5 minutes while an instance is up, *and* whenever an order is read.
  So expiry is correct even when Cloud Run scales to zero; it just happens on the next visit.

## Commands
Run these in Cloud Shell, in order. Each command is one line. Replace `your-project-id`,
`you@example.com` and `yourname@gmail.com` in step 2.

```bash
# 1. Clone the repo (or: cd ~/works-on-cloud && git pull)
git clone https://github.com/Aisha1124/works-on-cloud.git && cd works-on-cloud

# 2. Set the project and the names used below
export PROJECT_ID=your-project-id REGION=asia-southeast1 SERVICE=kampungcart
gcloud config set project "$PROJECT_ID"
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
export SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com" URL="https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app" BUCKET="$PROJECT_ID-kampungcart-photos"
export SAMPLE_OWNER_EMAIL=you@example.com
echo "Service URL will be: $URL"

# 3. Enable the APIs (aiplatform = Vertex AI)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com compute.googleapis.com aiplatform.googleapis.com firestore.googleapis.com storage.googleapis.com

# 4. Create the Firestore database (Native mode, Singapore). Skip if it already exists.
gcloud firestore databases create --location="$REGION" --type=firestore-native

# 5. Let Firestore delete old rate-limit counters by itself (TTL on the "expire_at" field)
gcloud firestore fields ttls update expire_at --collection-group=rate_limits --enable-ttl

# 6. Create the private bucket for menu photos
gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access

# 7. Create the secrets (input is hidden; no trailing newline is stored). Skip any that exist.
printf "OWNER_KEY: "; read -rs V; echo; printf %s "$V" | gcloud secrets create OWNER_KEY --data-file=-; unset V
printf "SMTP_USER (Gmail address): "; read -r V; printf %s "$V" | gcloud secrets create SMTP_USER --data-file=-; unset V
printf "SMTP_PASSWORD (Gmail app password): "; read -rs V; echo; printf %s "$V" | gcloud secrets create SMTP_PASSWORD --data-file=-; unset V
printf "ADMIN_EMAIL (gets shop reports): "; read -r V; printf %s "$V" | gcloud secrets create ADMIN_EMAIL --data-file=-; unset V

# 8. Permissions for the Cloud Run service account
for S in OWNER_KEY SMTP_USER SMTP_PASSWORD ADMIN_EMAIL; do gcloud secrets add-iam-policy-binding "$S" --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor; done
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/datastore.user
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member="serviceAccount:$SA" --role=roles/storage.objectCreator
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/aiplatform.user
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/run.builder

# 9. Deploy (answer Y if asked to create an Artifact Registry repository). --max-instances=10
#    is a cost cap only; the app no longer needs a single instance.
gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated --max-instances=10 --set-env-vars "^|^GEMINI_MODEL=gemini-3.8-flash|GOOGLE_GENAI_USE_VERTEXAI=true|GEMINI_LOCATION=global|STORE_BACKEND=firestore|FIRESTORE_DATABASE=(default)|GCS_BUCKET=$BUCKET|BASE_URL=$URL|GCP_PROJECT_ID=$PROJECT_ID|GCP_REGION=$REGION|EMAIL_PROVIDER=smtp|SMTP_HOST=smtp.gmail.com|SMTP_PORT=587|SAMPLE_OWNER_EMAIL=$SAMPLE_OWNER_EMAIL" --set-secrets "OWNER_KEY=OWNER_KEY:latest,SMTP_USER=SMTP_USER:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest,ADMIN_EMAIL=ADMIN_EMAIL:latest"

# 10. Check /mcp lists the tools
curl -s -X POST "$URL/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -c "import json,sys; print([t['name'] for t in json.load(sys.stdin)['result']['tools']])"

# 11. AI-readable pages: llms.txt and the JSON-LD on the shop page
curl -s "$URL/llms.txt"; curl -s "$URL/s/mak-kuih/llms.txt"; curl -s "$URL/s/mak-kuih" | grep -o '"@type":"Bakery"'
```

Step 10 should print
`['find_shops', 'get_shop', 'get_menu', 'get_quote', 'place_pickup_order', 'get_order_status']`.

`--set-env-vars` and `--set-secrets` replace everything that was set before. If a role grant in
step 8 hasn't spread yet, step 9 can fail with a permission error. Wait a couple of minutes and
try again.

## Check that data survives a redeploy
Place an order, force a new revision, and read the order back through its private status link.

```bash
# 1. Place an order on the sample shop (first free pickup slot) and keep its status link
SLOT=$(curl -s "$URL/api/public/shops/mak-kuih/slots" | python3 -c "import json,sys; print(json.load(sys.stdin)['days'][0]['times'][0]['value'])"); STATUS=$(curl -s -X POST "$URL/api/public/shops/mak-kuih/orders" -H "Content-Type: application/json" -d "{\"items\":[{\"product_id\":\"kuih-lapis\",\"variant\":\"20 pcs\",\"qty\":1}],\"customer_name\":\"Redeploy Check\",\"customer_phone\":\"+65 9123 4567\",\"pickup_time\":\"$SLOT\"}" | python3 -c "import json,sys; print(json.load(sys.stdin)['status_url'])"); echo "$STATUS"

# 2. Force a new revision (same code, new instance)
gcloud run services update "$SERVICE" --region "$REGION" --update-env-vars "REDEPLOY_CHECK=$(date +%s)"

# 3. The order is still there (prints its status, e.g. confirmed)
curl -s "$URL/api/public/orders/$(echo "$STATUS" | sed -E 's#.*/o/([^?]+)\?t=(.*)#\1?t=\2#')" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['order_id'], d['status'])"
```

## Check Vertex AI and email after deploying
- Upload a menu photo on the live site, then look for the Gemini log line (it should say `ok=True`):
  `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE AND textPayload:gemini_call" --freshness=1h --limit=5 --format="value(textPayload)"`
- Email failures are logged with a masked address:
  `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE AND textPayload:\"email failed\"" --freshness=1h --limit=5 --format="value(textPayload)"`

## Gemini usage (for honest reporting)
Every Gemini attempt writes one `gemini_call` line (a retry is a second line). It holds a running
count per instance, the label, the model, ok/failed, seconds and token counts, and never any
prompt text or customer data. Count the calls in the last 30 days:
`gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE AND textPayload:gemini_call" --freshness=30d --format="value(textPayload)" | wc -l`
Add `AND textPayload:ok=True` to count only successful calls. Log retention is 30 days by default.

## Redeploy after a code change
```bash
cd ~/works-on-cloud && git pull
# re-run the exports from step 2 if this is a new Cloud Shell session, then step 9
```
Data stays in Firestore, so a redeploy keeps every shop, order and audit event.

## Local Firestore (emulator)
`.\scripts\firestore_emulator.ps1` starts the Firestore emulator on Windows (needs Java and
Node, no gcloud). With `FIRESTORE_EMULATOR_HOST=127.0.0.1:8085`, `uv run pytest tests/test_store.py`
runs every store test on both backends.
