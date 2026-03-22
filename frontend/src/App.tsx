import { useMemo, useState } from "react";

import { GraphViewer } from "./components/GraphViewer";
import { NodeDetail } from "./components/NodeDetail";
import { Toolbar } from "./components/Toolbar";
import type { NodeSummary } from "./types/api";

export default function App() {
  const [selectedNode, setSelectedNode] = useState<NodeSummary | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [expandTarget, setExpandTarget] = useState<{ nodeId: string; depth: number } | null>(null);
  const [statusMessage, setStatusMessage] = useState("Graph loaded from the backend API.");

  const viewerKey = useMemo(
    () => `${refreshToken}:${expandTarget?.nodeId ?? "full"}:${expandTarget?.depth ?? 0}`,
    [expandTarget?.depth, expandTarget?.nodeId, refreshToken],
  );

  const handleGraphChanged = (message: string) => {
    setStatusMessage(message);
    setRefreshToken((current) => current + 1);
  };

  const handleExpand = (nodeId: string, depth: number) => {
    setStatusMessage(`Expanded graph around ${nodeId} with depth ${depth}.`);
    setExpandTarget({ nodeId, depth });
  };

  const handleShowFullGraph = () => {
    setStatusMessage("Showing the full graph.");
    setExpandTarget(null);
    setRefreshToken((current) => current + 1);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-[1800px] flex-col lg:flex-row">
        <aside className="w-full border-b border-slate-800 bg-slate-900/95 p-4 lg:w-[380px] lg:border-b-0 lg:border-r">
          <div className="flex h-full flex-col gap-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4 shadow-2xl shadow-slate-950/40">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-400">
                SAP O2C Graph Console
              </p>
              <h1 className="mt-2 text-2xl font-semibold text-white">Relationship Explorer</h1>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Explore orders, deliveries, invoices, payments, customers, products, and
                addresses through one interactive graph.
              </p>
            </div>

            <Toolbar onGraphChanged={handleGraphChanged} onShowFullGraph={handleShowFullGraph} />

            <NodeDetail
              key={selectedNode?.nodeKey ?? "empty"}
              onExpand={handleExpand}
              selectedNode={selectedNode}
            />

            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 px-4 py-3 text-sm text-slate-400">
              {statusMessage}
            </div>
          </div>
        </aside>

        <main className="relative flex-1 bg-[radial-gradient(circle_at_top,_rgba(6,182,212,0.12),_transparent_35%),linear-gradient(180deg,_#0f172a_0%,_#020617_100%)]">
          <GraphViewer
            key={viewerKey}
            expandTarget={expandTarget}
            onNodeSelect={setSelectedNode}
            refreshToken={refreshToken}
          />
        </main>
      </div>
    </div>
  );
}
