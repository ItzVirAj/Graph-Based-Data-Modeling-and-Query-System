from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.graph_store import graph_store

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: str


@router.post("/query")
def query_graph(request: QueryRequest) -> dict[str, Any]:
    stats = graph_store.graph.get_stats()
    return {
        "question": request.question,
        "answer": "Mock response: natural language query handling will be connected to LLM agents in the next step.",
        "grounding": {
            "graph_loaded": True,
            "total_nodes": stats["total_nodes"],
            "total_edges": stats["total_edges"],
        },
    }
