from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.query_pipeline import QueryPipeline
from backend.services.graph_store import graph_store

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: str


@router.post("/query")
async def query_graph(request: QueryRequest) -> dict[str, Any]:
    pipeline = QueryPipeline(graph_store.graph)
    return await pipeline.run(request.question)
