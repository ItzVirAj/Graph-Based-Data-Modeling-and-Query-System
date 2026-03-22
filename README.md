# SAP O2C Graph Query System

A full-stack graph exploration system for SAP Order-to-Cash data. The backend ingests raw O2C datasets, normalizes business entities, builds an in-memory NetworkX graph, and exposes graph/query APIs through FastAPI. The frontend renders the graph with Cytoscape.js and adds a natural-language chat workflow for guided exploration.

## What This Project Does

- Loads SAP O2C datasets from `sap-o2c-data`
- Normalizes Orders, Deliveries, Invoices, Payments, Customers, Products, and Addresses
- Builds a typed relationship graph in NetworkX
- Exposes graph inspection and mutation APIs with FastAPI
- Supports natural-language querying through a unified LLM query pipeline
- Visualizes nodes, edges, metadata, and query highlights in React + Cytoscape.js

## Dataset Scope

The current dataset covers the order-to-cash chain:

`Customer -> Order -> Delivery -> Invoice -> Payment`

Supported graph node types:

- `Order`
- `Delivery`
- `Invoice`
- `Payment`
- `Customer`
- `Product`
- `Address`

Primary edge patterns:

- `Order -> Delivery`
- `Delivery -> Invoice`
- `Invoice -> Payment`
- `Order -> Customer`
- `Order -> Product`
- `Customer -> Address`

## Architecture

```text
+-----------------------+        +---------------------------+
| Raw SAP O2C Files     |        | Frontend (React + Vite)   |
| CSV / JSON / JSONL    |        | Cytoscape.js + Tailwind   |
+-----------+-----------+        +-------------+-------------+
            |                                      |
            v                                      |
+-----------+-----------+                          |
| Data Loader            |                         |
| format handling        |                         |
| schema normalization   |                         |
| Pydantic validation    |                         |
+-----------+-----------+                          |
            |                                      |
            v                                      v
+-----------+-----------+        +---------------------------+
| Graph Builder          |<------| FastAPI REST API          |
| NetworkX MultiDiGraph  |       | graph/query endpoints     |
| typed nodes + edges    |       | in-memory graph store     |
+-----------+-----------+        +-------------+-------------+
            |                                      |
            v                                      |
+-----------+-----------+                          |
| Query Pipeline         |-------------------------+
| guardrail              |
| LLM translation        |
| Python execution       |
| LLM answer generation  |
+-----------------------+
```

## Repository Layout

```text
backend/
  agents/              LLM client, schema context, NL query pipeline
  logs/                LLM session markdown logs
  prompts/             example natural-language prompts
  routes/              FastAPI route modules
  services/            data loading, graph building, graph store
  tests/               backend tests
  main.py              FastAPI entrypoint
frontend/
  src/components/      graph viewer, toolbar, detail panel, chat panel
  src/services/        API client
  src/types/           frontend API and graph typings
sap-o2c-data/          raw SAP O2C files
```

## Backend Setup

1. Create a virtual environment.
2. Install dependencies.
3. Configure environment variables.
4. Start the API server.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..
copy .env.example .env
uvicorn backend.main:app --reload
```

Backend API will be available at `http://localhost:8000`.

## Frontend Setup

1. Install frontend dependencies.
2. Start the Vite dev server.

```bash
cd frontend
npm install
npm run dev
```

Frontend will be available at `http://localhost:5173`.

## Environment Variables

Create a root `.env` file from `.env.example`.

Current LLM integration uses Gemini via `GEMINI_API_KEY`. If the key is missing, the backend automatically falls back to a rule-based mock mode for translation and answer generation.

The user request mentioned an OpenAI API key, so the template also includes `OPENAI_API_KEY` as a placeholder for future provider swaps. The current backend does not use it yet.

Example:

```env
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=
VITE_API_BASE_URL=http://localhost:8000
```

## Running The Full App

Start the backend first:

```bash
uvicorn backend.main:app --reload
```

Then start the frontend in a second terminal:

```bash
cd frontend
npm run dev
```

## Sample Questions

- Show me all orders for customer 320000083
- What invoices are linked to delivery 80738040?
- Show the full chain from order 740509 to payment
- Count all invoices in the graph
- Which products appear in the most orders?
- What payments are connected to invoice 90504204?
- Show addresses for customer 320000083
- Trace invoice 90504204 flow
- What is the weather in Mumbai today?
  This should be rejected by the guardrail.

More examples live in `backend/prompts/example_prompts.md`.

## API Highlights

- `GET /api/graph`
- `GET /api/graph/stats`
- `GET /api/node/{node_id}`
- `GET /api/node/{node_id}/subgraph?depth=2`
- `POST /api/graph/node`
- `POST /api/graph/edge`
- `DELETE /api/graph/reset`
- `GET /api/graph/export`
- `POST /api/query`

## Screenshots

Add screenshots here as the UI is finalized.

- `docs/screenshots/graph-overview.png` - full graph view placeholder
- `docs/screenshots/node-detail.png` - node metadata panel placeholder
- `docs/screenshots/chat-query.png` - natural-language query workflow placeholder
- `docs/screenshots/subgraph-highlight.png` - graph highlight/subgraph placeholder

## Logging

Every query appends a markdown entry to `backend/logs/llm_sessions.md`.

The log captures:

- guardrail decisions
- translator prompt/response
- translation refinement passed to execution
- answer-generation prompt/response
- fallback notes when mock mode is used

## Integration Notes

This repository has been verified locally with:

- backend graph tests via `pytest`
- frontend production build via `npm run build`
- API smoke checks for graph load, node detail, query, add node, add edge, export, and reset

Visual browser interactions still depend on opening the running app locally, but the underlying API flow and frontend build path have been validated.
