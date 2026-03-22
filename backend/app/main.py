from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.services.graph_store import graph_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    graph_store.initialize()
    yield


app = FastAPI(
    title="SAP O2C Graph Query Backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
