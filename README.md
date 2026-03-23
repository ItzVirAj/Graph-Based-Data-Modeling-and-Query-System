# SAP O2C Graph Query System

A full-stack graph exploration system for SAP Order-to-Cash data. The backend ingests raw O2C datasets, normalizes business entities, builds an in-memory NetworkX graph, mirrors the normalized entities into SQLite, and exposes graph/query APIs through FastAPI. The frontend renders the graph with Cytoscape.js and adds a natural-language copilot for guided exploration.

## What This Project Does

- Loads SAP O2C datasets from `sap-o2c-data`
- Normalizes Orders, Deliveries, Invoices, Payments, Customers, Products, Addresses, Plants, and Journal Entries
- Builds a typed relationship graph in NetworkX
- Loads normalized entities into an in-memory SQLite engine for transparent SQL translation
- Supports natural-language querying with Gemini `gemini-3.1-flash-lite-preview`
- Streams query progress and answer generation back to the UI
- Maintains lightweight per-session conversation memory for follow-up questions
- Visualizes graph structure, node metadata, analytics overlays, and query-driven highlights in React + Cytoscape.js

## Dataset Scope

The current dataset covers the order-to-cash chain:

`Customer -> Order -> Delivery -> Invoice -> JournalEntry/Payment`

Supported graph node types:

- `Order`
- `Delivery`
- `Invoice`
- `Payment`
- `Customer`
- `Product`
- `Address`
- `Plant`
- `JournalEntry`

Primary edge patterns:

- `Order -> Delivery`
- `Delivery -> Invoice`
- `Invoice -> Payment`
- `Invoice -> JournalEntry`
- `Order -> Customer`
- `Order -> Product`
- `Delivery -> Product`
- `Customer -> Address`
- `Customer -> Delivery`
- `Delivery -> Plant`
- `Product -> Plant`

Dataset note:

- The provided SAP data contains Sales Orders, not Purchase Orders.
- The assignment mentions Purchase Orders, but the available source files use Sales Order terminology.
- `Order -> Product` models the available SalesOrderItem -> Material relationship.

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
            +-------------------+------------------+
                                |
                                v
+-----------------------+   +-----------------------+
| NetworkX Graph        |   | SQLite SQL Engine     |
| typed nodes + edges   |   | normalized tables     |
+-----------+-----------+   +-----------+-----------+
            \___________________________/
                        |
                        v
+---------------------------------------------------+
| Query Pipeline                                     |
| guardrail -> NL translation -> graph + SQL exec   |
| conversation memory -> answer generation          |
| sync response + SSE streaming                     |
+---------------------------+-----------------------+
                            |
                            v
+---------------------------+-----------------------+
| FastAPI API                                       |
| graph routes | analytics | query | stream | session |
+---------------------------------------------------+
```

## Repository Layout

```text
backend/
  agents/              LLM client, memory, schema context, NL query pipeline
  logs/                LLM session markdown logs
  prompts/             example natural-language prompts
  routes/              FastAPI route modules
  services/            data loading, graph building, SQL engine, analytics, graph store
  tests/               backend tests
  main.py              FastAPI entrypoint
frontend/
  src/components/      graph viewer, toolbar, detail panel, chat panel
  src/services/        API client
  src/types/           frontend API and graph typings
sap-o2c-data/          raw SAP O2C files
```

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..
copy .env.example .env
uvicorn backend.main:app --reload
```

Backend API is available at `http://localhost:8000`.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend is available at `http://localhost:5173`.

## Environment Variables

Create a root `.env` file from `.env.example`.

```env
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=
VITE_API_BASE_URL=http://localhost:8000
```

Notes:

- Gemini is the active provider.
- If `GEMINI_API_KEY` is missing or quota-limited, the backend falls back to deterministic mock translation/answer generation.
- The current model target is `gemini-3.1-flash-lite-preview`.

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

## Logging

Every query appends a markdown entry to `backend/logs/llm_sessions.md` with:

- timestamp
- user question
- guardrail result
- translation prompt and response
- parsed structured query
- execution summary
- answer prompt and response
- final answer or error details

## Screenshots

Add screenshots here as the UI is finalized.

- `docs/screenshots/graph-overview.png`
- `docs/screenshots/node-detail.png`
- `docs/screenshots/chat-query.png`
- `docs/screenshots/subgraph-highlight.png`
- `docs/screenshots/sql-translation.png`
- `docs/screenshots/analytics-overlays.png`
