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
    <section className="min-h-[320px] rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-2xl shadow-slate-950/30">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Inspector</p>
        <h2 className="mt-1 text-lg font-semibold text-white">Node Detail</h2>
      </div>

      {!selectedNode ? (
        <p className="text-sm leading-6 text-slate-400">
          Click a node in the graph to inspect its metadata, relationships, and connected entities.
        </p>
      ) : null}

      {loading ? <p className="text-sm text-cyan-300">Loading node details...</p> : null}

      {error ? (
        <div className="rounded-xl border border-rose-500/40 bg-rose-950/70 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {detail ? (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-cyan-400">{detail.node.entity_type}</p>
                <h3 className="mt-1 text-lg font-semibold text-white">
                  {detail.node.label ?? detail.node.entity_id}
                </h3>
                <p className="mt-1 text-xs text-slate-500">Node key: {detail.node.node_key ?? detail.node.id}</p>
              </div>
              <button
                className="rounded-xl bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
                onClick={() => onExpand(detail.node.entity_id, 2)}
                type="button"
              >
                Expand
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <h4 className="mb-3 text-sm font-semibold text-white">Metadata</h4>
            <div className="max-h-64 space-y-2 overflow-auto pr-2 scrollbar-thin">
              {Object.entries(detail.node.metadata ?? {}).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm"
                >
                  <div className="font-medium text-slate-300">{key}</div>
                  <div className="mt-1 break-words text-slate-400">
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
            <h4 className="mb-3 text-sm font-semibold text-white">Connected Nodes</h4>
            <div className="max-h-56 space-y-2 overflow-auto pr-2 scrollbar-thin">
              {detail.neighbors.map((neighbor) => (
                <div
                  key={neighbor.node_key ?? neighbor.id}
                  className="rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2"
                >
                  <div className="text-sm font-medium text-slate-200">
                    {neighbor.label ?? neighbor.entity_id}
                  </div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">
                    {neighbor.entity_type}
                  </div>
                </div>
              ))}
              {!detail.neighbors.length ? (
                <p className="text-sm text-slate-500">No connected nodes found.</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
