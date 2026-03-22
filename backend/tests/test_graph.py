from __future__ import annotations

from backend.services.data_loader import DEFAULT_DATA_DIR, DataLoader
from backend.services.graph_builder import GraphBuilder
from backend.services.graph_store import graph_store


def _find_full_chain(builder: GraphBuilder) -> tuple[str, str, str, str] | None:
    graph = builder.graph
    for node_key, attrs in graph.nodes(data=True):
        if attrs.get("entity_type") != "order":
            continue

        for delivery_key in graph.successors(node_key):
            if graph.nodes[delivery_key].get("entity_type") != "delivery":
                continue
            for invoice_key in graph.successors(delivery_key):
                if graph.nodes[invoice_key].get("entity_type") != "invoice":
                    continue
                for payment_key in graph.successors(invoice_key):
                    if graph.nodes[payment_key].get("entity_type") == "payment":
                        return (
                            graph.nodes[node_key]["entity_id"],
                            graph.nodes[delivery_key]["entity_id"],
                            graph.nodes[invoice_key]["entity_id"],
                            graph.nodes[payment_key]["entity_id"],
                        )
    return None


def test_graph_build_and_full_chain() -> None:
    data = DataLoader(DEFAULT_DATA_DIR).load_all()
    builder = GraphBuilder(data)
    stats = builder.get_stats()
    print("graph stats:", stats)

    assert stats["nodes_by_type"]["order"] > 0
    assert stats["nodes_by_type"]["delivery"] > 0
    assert stats["nodes_by_type"]["invoice"] > 0
    assert stats["nodes_by_type"]["payment"] > 0
    assert stats["nodes_by_type"]["customer"] > 0
    assert stats["nodes_by_type"]["product"] > 0
    assert stats["nodes_by_type"]["address"] > 0

    chain = _find_full_chain(builder)
    print("full chain:", chain)
    assert chain is not None


def test_graph_store_singleton_initializes() -> None:
    graph = graph_store.initialize(force=True)
    assert graph is graph_store.graph
