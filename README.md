# KampungCart

**Make any shop AI-ready from one photo.**

AI shopping agents are becoming the new way people shop. Small shops without websites are invisible to them. KampungCart turns a menu or price-list photo into an AI-agent-ready store with built-in fraud checks and owner approval.

Built for the Google Cloud AI Builder Cup 2026 — Retail & Commerce.

## Team: Works On Cloud
- Aisha Siddiqua (Lead): agents, AI, MCP
- Bijay Pathak: infrastructure, CI/CD, security, deck

## Stack
Gemini · Google ADK · Cloud Run · Firestore · Cloud Storage · Firebase Hosting · Secret Manager · Cloud Build

## Structure
- `agents/`: ADK + Gemini agents
- `backend/`: FastAPI APIs, MCP server, UCP endpoint
- `dashboard/`: owner dashboard
- `infra/`: deployment and CI/CD
- `docs/`: deck and architecture
- `tests/`: evaluation data
