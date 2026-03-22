import axios from "axios";

import type {
  AddEdgePayload,
  AddNodePayload,
  GraphPayload,
  GraphStats,
  NodeDetailResponse,
} from "../types/api";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  headers: {
    "Content-Type": "application/json",
  },
});

export async function fetchGraph(limit?: number): Promise<GraphPayload> {
  const response = await api.get<GraphPayload>("/api/graph", {
    params: limit ? { limit } : undefined,
  });
  return response.data;
}

export async function fetchGraphStats(): Promise<GraphStats> {
  const response = await api.get<GraphStats>("/api/graph/stats");
  return response.data;
}

export async function fetchNode(nodeId: string): Promise<NodeDetailResponse> {
  const response = await api.get<NodeDetailResponse>(`/api/node/${nodeId}`);
  return response.data;
}

export async function fetchSubgraph(nodeId: string, depth: number): Promise<GraphPayload> {
  const response = await api.get<GraphPayload>(`/api/node/${nodeId}/subgraph`, {
    params: { depth },
  });
  return response.data;
}

export async function addGraphNode(payload: AddNodePayload) {
  const response = await api.post("/api/graph/node", payload);
  return response.data;
}

export async function addGraphEdge(payload: AddEdgePayload) {
  const response = await api.post("/api/graph/edge", payload);
  return response.data;
}

export async function resetGraph() {
  const response = await api.delete("/api/graph/reset");
  return response.data;
}

export async function exportGraphJson(): Promise<Blob> {
  const response = await api.get("/api/graph/export", {
    responseType: "blob",
  });
  return response.data;
}

export { api };
