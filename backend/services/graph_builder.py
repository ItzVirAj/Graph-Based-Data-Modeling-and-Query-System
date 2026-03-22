from __future__ import annotations

from collections import Counter
from typing import Any

import networkx as nx

from .data_loader import NormalizedData


class GraphBuilder:
    def __init__(self, data: NormalizedData) -> None:
        self.data = data
        self.graph = nx.MultiDiGraph()
        self._build()

    @staticmethod
    def _node_key(entity_type: str, entity_id: str) -> str:
        return f"{entity_type}:{entity_id}"

    def _build(self) -> None:
        for customer in self.data.customers:
            self._add_entity_node("customer", customer)
        for address in self.data.addresses:
            self._add_entity_node("address", address)
        for product in self.data.products:
            self._add_entity_node("product", product)
        for order in self.data.orders:
            self._add_entity_node("order", order)
        for delivery in self.data.deliveries:
            self._add_entity_node("delivery", delivery)
        for invoice in self.data.invoices:
            self._add_entity_node("invoice", invoice)
        for payment in self.data.payments:
            self._add_entity_node("payment", payment)

        for order in self.data.orders:
            order_key = self._node_key("order", order.id)
            if order.customer_id:
                self._add_edge(order_key, self._node_key("customer", order.customer_id), "order_to_customer")
            for product_id in order.product_ids:
                self._add_edge(order_key, self._node_key("product", product_id), "order_to_product")

        for customer in self.data.customers:
            customer_key = self._node_key("customer", customer.id)
            for address_id in customer.address_ids:
                self._add_edge(customer_key, self._node_key("address", address_id), "customer_to_address")

        for delivery in self.data.deliveries:
            delivery_key = self._node_key("delivery", delivery.id)
            for order_id in delivery.order_ids:
                self._add_edge(self._node_key("order", order_id), delivery_key, "order_to_delivery")

        for invoice in self.data.invoices:
            invoice_key = self._node_key("invoice", invoice.id)
            for delivery_id in invoice.delivery_ids:
                self._add_edge(self._node_key("delivery", delivery_id), invoice_key, "delivery_to_invoice")

        for payment in self.data.payments:
            payment_key = self._node_key("payment", payment.id)
            for invoice_id in payment.invoice_ids:
                self._add_edge(self._node_key("invoice", invoice_id), payment_key, "invoice_to_payment")

    def _add_entity_node(self, entity_type: str, entity: Any) -> None:
        node_key = self._node_key(entity_type, entity.id)
        payload = entity.model_dump(mode="json")
        payload["entity_type"] = entity_type
        payload["entity_id"] = entity.id
        payload["label"] = entity.id
        self.graph.add_node(node_key, **payload)

    def _add_edge(self, source: str, target: str, edge_type: str) -> None:
        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return
        self.graph.add_edge(
            source,
            target,
            key=f"{edge_type}:{source}:{target}",
            edge_type=edge_type,
            source=source,
            target=target,
        )

    def _resolve_node_key(self, node_id: str) -> str | None:
        if self.graph.has_node(node_id):
            return node_id

        matches = [
            candidate
            for candidate, attrs in self.graph.nodes(data=True)
            if attrs.get("entity_id") == node_id
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        node_key = self._resolve_node_key(node_id)
        if node_key is None:
            return None
        return dict(self.graph.nodes[node_key])

    def get_neighbors(self, node_id: str) -> list[dict[str, Any]]:
        node_key = self._resolve_node_key(node_id)
        if node_key is None:
            return []

        neighbors = set(self.graph.successors(node_key)) | set(self.graph.predecessors(node_key))
        results = []
        for neighbor_key in sorted(neighbors):
            payload = dict(self.graph.nodes[neighbor_key])
            payload["node_key"] = neighbor_key
            results.append(payload)
        return results

    def get_subgraph(self, node_id: str, depth: int = 1) -> nx.MultiDiGraph:
        node_key = self._resolve_node_key(node_id)
        if node_key is None:
            return nx.MultiDiGraph()

        undirected = self.graph.to_undirected()
        lengths = nx.single_source_shortest_path_length(undirected, node_key, cutoff=max(depth, 0))
        return self.graph.subgraph(lengths.keys()).copy()

    def to_json(self) -> dict[str, list[dict[str, Any]]]:
        nodes = []
        edges = []

        for node_key, attrs in self.graph.nodes(data=True):
            node_data = {"id": node_key, **attrs}
            nodes.append({"data": node_data})

        for source, target, key, attrs in self.graph.edges(keys=True, data=True):
            edge_data = {"id": key, "source": source, "target": target, **attrs}
            edges.append({"data": edge_data})

        return {"nodes": nodes, "edges": edges}

    def get_stats(self) -> dict[str, Any]:
        node_counts = Counter(attrs.get("entity_type", "unknown") for _, attrs in self.graph.nodes(data=True))
        edge_counts = Counter(attrs.get("edge_type", "unknown") for *_, attrs in self.graph.edges(data=True))
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "nodes_by_type": dict(sorted(node_counts.items())),
            "edges_by_type": dict(sorted(edge_counts.items())),
        }
