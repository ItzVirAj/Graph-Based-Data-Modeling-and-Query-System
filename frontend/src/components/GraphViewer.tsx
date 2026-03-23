import { useEffect, useRef, useState } from "react";

import cytoscape, { type Core, type ElementDefinition, type NodeSingular } from "cytoscape";
import coseBilkent from "cytoscape-cose-bilkent";

import { fetchGraph, fetchGraphStats, fetchSubgraph } from "../services/api";
import type { CytoscapeNodeData, GraphPayload, GraphStats, NodeSummary } from "../types/api";
import { DEFAULT_NODE_COLOR, NODE_TYPE_COLORS } from "../types/graph";

cytoscape.use(coseBilkent);

interface GraphViewerProps {
  expandTarget: { nodeId: string; depth: number } | null;
  focusedNodeId: string | null;
  highlightedNodes: string[];
  onClearHighlights: () => void;
  onNodeSelect: (node: NodeSummary | null) => void;
  refreshToken: number;
}

interface GraphOverlayCardProps {
  node: CytoscapeNodeData;
  connections: number;
}

function toElements(payload: GraphPayload): ElementDefinition[] {
  const nodes = payload.nodes.map((node) => ({ data: node.data }));
  const edges = payload.edges.map((edge) => ({ data: edge.data }));
  return [...nodes, ...edges];
}

function normalizeHighlightId(value: string): string {
  const trimmed = value.trim();
  const parts = trimmed.split(":");
  return parts[parts.length - 1] ?? trimmed;
}

function buildNodeSummary(node: NodeSingular): NodeSummary {
  return {
    nodeId: node.data("entity_id"),
    nodeKey: node.id(),
    entityId: node.data("entity_id"),
    entityType: node.data("entity_type"),
    label: node.data("label") ?? node.data("entity_id"),
  };
}

