# KampungCart

**Make any shop AI-ready from one photo.**

AI shopping agents are becoming the new way people shop. Small shops without websites are invisible to them. KampungCart turns a menu or price-list photo into an AI-agent-ready store with built-in fraud checks and owner approval.

Built for the Google Cloud AI Builder Cup 2026 — Retail & Commerce.

## Team: Works On Cloud
- Aisha Siddiqua (Lead): agents, AI, MCP
- Bijay Pathak: infrastructure, deployment, security, deck

## Stack
Gemini · Google ADK · Cloud Run · Firestore · Cloud Storage · Secret Manager

One Cloud Run container (asia-southeast1) serves the API, the MCP server, the UCP endpoints and the built dashboard. It is deployed with `gcloud run deploy --source .`, which uses Cloud Build only to build the image.

## Structure
- `agents/`: ADK + Gemini agents
- `backend/`: FastAPI APIs, MCP server, UCP endpoint
- `dashboard/`: owner dashboard
- `infra/`: deploy docs
- `docs/`: deck and architecture
- `tests/`: evaluation data
