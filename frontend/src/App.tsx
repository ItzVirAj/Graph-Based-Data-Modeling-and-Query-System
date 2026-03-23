import { useCallback, useMemo, useState } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { GraphViewer } from "./components/GraphViewer";
import { NodeDetail } from "./components/NodeDetail";
import { Toolbar } from "./components/Toolbar";
import type { AnalyticsView, NodeSummary } from "./types/api";

interface QueryHighlightState {
  edgeIds: string[];
  nodeIds: string[];
  primaryNodeId: string | null;
  reasons: Record<string, string>;
}

const DEFAULT_ANALYTICS_VIEW: AnalyticsView = { mode: "default" };

export default function App() {
  const [selectedNode, setSelectedNode] = useState<NodeSummary | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [expandTarget, setExpandTarget] = useState<{ nodeId: string; depth: number } | null>(null);
  const [highlightState, setHighlightState] = useState<QueryHighlightState>({ edgeIds: [], nodeIds: [], primaryNodeId: null, reasons: {} });
  const [statusMessage, setStatusMessage] = useState("Graph loaded from the backend API.");
  const [isConsoleOpen, setIsConsoleOpen] = useState(true);
  const [chatScrollNodeId, setChatScrollNodeId] = useState<string | null>(null);
  const [analyticsView, setAnalyticsView] = useState<AnalyticsView>(DEFAULT_ANALYTICS_VIEW);

  const viewerKey = useMemo(
    () => `${refreshToken}:${expandTarget?.nodeId ?? "full"}:${expandTarget?.depth ?? 0}`,
    [expandTarget?.depth, expandTarget?.nodeId, refreshToken],
  );

  const handleClearHighlights = useCallback(() => {
    setHighlightState({ edgeIds: [], nodeIds: [], primaryNodeId: null, reasons: {} });
  }, []);

  const handleGraphChanged = (message: string) => {
    setStatusMessage(message);
    setRefreshToken((current) => current + 1);
  };

  const handleExpand = (nodeId: string, depth: number) => {
    setStatusMessage(`Expanded graph around ${nodeId} with depth ${depth}.`);
    setExpandTarget({ nodeId, depth });
    setHighlightState({ edgeIds: [], nodeIds: [nodeId], primaryNodeId: nodeId, reasons: { [nodeId]: `Matched: id=${nodeId}` } });
  };

  const handleShowFullGraph = () => {
    setStatusMessage("Showing the full graph.");
    setExpandTarget(null);
    setRefreshToken((current) => current + 1);
  };

  const handleApplyQueryFocus = (payload: QueryHighlightState) => {
    setHighlightState(payload);
  };

  const handleAnalyticsChange = (view: AnalyticsView, message: string) => {
    setAnalyticsView(view);
    setStatusMessage(message);
  };

  return (
    <div className="h-screen overflow-hidden bg-[#f7f7f5] text-slate-900">
      <header className="flex h-20 items-center justify-between border-b border-slate-200 bg-white px-7">
        <div className="flex items-center gap-4">
          <button
            className="flex h-11 items-center justify-center rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            onClick={() => setIsConsoleOpen((current) => !current)}
            type="button"
          >
            Menu
          </button>
          <div className="h-8 w-px bg-slate-200" />
          <div className="flex items-center gap-2 text-[18px]">
            <span className="text-slate-400">Mapping</span>
            <span className="text-slate-300">/</span>
            <span className="font-semibold text-slate-950">Order to Cash</span>
          </div>
        </div>
      </header>

      <div className="flex h-[calc(100vh-5rem)] overflow-hidden p-4">
        <section className="relative min-w-0 flex-1 overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-sm">
          <div className="absolute left-4 top-4 z-20 flex items-center gap-3">
            <button
              className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
              onClick={() => setIsConsoleOpen((current) => !current)}
              type="button"
            >
              {isConsoleOpen ? "Minimize" : "Open Console"}
            </button>
            <button
              className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800"
              onClick={handleShowFullGraph}
              type="button"
            >
              Show Full Graph
            </button>
          </div>

          <div
            className={`absolute left-4 top-20 z-20 h-[calc(100%-6rem)] overflow-hidden rounded-[24px] border border-slate-200 bg-white/95 shadow-xl backdrop-blur transition-all duration-300 ${
              isConsoleOpen ? "w-full max-w-[360px] opacity-100" : "pointer-events-none w-0 opacity-0"
            }`}
          >
            <div className="flex h-full min-h-0 flex-col overflow-hidden p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Console</p>
                  <h1 className="mt-1 text-2xl font-semibold text-slate-950">Order to Cash</h1>
                </div>
                <button
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
                  onClick={() => setIsConsoleOpen(false)}
                  type="button"
                >
                  Hide
                </button>
              </div>

              <div className="shrink-0">
                <Toolbar onAnalyticsChange={handleAnalyticsChange} onGraphChanged={handleGraphChanged} onShowFullGraph={handleShowFullGraph} />
              </div>

              <div className="mt-4 min-h-0 flex-1">
                <NodeDetail key={selectedNode?.nodeKey ?? "empty"} onExpand={handleExpand} selectedNode={selectedNode} />
              </div>

              <div className="mt-4 shrink-0 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                {statusMessage}
              </div>
            </div>
          </div>

          <GraphViewer
            key={viewerKey}
            analyticsView={analyticsView}
            expandTarget={expandTarget}
            focusedNodeId={highlightState.primaryNodeId}
            highlightedEdges={highlightState.edgeIds}
            highlightedNodes={highlightState.nodeIds}
            highlightReasons={highlightState.reasons}
            onClearHighlights={handleClearHighlights}
            onHighlightedNodeTap={setChatScrollNodeId}
            onNodeSelect={setSelectedNode}
            refreshToken={refreshToken}
          />
        </section>

        <ChatPanel
          highlightedNodes={highlightState.nodeIds}
          onApplyQueryFocus={handleApplyQueryFocus}
          onClearHighlights={handleClearHighlights}
          onResetConversationView={() => {
            handleClearHighlights();
            setChatScrollNodeId(null);
          }}
          onStatusChange={setStatusMessage}
          scrollToNodeId={chatScrollNodeId}
        />
      </div>
    </div>
  );
}
