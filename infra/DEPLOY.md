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
- **`OWNER_KEY` is the owner key of the sample shop `mak-kuih` only.** Use it at
  "Shop owner login" to manage that shop's orders. Every other shop gets its own random key
  when it goes live. Pick a long random value, e.g. `kc_` followed by
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **Secrets** (`GEMINI_API_KEY`, `OWNER_KEY`) live in Secret Manager and are injected at
  runtime. Nothing secret is in the image: `.env` is excluded by `.gcloudignore` and
  `.dockerignore`.
- **`BASE_URL` must be the service URL** (`https://SERVICE-PROJECT_NUMBER.REGION.run.app`).
  The MCP server rejects requests whose Host doesn't match it (HTTP 421). Use that URL, not
  the older random-hash `*.a.run.app` URL that Cloud Run also shows.

## Commands
Run these in Cloud Shell, in order. Replace `your-project-id` in step 2.

```bash
# 1. Clone the repo
git clone https://github.com/Aisha1124/works-on-cloud.git
cd works-on-cloud

# 2. Set the project and the names used below
export PROJECT_ID=your-project-id
export REGION=asia-southeast1
export SERVICE=kampungcart
gcloud config set project "$PROJECT_ID"
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
export SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
export URL="https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app"
echo "Service URL will be: $URL"

# 3. Enable the APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com compute.googleapis.com

# 4. Create the secrets (input is hidden; no trailing newline is stored)
printf "GEMINI_API_KEY: "; read -rs V; echo; printf %s "$V" | gcloud secrets create GEMINI_API_KEY --data-file=-; unset V
printf "OWNER_KEY: "; read -rs V; echo; printf %s "$V" | gcloud secrets create OWNER_KEY --data-file=-; unset V

# 5. Let the Cloud Run service account read the secrets, and build from source
for S in GEMINI_API_KEY OWNER_KEY; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA" --role=roles/run.builder

# 6. Deploy (answer Y if asked to create an Artifact Registry repository)
gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --allow-unauthenticated --max-instances=1 \
  --set-env-vars "GEMINI_MODEL=gemini-3.8-flash,STORE_BACKEND=local,BASE_URL=$URL,GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION" \
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest,OWNER_KEY=OWNER_KEY:latest"

# 7. Check /mcp lists the tools
curl -s -X POST "$URL/mcp" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python3 -c "import json,sys; print([t['name'] for t in json.load(sys.stdin)['result']['tools']])"

# 8. Call get_menu on the seeded shop
curl -s -X POST "$URL/mcp" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_menu","arguments":{"shop_slug":"mak-kuih"}}}' \
  | python3 -m json.tool
```

Step 7 should print
`['find_shops', 'get_shop', 'get_menu', 'get_quote', 'place_pickup_order', 'get_order_status']`.

If the role grant in step 5 hasn't spread yet, step 6 can fail with a permission error. Wait a
couple of minutes and run step 6 again.

## Redeploy after a code change
```bash
cd ~/works-on-cloud && git pull
# re-run the exports from step 2 if this is a new Cloud Shell session, then step 6
```
A redeploy creates a new revision, which wipes the local data and reseeds `mak-kuih`.
