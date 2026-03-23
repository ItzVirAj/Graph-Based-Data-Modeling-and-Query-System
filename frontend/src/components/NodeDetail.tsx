import { useEffect, useState } from "react";

import { fetchNode } from "../services/api";
import type { CytoscapeNodeData, NodeSummary } from "../types/api";

interface NodeDetailProps {
  onExpand: (nodeId: string, depth: number) => void;
  selectedNode: NodeSummary | null;
}

interface DetailState {
  neighbors: CytoscapeNodeData[];
  node: CytoscapeNodeData;
}

export function NodeDetail({ onExpand, selectedNode }: NodeDetailProps) {
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadNode() {
      if (!selectedNode) {
        setDetail(null);
        setError(null);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const response = await fetchNode(selectedNode.entityId);
        if (isActive) {
          setDetail(response);
        }
      } catch (loadError) {
        if (isActive) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load node details");
        }
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    }

    void loadNode();

    return () => {
      isActive = false;
    };
  }, [selectedNode]);

  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-200 bg-white p-4">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Inspector</p>
        <h2 className="mt-1 text-lg font-semibold text-slate-950">Node Detail</h2>
      </div>

      {!selectedNode ? <p className="text-sm leading-6 text-slate-500">Click a node in the graph to inspect its metadata and connected entities.</p> : null}
      {loading ? <p className="text-sm text-sky-600">Loading node details...</p> : null}
      {error ? <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div> : null}

      {detail ? (
        <div className="min-h-0 space-y-4 overflow-hidden">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{detail.node.entity_type}</p>
                <h3 className="mt-1 text-lg font-semibold text-slate-950">{detail.node.label ?? detail.node.entity_id}</h3>
                <p className="mt-1 text-xs text-slate-500">Node key: {detail.node.node_key ?? detail.node.id}</p>
              </div>
              <button className="rounded-xl bg-slate-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800" onClick={() => onExpand(detail.node.entity_id, 2)} type="button">Expand</button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <h4 className="mb-3 text-sm font-semibold text-slate-900">Metadata</h4>
            <div className="max-h-48 space-y-2 overflow-auto pr-2 scrollbar-thin">
              {Object.entries(detail.node.metadata ?? {}).map(([key, value]) => (
                <div key={key} className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
                  <div className="font-medium text-slate-700">{key}</div>
                  <div className="mt-1 break-words text-slate-500">{typeof value === "object" ? JSON.stringify(value) : String(value)}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <h4 className="mb-3 text-sm font-semibold text-slate-900">Connected Nodes</h4>
            <div className="max-h-40 space-y-2 overflow-auto pr-2 scrollbar-thin">
              {detail.neighbors.map((neighbor) => (
                <div key={neighbor.node_key ?? neighbor.id} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                  <div className="text-sm font-medium text-slate-800">{neighbor.label ?? neighbor.entity_id}</div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{neighbor.entity_type}</div>
                </div>
              ))}
              {!detail.neighbors.length ? <p className="text-sm text-slate-500">No connected nodes found.</p> : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
