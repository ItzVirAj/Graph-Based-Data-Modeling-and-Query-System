from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.services.graph_builder import GraphBuilder
from backend.services.graph_store import graph_store

EDGE_LABELS = {
    "order_to_delivery": "Order -> Delivery",
    "delivery_to_invoice": "Delivery -> Invoice",
    "invoice_to_payment": "Invoice -> Payment",
    "order_to_customer": "Order -> Customer",
    "order_to_product": "Order -> Product",
    "customer_to_address": "Customer -> Address",
}


def get_schema_dict(builder: GraphBuilder | None = None) -> dict[str, Any]:
    active_builder = builder or graph_store.graph
    graph = active_builder.graph
    fields_by_type: dict[str, set[str]] = defaultdict(set)

    for _, attrs in graph.nodes(data=True):
        entity_type = str(attrs.get("entity_type", "unknown")).capitalize()
        fields_by_type[entity_type].update(
            key for key in attrs.keys() if key not in {"entity_type", "label", "node_key"}
        )
        metadata = attrs.get("metadata")
        if isinstance(metadata, dict):
            fields_by_type[entity_type].update(str(key) for key in metadata.keys())

    edge_types = sorted({attrs.get("edge_type", "unknown") for *_, attrs in graph.edges(data=True)})
    edge_descriptions = [EDGE_LABELS.get(edge_type, edge_type) for edge_type in edge_types]

    return {
        "node_types": sorted(fields_by_type.keys()),
        "fields_by_type": {key: sorted(values) for key, values in sorted(fields_by_type.items())},
        "edge_types": edge_types,
        "edge_descriptions": edge_descriptions,
    }


def get_schema_prompt(builder: GraphBuilder | None = None) -> str:
    schema = get_schema_dict(builder)
    lines = ["GRAPH SCHEMA:", "", "Node Types:"]
    for node_type in schema["node_types"]:
        fields = ", ".join(schema["fields_by_type"][node_type])
        lines.append(f"- {node_type}: fields [{fields}]")

    lines.extend(["", "Edge Types:"])
    for edge_description in schema["edge_descriptions"]:
        lines.append(f"- {edge_description}")

    return "\n".join(lines)
