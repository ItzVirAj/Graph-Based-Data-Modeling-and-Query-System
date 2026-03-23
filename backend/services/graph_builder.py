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
        for plant in self.data.plants:
            self._add_entity_node("plant", plant)
        for product in self.data.products:
            self._add_entity_node("product", product)
        for order in self.data.orders:
            self._add_entity_node("order", order)
        for delivery in self.data.deliveries:
            self._add_entity_node("delivery", delivery)
        for invoice in self.data.invoices:
            self._add_entity_node("invoice", invoice)
        for journal_entry in self.data.journal_entries:
            self._add_entity_node("journal_entry", journal_entry)
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
            for delivery_id in customer.delivery_ids:
                self._add_edge(customer_key, self._node_key("delivery", delivery_id), "customer_to_delivery")

        for plant in self.data.plants:
            plant_key = self._node_key("plant", plant.id)
            for product_id in plant.product_ids:
                self._add_edge(self._node_key("product", product_id), plant_key, "product_to_plant")
            for delivery_id in plant.delivery_ids:
                self._add_edge(self._node_key("delivery", delivery_id), plant_key, "delivery_to_plant")

        for delivery in self.data.deliveries:
            delivery_key = self._node_key("delivery", delivery.id)
            for order_id in delivery.order_ids:
                self._add_edge(self._node_key("order", order_id), delivery_key, "order_to_delivery")
            for product_id in delivery.product_ids:
                self._add_edge(delivery_key, self._node_key("product", product_id), "delivery_to_product")
            for plant_id in delivery.plant_ids:
                self._add_edge(delivery_key, self._node_key("plant", plant_id), "delivery_to_plant")

        for invoice in self.data.invoices:
            invoice_key = self._node_key("invoice", invoice.id)
            for delivery_id in invoice.delivery_ids:
                self._add_edge(self._node_key("delivery", delivery_id), invoice_key, "delivery_to_invoice")
            for journal_entry_id in invoice.journal_entry_ids:
                self._add_edge(invoice_key, self._node_key("journal_entry", journal_entry_id), "invoice_to_journal_entry")

        for payment in self.data.payments:
            payment_key = self._node_key("payment", payment.id)
            for invoice_id in payment.invoice_ids:
                self._add_edge(self._node_key("invoice", invoice_id), payment_key, "invoice_to_payment")

        # The provided SAP dataset contains Sales Orders and order items, not Purchase Orders.
        # Order -> Product captures the available SalesOrderItem -> Material relationship.

    def _add_entity_node(self, entity_type: str, entity: Any) -> None:
        self.add_node(entity.id, entity_type, entity.model_dump(mode="json"))

    def _add_edge(self, source: str, target: str, edge_type: str) -> None:
        if not self.graph.has_node(source) or not self.graph.has_node(target):
            return
        edge_id = f"{edge_type}:{source}:{target}:{self.graph.number_of_edges(source, target)}"
        self.graph.add_edge(source, target, key=edge_id, edge_type=edge_type, relationship=edge_type, source=source, target=target)

    def _resolve_node_key(self, node_id: str, entity_type: str | None = None) -> str | None:
        if entity_type:
            node_key = self._node_key(entity_type.lower(), node_id)
            if self.graph.has_node(node_key):
                return node_key
        if self.graph.has_node(node_id):
            return node_id
        matches = [candidate for candidate, attrs in self.graph.nodes(data=True) if attrs.get("entity_id") == node_id and (entity_type is None or attrs.get("entity_type") == entity_type.lower())]
        if len(matches) == 1:
            return matches[0]
        return None

    def add_node(self, entity_id: str, entity_type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_type = entity_type.lower()
        node_key = self._node_key(normalized_type, entity_id)
        payload = dict(metadata or {})
        payload.setdefault("id", entity_id)
        payload["entity_type"] = normalized_type
        payload["entity_id"] = entity_id
        payload.setdefault("label", payload.get("name") or entity_id)
        self.graph.add_node(node_key, **payload)
        return dict(self.graph.nodes[node_key])

    def add_edge(self, source: str, target: str, relationship: str) -> dict[str, Any]:
        source_key = self._resolve_node_key(source)
        target_key = self._resolve_node_key(target)
        if source_key is None or target_key is None:
            raise ValueError("Both source and target nodes must exist before adding an edge.")
        self._add_edge(source_key, target_key, relationship)
        edge_key = next(reversed(list(self.graph[source_key][target_key].keys())))
        return dict(self.graph[source_key][target_key][edge_key])

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        node_key = self._resolve_node_key(node_id)
        if node_key is None:
            return None
        payload = dict(self.graph.nodes[node_key])
        payload["node_key"] = node_key
        return payload

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

    def serialize_graph(self, graph: nx.MultiDiGraph | None = None) -> dict[str, list[dict[str, Any]]]:
        target_graph = graph or self.graph
        nodes = [{"data": {**attrs, "id": node_key, "node_key": node_key}} for node_key, attrs in target_graph.nodes(data=True)]
        edges = [{"data": {"id": key, "source": source, "target": target, **attrs}} for source, target, key, attrs in target_graph.edges(keys=True, data=True)]
        return {"nodes": nodes, "edges": edges}

    def to_json(self) -> dict[str, list[dict[str, Any]]]:
        return self.serialize_graph()

    def get_stats(self) -> dict[str, Any]:
        node_counts = Counter(attrs.get("entity_type", "unknown") for _, attrs in self.graph.nodes(data=True))
        edge_counts = Counter(attrs.get("edge_type", "unknown") for *_, attrs in self.graph.edges(data=True))
        return {"total_nodes": self.graph.number_of_nodes(), "total_edges": self.graph.number_of_edges(), "nodes_by_type": dict(sorted(node_counts.items())), "edges_by_type": dict(sorted(edge_counts.items()))}
