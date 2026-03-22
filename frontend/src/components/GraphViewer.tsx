import { useEffect, useRef, useState } from "react";

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import coseBilkent from "cytoscape-cose-bilkent";

import { fetchGraph, fetchGraphStats, fetchSubgraph } from "../services/api";
import type { GraphPayload, GraphStats, NodeSummary } from "../types/api";
import { DEFAULT_NODE_COLOR, NODE_TYPE_COLORS } from "../types/graph";

cytoscape.use(coseBilkent);

interface GraphViewerProps {
  expandTarget: { nodeId: string; depth: number } | null;
  highlightedNodes: string[];
  onClearHighlights: () => void;
  onNodeSelect: (node: NodeSummary | null) => void;
  refreshToken: number;
}

function toElements(payload: GraphPayload): ElementDefinition[] {
  const nodes = payload.nodes.map((node) => ({ data: node.data }));
  const edges = payload.edges.map((edge) => ({ data: edge.data }));
  return [...nodes, ...edges];
}

export function GraphViewer({
  expandTarget,
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
        padding: 32,
      } as cytoscape.LayoutOptions,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (element) => NODE_TYPE_COLORS[element.data("entity_type")] ?? DEFAULT_NODE_COLOR,
            label: "data(label)",
            color: "#e2e8f0",
            "font-size": "11px",
            "font-weight": 700,
            "text-max-width": "90px",
            "text-wrap": "wrap",
            "text-valign": "bottom",
            "text-margin-y": 10,
            width: "24",
            height: "24",
            "border-width": "2px",
            "border-color": "#cbd5e1",
            "overlay-opacity": 0,
          },
        },
        {
          selector: "edge",
          style: {
            width: "2px",
            "line-color": "#475569",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.4,
          },
        },
        {
          selector: ".active-node",
          style: {
            "border-width": "4px",
            "border-color": "#f8fafc",
            width: "30",
            height: "30",
          },
        },
        {
          selector: ".active-edge",
          style: {
            width: "4px",
            opacity: 1,
            "line-color": "#f8fafc",
            "target-arrow-color": "#f8fafc",
          },
        },
        {
          selector: ".query-highlight",
          style: {
            "border-width": "5px",
            "border-color": "#22d3ee",
            "underlay-color": "#22d3ee",
            "underlay-padding": "10px",
            "underlay-opacity": 0.18,
          },
        },
        {
          selector: ".faded",
          style: {
            opacity: 0.14,
          },
        },
      ],
    });

    cy.on("tap", "node", (event) => {
      const node = event.target;
      cy.elements().removeClass("active-node active-edge faded");
      cy.elements().addClass("faded");
      node.removeClass("faded").addClass("active-node");
      node.connectedEdges().removeClass("faded").addClass("active-edge");
      node.connectedEdges().connectedNodes().removeClass("faded");
      onClearHighlights();

      onNodeSelect({
        nodeId: node.data("entity_id"),
        nodeKey: node.id(),
        entityId: node.data("entity_id"),
        entityType: node.data("entity_type"),
        label: node.data("label") ?? node.data("entity_id"),
      });
    });

    cy.on("tap", (event) => {
      if (event.target === cy) {
        cy.elements().removeClass("active-node active-edge faded");
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
          padding: 36,
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
    cy.nodes().removeClass("query-highlight");

    if (!highlightedNodes.length) {
      return;
    }

    const normalizedIds = new Set(highlightedNodes);
    const matches = cy.nodes().filter((node) => normalizedIds.has(node.id()) || normalizedIds.has(node.data("entity_id")));
    matches.addClass("query-highlight");
  }, [highlightedNodes]);

  return (
    <div className="relative flex h-[70vh] min-h-[560px] flex-col lg:h-screen">
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-950/70 px-4 py-3 backdrop-blur">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Graph Workspace</p>
          <h2 className="mt-1 text-lg font-semibold text-white">Interactive Cytoscape View</h2>
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-400">
          <span>{stats ? `${stats.total_nodes} nodes` : "..."}</span>
          <span>{stats ? `${stats.total_edges} edges` : "..."}</span>
        </div>
      </div>

      <div className="relative flex-1">
        <div ref={containerRef} className="h-full w-full" />

        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm">
            <div className="rounded-full border border-cyan-400/30 bg-slate-900/90 px-5 py-3 text-sm text-cyan-300">
              Loading graph...
            </div>
          </div>
        ) : null}

        {error ? (
          <div className="absolute left-4 top-4 max-w-md rounded-2xl border border-rose-500/40 bg-rose-950/80 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        ) : null}

        <div className="absolute bottom-4 right-4 rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-xs text-slate-400 shadow-xl backdrop-blur">
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
            {Object.entries(NODE_TYPE_COLORS).map(([type, color]) => (
              <div key={type} className="flex items-center gap-2">
                <span className="size-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="capitalize">{type}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
