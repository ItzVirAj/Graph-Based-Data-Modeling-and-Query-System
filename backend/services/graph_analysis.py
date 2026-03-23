from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx
from networkx.algorithms.community import label_propagation_communities

from backend.services.graph_builder import GraphBuilder


class GraphAnalysisService:
    def __init__(self, builder: GraphBuilder) -> None:
        self.builder = builder

    def get_clusters(self) -> list[dict[str, Any]]:
        graph = nx.Graph(self.builder.graph.to_undirected())
        communities = list(label_propagation_communities(graph))
        clusters = []
        for index, community in enumerate(communities, start=1):
            node_ids = sorted(str(self.builder.graph.nodes[node_key].get("entity_id", node_key)) for node_key in community)
            clusters.append({"cluster_id": f"cluster_{index}", "size": len(node_ids), "node_ids": node_ids})
        return sorted(clusters, key=lambda cluster: cluster["size"], reverse=True)

    def get_node_importance(self, limit: int = 25) -> list[dict[str, Any]]:
        scores = nx.pagerank(nx.DiGraph(self.builder.graph))
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [{"node_key": node_key, "entity_id": self.builder.graph.nodes[node_key].get("entity_id"), "entity_type": self.builder.graph.nodes[node_key].get("entity_type"), "label": self.builder.graph.nodes[node_key].get("label"), "importance_score": round(score, 6)} for node_key, score in ranked]

    def get_broken_flows(self) -> dict[str, list[str]]:
        graph = self.builder.graph
        result: dict[str, list[str]] = defaultdict(list)
        billed_without_delivery: set[str] = set()

        for node_key, attrs in graph.nodes(data=True):
            if attrs.get("entity_type") == "invoice":
                has_delivery = any(graph.nodes[pred].get("entity_type") == "delivery" for pred in graph.predecessors(node_key))
                if not has_delivery:
                    billed_without_delivery.add(str(attrs.get("entity_id")))

        for node_key, attrs in graph.nodes(data=True):
            if attrs.get("entity_type") != "order":
                continue
            order_id = str(attrs.get("entity_id"))
            delivery_keys = [key for key in graph.successors(node_key) if graph.nodes[key].get("entity_type") == "delivery"]
            if not delivery_keys:
                result["missing_delivery"].append(order_id)
                continue
            invoice_keys = [key for delivery_key in delivery_keys for key in graph.successors(delivery_key) if graph.nodes[key].get("entity_type") == "invoice"]
            if not invoice_keys:
                result["missing_invoice"].append(order_id)
                continue
            payment_keys = [key for invoice_key in invoice_keys for key in graph.successors(invoice_key) if graph.nodes[key].get("entity_type") == "payment"]
            if not payment_keys:
                result["missing_payment"].append(order_id)
                continue
            result["complete"].append(order_id)

        return {"complete": sorted(result.get("complete", [])), "missing_delivery": sorted(result.get("missing_delivery", [])), "missing_invoice": sorted(result.get("missing_invoice", [])), "missing_payment": sorted(result.get("missing_payment", [])), "billed_without_delivery": sorted(billed_without_delivery)}
