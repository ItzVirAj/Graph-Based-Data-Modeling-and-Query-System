from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.memory import clear_session_memory, get_session_memory
from backend.agents.query_pipeline import QueryPipeline
from backend.services.graph_store import graph_store

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None


def _resolve_session_id(body_session_id: str | None, header_session_id: str | None) -> str:
    return header_session_id or body_session_id or str(uuid4())


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/query")
async def query_graph(request: QueryRequest, x_session_id: str | None = Header(default=None)) -> dict[str, Any]:
    session_id = _resolve_session_id(request.session_id, x_session_id)
    pipeline = QueryPipeline(graph_store.graph, graph_store.sql_engine)
    memory = get_session_memory(session_id)
    payload = await pipeline.run(request.question, memory=memory)
    payload["session_id"] = session_id
    return payload


@router.post("/query/stream")
async def stream_query_graph(request: QueryRequest, x_session_id: str | None = Header(default=None)) -> StreamingResponse:
    session_id = _resolve_session_id(request.session_id, x_session_id)
    pipeline = QueryPipeline(graph_store.graph, graph_store.sql_engine)
    memory = get_session_memory(session_id)

    async def event_stream():
        yield _sse("status", {"stage": "session", "message": "Session ready", "session_id": session_id})
        async for event, payload in pipeline.stream(request.question, memory=memory):
            payload.setdefault("session_id", session_id)
            yield _sse(event, payload)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/session/{session_id}", status_code=204)
def clear_session(session_id: str) -> Response:
    clear_session_memory(session_id)
    return Response(status_code=204)