function GraphOverlayCard({ node, connections }: GraphOverlayCardProps) {
  const metadataEntries = Object.entries(node.metadata ?? {});
  const visibleEntries = metadataEntries.slice(0, 14);
  const hiddenCount = Math.max(metadataEntries.length - visibleEntries.length, 0);

  return (
    <div className="absolute left-1/2 top-16 z-20 max-h-[420px] w-[320px] -translate-x-1/2 overflow-hidden rounded-[20px] border border-slate-200 bg-white p-4 shadow-2xl">
      <div className="mb-3">
        <h3 className="text-lg font-semibold text-slate-900">{node.label ?? node.entity_id}</h3>
        <p className="text-sm text-slate-500">Entity: {node.entity_type}</p>
      </div>

      <div className="max-h-[300px] space-y-1 overflow-auto pr-1 text-sm text-slate-700">
        {visibleEntries.map(([key, value]) => (
          <div key={key}>
            <span className="font-medium text-slate-900">{key}:</span>{" "}
            <span className="break-words text-slate-600">{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
          </div>
        ))}
        {hiddenCount > 0 ? (
          <div className="pt-1 text-xs italic text-slate-400">Additional fields hidden for readability</div>
        ) : null}
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-600">Connections: {connections}</div>
    </div>
  );
}

export function GraphViewer({
  expandTarget,
  focusedNodeId,
  highlightedNodes,
  onClearHighlights,
  onNodeSelect,
  refreshToken,
}: GraphViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [overlayNode, setOverlayNode] = useState<CytoscapeNodeData | null>(null);
  const [overlayConnections, setOverlayConnections] = useState(0);

  useEffect(() => {
    if (!containerRef.current || cyRef.current) {
      return;
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      layout: {
        name: "cose-bilkent",
        fit: true,
        padding: 120,
        nodeRepulsion: 240000,
        idealEdgeLength: 180,
        edgeElasticity: 0.12,
        nestingFactor: 0.9,
        gravity: 0.12,
        tile: false,
      } as cytoscape.LayoutOptions,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (element) => NODE_TYPE_COLORS[element.data("entity_type")] ?? DEFAULT_NODE_COLOR,
            label: "",
            width: "20",
            height: "20",
            opacity: 0.95,
            "border-width": 0,
            "overlay-opacity": 0,
          },
        },
        {
          selector: "edge",
          style: {
            width: "4px",
            "line-color": "#8fd0ff",
            "target-arrow-color": "#8fd0ff",
            "target-arrow-shape": "none",
            "curve-style": "straight",
            opacity: 0.45,
          },
        },
        {
          selector: ".active-node",
          style: {
            width: "24",
            height: "24",
            "background-color": "#111827",
          },
        },
        {
          selector: ".active-edge",
          style: {
            width: "4.5px",
            opacity: 0.95,
            "line-color": "#38bdf8",
          },
        },
        {
          selector: ".query-highlight",
          style: {
            width: "28",
            height: "28",
            "background-color": "#ef4444",
            "underlay-color": "#fecaca",
            "underlay-padding": "9px",
            "underlay-opacity": 0.95,
          },
        },
      ],
    });

    cy.on("tap", "node", (event) => {
      const node = event.target;
      cy.elements().removeClass("active-node active-edge query-highlight");
      node.addClass("active-node");
      node.connectedEdges().addClass("active-edge");
      setOverlayNode(node.data() as CytoscapeNodeData);
      setOverlayConnections(node.connectedEdges().length);
      onNodeSelect(buildNodeSummary(node));
      onClearHighlights();
    });

    cy.on("tap", (event) => {
      if (event.target === cy) {
        cy.elements().removeClass("active-node active-edge query-highlight");
        setOverlayNode(null);
        setOverlayConnections(0);
        onNodeSelect(null);
        onClearHighlights();
      }
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [onClearHighlights, onNodeSelect]);

  useEffect(() => {
    let isActive = true;

    async function loadGraph() {
      setLoading(true);
      setError(null);
      try {
        const [graphPayload, graphStats] = await Promise.all([
          expandTarget ? fetchSubgraph(expandTarget.nodeId, expandTarget.depth) : fetchGraph(),
          fetchGraphStats(),
        ]);

        if (!isActive || !cyRef.current) {
          return;
        }

        cyRef.current.elements().remove();
        cyRef.current.add(toElements(graphPayload));
        cyRef.current.layout({
          name: "cose-bilkent",
          fit: true,
          padding: 140,
          nodeRepulsion: 240000,
          idealEdgeLength: 180,
          edgeElasticity: 0.12,
          nestingFactor: 0.9,
          gravity: 0.12,
          tile: false,
        } as cytoscape.LayoutOptions).run();

        setStats(graphStats);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load graph");
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    }

    void loadGraph();

    return () => {
      isActive = false;
    };
  }, [expandTarget, refreshToken]);

  useEffect(() => {
    if (!cyRef.current) {
      return;
    }

    const cy = cyRef.current;
    cy.elements().removeClass("query-highlight active-node active-edge");

    if (!highlightedNodes.length) {
      return;
    }

    const normalizedIds = new Set(highlightedNodes.map(normalizeHighlightId));
    const matches = cy.nodes().filter((node) => {
      const nodeKey = String(node.id());
      const entityId = String(node.data("entity_id") ?? "");
      return normalizedIds.has(nodeKey) || normalizedIds.has(entityId) || normalizedIds.has(normalizeHighlightId(nodeKey));
    });

    if (!matches.length) {
      return;
    }

    matches.addClass("query-highlight");
  }, [highlightedNodes]);

  useEffect(() => {
    if (!cyRef.current || !focusedNodeId) {
      return;
    }

    const cy = cyRef.current;
    const normalizedTarget = normalizeHighlightId(focusedNodeId);
    const matchedNodes = cy.nodes().filter((node) => {
      const nodeKey = String(node.id());
      const entityId = String(node.data("entity_id") ?? "");
      return entityId === normalizedTarget || nodeKey === focusedNodeId || normalizeHighlightId(nodeKey) === normalizedTarget;
    });

    if (!matchedNodes.length) {
      return;
    }

    const match = matchedNodes[0] as NodeSingular;

    cy.elements().removeClass("active-node active-edge query-highlight");
    match.addClass("query-highlight");
    cy.animate({
      fit: { eles: match, padding: 280 },
      duration: 350,
    });

    setOverlayNode(match.data() as CytoscapeNodeData);
    setOverlayConnections(match.connectedEdges().length);
    onNodeSelect(buildNodeSummary(match));
  }, [focusedNodeId, onNodeSelect]);

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-white">
      <div className="relative min-h-0 flex-1">
        <div ref={containerRef} className="h-full w-full" />

        {overlayNode ? <GraphOverlayCard connections={overlayConnections} node={overlayNode} /> : null}

        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-white/75 backdrop-blur-sm">
            <div className="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm text-slate-600 shadow-sm">
              Loading graph...
            </div>
          </div>
        ) : null}

        {error ? (
          <div className="absolute left-4 top-24 max-w-md rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        ) : null}

        <div className="absolute bottom-4 right-4 rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 text-xs text-slate-500 shadow-sm backdrop-blur">
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
            {Object.entries(NODE_TYPE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-2">
                <span className="size-2 rounded-full" style={{ backgroundColor: color }} />
                <span className="capitalize">{type}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-slate-400">{stats ? `${stats.total_nodes} nodes · ${stats.total_edges} edges` : "Loading stats..."}</div>
        </div>
      </div>
    </div>
  );
}


