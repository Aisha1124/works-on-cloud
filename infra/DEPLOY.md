# Deploy to Cloud Run (from Google Cloud Shell)

One container on Cloud Run (asia-southeast1) serves the API, `/mcp`, the UCP routes and the
dashboard. `gcloud run deploy --source .` sends the repo to Cloud Build, which builds the root
`Dockerfile`. There is no CI/CD pipeline.

## Current limits (read first)
- **Storage is local, not Firestore.** `FirestoreStore` is not implemented yet, so the service
  runs with `STORE_BACKEND=local`. Data lives in the container's in-memory filesystem and is
  **lost on every restart or new revision**. The sample shop `mak-kuih` is seeded again at
  each startup (`scripts/seed_shop.py`). Shops, orders and audit events created on the live
  site disappear when the instance is replaced.
- **`--max-instances=1`** keeps all requests on the one instance that holds the data.
- **Gemini runs through Vertex AI**, with no API key: `GOOGLE_GENAI_USE_VERTEXAI=true`, the project
  from `GCP_PROJECT_ID`, and the Cloud Run service account's credentials (it needs
  `roles/aiplatform.user`). The location is `GEMINI_LOCATION=global`: the Gemini Interactions
  API that the app uses is served from `global` only on Vertex AI (preview). The model
  `gemini-3.8-flash` is listed for Vertex AI in both `global` and `asia-southeast1`. Cloud Run
  itself stays in asia-southeast1, but Gemini requests can be served outside Singapore.
  `GEMINI_API_KEY` is only for local development.
- **`OWNER_KEY` is the owner key of the sample shop `mak-kuih` only.** Use it at
  "Shop owner login" to manage that shop's orders. Every other shop gets its own random key
  when it goes live. Pick a long random value, e.g. `kc_` followed by
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **Email** goes through Gmail SMTP (`EMAIL_PROVIDER=smtp`): `SMTP_USER` is the Gmail address
  and `SMTP_PASSWORD` (Secret Manager) is a Gmail **app password** (Google account → Security →
  2-Step Verification → App passwords). It can email any owner. Mail is sent from
  "KampungCart <SMTP_USER>". Gmail allows a limited number of messages per day, which is enough
  for a demo. `EMAIL_PROVIDER=resend` with `RESEND_API_KEY` still works. Without the provider's
  credentials, emails are only logged and orders still work.
- **Secrets** (`OWNER_KEY`, `SMTP_PASSWORD`, and `RESEND_API_KEY` if you use Resend) live in
  Secret Manager and are injected at runtime. Nothing secret is in the image: `.env` is
  excluded by `.gcloudignore` and `.dockerignore`.
- **`BASE_URL` must be the service URL** (`https://SERVICE-PROJECT_NUMBER.REGION.run.app`).
  The MCP server rejects requests whose Host doesn't match it (HTTP 421). Use that URL, not
  the older random-hash `*.a.run.app` URL that Cloud Run also shows.

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
export SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com" URL="https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app"
export SAMPLE_OWNER_EMAIL=you@example.com SMTP_USER=yourname@gmail.com
echo "Service URL will be: $URL"

# 3. Enable the APIs (aiplatform = Vertex AI)
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com compute.googleapis.com aiplatform.googleapis.com

# 4. Create the secrets (input is hidden; no trailing newline is stored). Skip any that exist.
printf "OWNER_KEY: "; read -rs V; echo; printf %s "$V" | gcloud secrets create OWNER_KEY --data-file=-; unset V
printf "SMTP_PASSWORD (Gmail app password): "; read -rs V; echo; printf %s "$V" | gcloud secrets create SMTP_PASSWORD --data-file=-; unset V

# 5. Permissions for the Cloud Run service account: read the secrets, call Vertex AI, build from source
for S in OWNER_KEY SMTP_PASSWORD; do gcloud secrets add-iam-policy-binding "$S" --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor; done
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/aiplatform.user
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/run.builder

# 6. Deploy (answer Y if asked to create an Artifact Registry repository)
gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated --max-instances=1 --set-env-vars "^|^GEMINI_MODEL=gemini-3.8-flash|GOOGLE_GENAI_USE_VERTEXAI=true|GEMINI_LOCATION=global|STORE_BACKEND=local|BASE_URL=$URL|GCP_PROJECT_ID=$PROJECT_ID|GCP_REGION=$REGION|EMAIL_PROVIDER=smtp|SMTP_HOST=smtp.gmail.com|SMTP_PORT=587|SMTP_USER=$SMTP_USER|SAMPLE_OWNER_EMAIL=$SAMPLE_OWNER_EMAIL" --set-secrets "OWNER_KEY=OWNER_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest"

# 7. Check /mcp lists the tools
curl -s -X POST "$URL/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -c "import json,sys; print([t['name'] for t in json.load(sys.stdin)['result']['tools']])"

# 8. Call get_menu on the seeded shop
curl -s -X POST "$URL/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_menu","arguments":{"shop_slug":"mak-kuih"}}}' | python3 -m json.tool

# 9. AI-readable pages: llms.txt and the JSON-LD on the shop page
curl -s "$URL/llms.txt"; curl -s "$URL/s/mak-kuih/llms.txt"; curl -s "$URL/s/mak-kuih" | grep -o '"@type":"Bakery"'
```

Step 7 should print
`['find_shops', 'get_shop', 'get_menu', 'get_quote', 'place_pickup_order', 'get_order_status']`.

`--set-env-vars` and `--set-secrets` replace everything that was set before. So the old
`GEMINI_API_KEY` (and `RESEND_API_KEY`) secrets are no longer attached, and production uses
Vertex AI. To keep Resend instead of Gmail, set `EMAIL_PROVIDER=resend` and add
`,RESEND_API_KEY=RESEND_API_KEY:latest` to `--set-secrets`.

If a role grant in step 5 hasn't spread yet, step 6 can fail with a permission error, or the first
menu read can fail with a Vertex AI permission error. Wait a couple of minutes and try again.

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
# re-run the exports from step 2 if this is a new Cloud Shell session, then step 6
```
A redeploy creates a new revision, which wipes the local data and reseeds `mak-kuih`.
