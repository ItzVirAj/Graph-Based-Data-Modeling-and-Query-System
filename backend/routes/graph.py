from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.graph_store import graph_store

router = APIRouter(prefix="/api", tags=["graph"])
logger = logging.getLogger(__name__)


class NodeCreateRequest(BaseModel):
    id: str
    type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeCreateRequest(BaseModel):
    source: str
    target: str
    relationship: str


def _apply_limit(payload: dict[str, list[dict[str, Any]]], limit: int | None) -> dict[str, list[dict[str, Any]]]:
    if limit is None or limit <= 0 or len(payload["nodes"]) <= limit:
        return payload

    nodes = payload["nodes"][:limit]
    allowed_ids = {node["data"]["id"] for node in nodes}
    edges = [
        edge
        for edge in payload["edges"]
        if edge["data"]["source"] in allowed_ids and edge["data"]["target"] in allowed_ids
    ]
    return {"nodes": nodes, "edges": edges}


@router.get("/graph")
def get_graph(limit: int | None = Query(default=None, ge=1)) -> dict[str, list[dict[str, Any]]]:
    payload = graph_store.graph.to_json()
    return _apply_limit(payload, limit)


@router.get("/graph/stats")
def get_graph_stats() -> dict[str, Any]:
    return graph_store.graph.get_stats()


@router.get("/node/{node_id}")
def get_node(node_id: str) -> dict[str, Any]:
    node = graph_store.graph.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    return {
        "node": node,
        "neighbors": graph_store.graph.get_neighbors(node_id),
    }


@router.get("/node/{node_id}/subgraph")
def get_node_subgraph(node_id: str, depth: int = Query(default=2, ge=1, le=10)) -> dict[str, list[dict[str, Any]]]:
    node = graph_store.graph.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    subgraph = graph_store.graph.get_subgraph(node_id, depth)
    return graph_store.graph.serialize_graph(subgraph)


@router.post("/graph/node", status_code=201)
def create_graph_node(request: NodeCreateRequest) -> dict[str, Any]:
    logger.info("Adding node %s of type %s", request.id, request.type)
    node = graph_store.graph.add_node(request.id, request.type, request.metadata)
    return {"node": node}


@router.post("/graph/edge", status_code=201)
def create_graph_edge(request: EdgeCreateRequest) -> dict[str, Any]:
    logger.info("Adding edge %s -> %s (%s)", request.source, request.target, request.relationship)
    edge = graph_store.graph.add_edge(request.source, request.target, request.relationship)
    return {"edge": edge}


@router.delete("/graph/reset")
def reset_graph() -> dict[str, Any]:
    logger.info("Resetting graph from original dataset")
    builder = graph_store.reset()
    return {
        "message": "Graph rebuilt from source data",
        "stats": builder.get_stats(),
    }


@router.get("/graph/export")
def export_graph() -> JSONResponse:
    payload = graph_store.graph.to_json()
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="sap-o2c-graph.json"'},
    )
