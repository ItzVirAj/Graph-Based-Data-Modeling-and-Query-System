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
  highlight_reason?: string;
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

export interface GeneratedQuery {
  type: "graph_traversal" | "sql" | string;
  query_string: string;
  structured_form: Record<string, unknown>;
  explanation: string;
  sql_query?: string;
  graph_query_string?: string;
}

export interface QueryMemory {
  turn_count: number;
  max_turns: number;
  last_entities: Array<{ entity_type: string; entity_id: string }>;
}

export interface EdgePath {
  edge_id: string;
  source: string;
  target: string;
  relationship?: string;
  edge_type?: string;
}

export interface QueryRawData {
  graph_result?: {
    operation?: string;
    records?: unknown[];
    path_edges?: EdgePath[];
    [key: string]: unknown;
  };
  sql_result?: {
    query?: string;
    rows?: Array<Record<string, unknown>>;
    error?: string | null;
  };
}

export interface QueryResponse {
  answer: string;
  relevant_node_ids: string[];
  raw_data: QueryRawData | null;
  generated_query: GeneratedQuery | null;
  execution_time_ms: number;
  session_id: string;
  memory?: QueryMemory | null;
}

export interface ClusterResponse {
  clusters: Array<{
    cluster_id: string;
    size: number;
    node_ids: string[];
  }>;
}

export interface ImportanceNode {
  node_key: string;
  entity_id: string;
  entity_type: string;
  label?: string;
  importance_score: number;
}

export interface ImportanceResponse {
  nodes: ImportanceNode[];
}

export interface BrokenFlowsResponse {
  complete: string[];
  missing_delivery: string[];
  missing_invoice: string[];
  missing_payment: string[];
}


export interface AnalyticsView {
  mode: "default" | "clusters" | "importance" | "broken_flows";
  clusterMap?: Record<string, string>;
  importanceMap?: Record<string, number>;
  brokenNodeIds?: string[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  relevantNodeIds?: string[];
  relevantEdgeIds?: string[];
  rawData?: QueryRawData | null;
  generatedQuery?: GeneratedQuery | null;
  executionTimeMs?: number;
  rejected?: boolean;
}
