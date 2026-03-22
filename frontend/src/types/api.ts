export type EntityType =
  | "order"
  | "delivery"
  | "invoice"
  | "payment"
  | "customer"
  | "product"
  | "address"
  | string;

export interface CytoscapeNodeData {
  id: string;
  node_key?: string;
  entity_id: string;
  entity_type: EntityType;
  label?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface CytoscapeEdgeData {
  id: string;
  source: string;
  target: string;
  edge_type?: string;
  relationship?: string;
  [key: string]: unknown;
}

export interface CytoscapeElement<T> {
  data: T;
}

export interface GraphPayload {
  nodes: CytoscapeElement<CytoscapeNodeData>[];
  edges: CytoscapeElement<CytoscapeEdgeData>[];
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
}

export interface NodeSummary {
  nodeId: string;
  nodeKey: string;
  entityId: string;
  entityType: EntityType;
  label: string;
}

export interface NodeDetailResponse {
  node: CytoscapeNodeData;
  neighbors: CytoscapeNodeData[];
}

export interface AddNodePayload {
  id: string;
  type: string;
  metadata: Record<string, unknown>;
}

export interface AddEdgePayload {
  source: string;
  target: string;
  relationship: string;
}

export interface QueryResponse {
  answer: string;
  relevant_node_ids: string[];
  raw_data: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  relevantNodeIds?: string[];
  rawData?: unknown;
  rejected?: boolean;
}
