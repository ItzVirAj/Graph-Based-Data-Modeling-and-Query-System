import axios from "axios";

import type {
  AddEdgePayload,
  AddNodePayload,
  BrokenFlowsResponse,
  ClusterResponse,
  GraphPayload,
  GraphStats,
  ImportanceResponse,
  NodeDetailResponse,
  QueryResponse,
} from "../types/api";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";

export const API_BASE_URL = configuredApiBaseUrl;

function buildApiUrl(path: string): string {
  if (!API_BASE_URL) {
    return path;
  }

  return new URL(path, API_BASE_URL).toString();
}

const api = axios.create({
  baseURL: API_BASE_URL || undefined,
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

export async function fetchClusters(): Promise<ClusterResponse> {
  const response = await api.get<ClusterResponse>("/api/graph/clusters");
  return response.data;
}

export async function fetchImportance(limit = 25): Promise<ImportanceResponse> {
  const response = await api.get<ImportanceResponse>("/api/graph/importance", {
    params: { limit },
  });
  return response.data;
}

export async function fetchBrokenFlows(): Promise<BrokenFlowsResponse> {
  const response = await api.get<BrokenFlowsResponse>("/api/graph/broken-flows");
  return response.data;
}

export async function clearSession(sessionId: string) {
  await api.delete(`/api/session/${sessionId}`);
}

export async function queryGraph(question: string, sessionId: string): Promise<QueryResponse> {
  const response = await api.post<QueryResponse>("/api/query", { question, session_id: sessionId }, {
    headers: { "X-Session-Id": sessionId },
  });
  return response.data;
}

export interface StreamHandlers {
  onStatus?: (payload: Record<string, unknown>) => void;
  onQuery?: (payload: Record<string, unknown>) => void;
  onToken?: (payload: Record<string, unknown>) => void;
  onComplete?: (payload: QueryResponse) => void;
}

function parseSseChunk(chunk: string, emit: (eventName: string, payload: Record<string, unknown>) => void) {
  const events = chunk.split("\n\n").filter(Boolean);
  for (const eventBlock of events) {
    const lines = eventBlock.split("\n");
    const eventLine = lines.find((line) => line.startsWith("event:"));
    const dataLine = lines.find((line) => line.startsWith("data:"));
    if (!eventLine || !dataLine) {
      continue;
    }
    const eventName = eventLine.replace("event:", "").trim();
    const dataText = dataLine.replace("data:", "").trim();
    try {
      emit(eventName, JSON.parse(dataText) as Record<string, unknown>);
    } catch {
      emit(eventName, { text: dataText });
    }
  }
}

export async function streamGraphQuery(question: string, sessionId: string, handlers: StreamHandlers): Promise<void> {
  const response = await fetch(buildApiUrl("/api/query/stream"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Session-Id": sessionId,
    },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (!response.ok || !response.body) {
    throw new Error("Streaming request failed.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      parseSseChunk(`${part}\n\n`, (eventName, payload) => {
        if (eventName === "status") {
          handlers.onStatus?.(payload);
        } else if (eventName === "query") {
          handlers.onQuery?.(payload);
        } else if (eventName === "token") {
          handlers.onToken?.(payload);
        } else if (eventName === "complete") {
          handlers.onComplete?.(payload as unknown as QueryResponse);
        }
      });
    }
  }
}

export { api };
