# SAP O2C Graph Query System

A full-stack graph exploration system for SAP Order-to-Cash data. The backend ingests raw O2C datasets, normalizes business entities, builds an in-memory NetworkX graph, mirrors the normalized entities into SQLite, and exposes graph/query APIs through FastAPI. The frontend renders the graph with Cytoscape.js and adds a natural-language copilot for guided exploration.

## What This Project Does

- Loads SAP O2C datasets from `sap-o2c-data`
- Normalizes Orders, Deliveries, Invoices, Payments, Customers, Products, Addresses, Plants, and Journal Entries
- Builds a typed relationship graph in NetworkX
- Loads normalized entities into an in-memory SQLite engine for transparent SQL translation
- Supports natural-language querying with Gemini
- Streams query progress and answer generation back to the UI
- Maintains lightweight per-session conversation memory for follow-up questions
- Visualizes graph structure, node metadata, analytics overlays, and query-driven highlights in React + Cytoscape.js

## Repository Layout

```text
backend/
  agents/              LLM client, memory, schema context, NL query pipeline
  routes/              FastAPI route modules
  services/            data loading, graph building, SQL engine, analytics, graph store
  tests/               backend tests
  config.py            environment-driven runtime settings
  Dockerfile           production backend image
  main.py              FastAPI entrypoint
frontend/
  src/components/      graph viewer, toolbar, detail panel, chat panel
  src/services/        API client
  src/types/           frontend API and graph typings
  Dockerfile           production frontend image
  nginx.conf           SPA + API reverse proxy config
sap-o2c-data/          raw SAP O2C files
docker-compose.yml     production-like local deployment
```

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..
copy .env.example .env
python -m backend
```

Backend API is available at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend is available at `http://localhost:5173`.

## Environment Variables

Create a root `.env` file from `.env.example`.

```env
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DATA_DIR=./sap-o2c-data
GEMINI_API_KEY=your_gemini_api_key_here
VITE_API_BASE_URL=
VITE_API_PROXY_TARGET=http://localhost:8000
```

Notes:

- Leave `VITE_API_BASE_URL` empty when the frontend is served from the same host and proxies `/api` through Nginx.
- Set `VITE_API_BASE_URL` only when the frontend must call a separate backend origin directly.
- `ALLOWED_ORIGINS` is a comma-separated list consumed by FastAPI CORS middleware.
- `DATA_DIR` must point to the bundled SAP dataset directory in the target environment.
- The backend exposes `GET /healthz` for container and platform health checks.
- The production backend should stay at `WEB_CONCURRENCY=1` unless you intentionally want multiple in-memory graph copies.

## Deployment Ready Setup

### Option 1: Docker Compose on One Host

This is the simplest production-style setup for this repository.

```bash
copy .env.example .env
# edit .env for your real domain + API key
docker compose up --build -d
```

App URLs:

- Frontend: `http://localhost:8080`
- Backend: `http://localhost:8000`
- Health check: `http://localhost:8000/healthz`

### Option 2: Separate Frontend and Backend Deployments

Backend start command:

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:$PORT backend.main:app
```

Frontend build command:

```bash
npm run build
```

Frontend publish directory:

```text
frontend/dist
```

If the frontend and backend are on different origins:

- set `VITE_API_BASE_URL=https://your-api-domain`
- set `ALLOWED_ORIGINS=https://your-frontend-domain`

## Files To Edit During Deployment

Use these exact files when promoting to staging or production:

- `.env.example` -> copy to `.env` and set `GEMINI_API_KEY`, `ALLOWED_ORIGINS`, `DATA_DIR`, and optionally `VITE_API_BASE_URL`
- `docker-compose.yml` -> update exposed ports and `ALLOWED_ORIGINS` if you are not using `localhost:8080`
- `frontend/nginx.conf` -> update `proxy_pass http://backend:8000;` only if your frontend container must proxy to a differently named backend upstream
- `frontend/Dockerfile` -> set `VITE_API_BASE_URL` build arg only when you need a hard-coded external API origin at build time
- `backend/Dockerfile` -> adjust the gunicorn bind/worker command only if your hosting platform requires different port binding behavior

## Sample Questions

- Which products are associated with the highest number of billing documents?
- Trace the full flow of billing document 90504204
- Find sales orders with broken or incomplete flows
- Show me all orders for customer 320000083
- What invoices are linked to delivery 80738040?
- Show the full chain from order 740509 to payment
- Trace invoice 90504204 flow
- Which of these have deliveries?
- What about their invoices?
- What is the capital of France?
  This should be rejected by the guardrail.

## API Highlights

- `GET /healthz`
- `GET /api/graph`
- `GET /api/graph/stats`
- `GET /api/graph/clusters`
- `GET /api/graph/importance`
- `GET /api/graph/broken-flows`
- `GET /api/node/{node_id}`
- `GET /api/node/{node_id}/subgraph?depth=2`
- `POST /api/graph/node`
- `POST /api/graph/edge`
- `DELETE /api/graph/reset`
- `GET /api/graph/export`
- `POST /api/query`
- `POST /api/query/stream`
- `DELETE /api/session/{session_id}`
