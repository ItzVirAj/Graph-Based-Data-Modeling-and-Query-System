# SAP O2C Graph Query System

Scaffold for a graph-based data modeling and query platform over SAP Order-to-Cash datasets.

This repository is intentionally initialized without implementation code. It contains:

- a Python backend scaffold for ingestion, normalization, graph construction, query orchestration, and APIs
- a React + Vite + TypeScript frontend scaffold for graph exploration and LLM-assisted querying
- shared contracts/config placeholders for normalized entities, graph metadata, and dataset mappings
- documentation placeholders for data dictionary, graph model, and query flows

## Scope

The raw data currently available in [`sap-o2c-data`](/c:/Projects/DodgeAI-Assignment/sap-o2c-data) contains 49 JSONL files across 18 logical dataset groups:

- `sales_order_headers`
- `sales_order_items`
- `sales_order_schedule_lines`
- `outbound_delivery_headers`
- `outbound_delivery_items`
- `billing_document_headers`
- `billing_document_items`
- `billing_document_cancellations`
- `journal_entry_items_accounts_receivable`
- `payments_accounts_receivable`
- `business_partners`
- `business_partner_addresses`
- `customer_company_assignments`
- `customer_sales_area_assignments`
- `products`
- `product_descriptions`
- `product_plants`
- `product_storage_locations`
- `plants`

The observed business flow is:

`Customer -> Sales Order -> Delivery -> Invoice -> AR Journal / Payment`

Supporting master-data domains:

- customer and address
- product and product description
- plant and storage location
- customer company and sales area assignments

## Target Architecture

```text
                        +----------------------+
                        |   Raw SAP O2C Files  |
                        | CSV / JSON / JSONL   |
                        +----------+-----------+
                                   |
                                   v
                    +--------------+---------------+
                    | Ingestion + Schema Inspection |
                    | file loaders, profiling,      |
                    | source metadata capture       |
                    +--------------+---------------+
                                   |
                                   v
                    +--------------+---------------+
                    | Normalization Layer           |
                    | canonical IDs, typed fields,  |
                    | entity mapping, validation    |
                    +--------------+---------------+
                                   |
                 +-----------------+------------------+
                 |                                    |
                 v                                    v
    +------------+------------+          +------------+------------+
    | Normalized Entity Store |          | Graph Builder           |
    | orders, deliveries,     |          | NetworkX nodes/edges,   |
    | invoices, payments,     |          | lineage and traversal   |
    | customers, products     |          +------------+------------+
    +------------+------------+                       |
                 |                                    v
                 |                     +--------------+---------------+
                 |                     | Query Engine + LLM Agents     |
                 |                     | intent parsing, tool routing, |
                 |                     | graph + tabular responses     |
                 |                     +--------------+---------------+
                 |                                    |
                 +--------------------+---------------+
                                      |
                                      v
                        +-------------+--------------+
                        | FastAPI Backend            |
                        | datasets, graph, lineage,  |
                        | query, health endpoints    |
                        +-------------+--------------+
                                      |
                                      v
                        +-------------+--------------+
                        | React UI (Vite + TS)       |
                        | Cytoscape graph canvas,    |
                        | dataset panels, query UX   |
                        +----------------------------+
```

## Repository Layout

```text
.
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |   `-- routes/
|   |   |-- agents/
|   |   |-- core/
|   |   |-- graph/
|   |   |-- ingestion/
|   |   |-- models/
|   |   |-- normalization/
|   |   |-- repositories/
|   |   |-- schemas/
|   |   `-- utils/
|   `-- tests/
|-- docs/
|-- frontend/
|   |-- public/
|   `-- src/
|       |-- app/
|       |-- components/
|       |-- features/
|       |-- hooks/
|       |-- lib/
|       |-- pages/
|       |-- services/
|       |-- styles/
|       `-- types/
|-- scripts/
|-- shared/
|   |-- config/
|   `-- contracts/
`-- sap-o2c-data/
```

## Backend Responsibilities

- `app/ingestion`: read CSV, JSON, and JSONL; capture schema profiles and source metadata
- `app/normalization`: map raw fields to canonical entities and validate normalized records
- `app/graph`: build and query the NetworkX graph plus lineage structures
- `app/agents`: LLM orchestration layer for natural-language query translation and tool use
- `app/api/routes`: FastAPI endpoints for health, datasets, graph views, lineage, and query execution
- `app/models` and `app/schemas`: internal domain models and API payload definitions

## Frontend Responsibilities

- graph visualization with Cytoscape.js
- natural-language query entry and results display
- dataset and entity exploration panels
- lineage and relationship inspection
- API client and typed contract layer

## Initial Normalized Entity Model

Planned canonical entities:

- `customer`
- `address`
- `customer_company`
- `customer_sales_area`
- `product`
- `product_description`
- `plant`
- `product_plant`
- `product_storage_location`
- `sales_order`
- `sales_order_item`
- `sales_order_schedule_line`
- `delivery`
- `delivery_item`
- `invoice`
- `invoice_item`
- `ar_document`
- `payment`

Key business identifiers expected across the system:

- `customer_id`
- `address_id`
- `product_id`
- `plant_id`
- `order_id`
- `order_item_id`
- `delivery_id`
- `delivery_item_id`
- `invoice_id`
- `invoice_item_id`
- `accounting_document_id`
- `payment_document_id`

## Planned API Surface

- `GET /health`
- `GET /datasets`
- `GET /datasets/{dataset_name}/schema`
- `GET /graph/summary`
- `POST /graph/subgraph`
- `GET /lineage/{entity_type}/{entity_id}`
- `POST /query`

## Dependencies

Dependency manifests are intentionally limited to:

- [`backend/requirements.txt`](/c:/Projects/DodgeAI-Assignment/backend/requirements.txt)
- [`frontend/package.json`](/c:/Projects/DodgeAI-Assignment/frontend/package.json)

All other source and config files are placeholders only at this stage.

## Next Step

After reviewing the scaffold, initialize version control:

```bash
git init && git add . && git commit -m "chore: initial project scaffold"
```
