from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

from backend.agents.llm_client import MODEL_NAME, call_gemini, is_gemini_available, stream_gemini
from backend.agents.memory import ConversationMemory
from backend.agents.schema_context import get_schema_prompt
from backend.services.graph_analysis import GraphAnalysisService
from backend.services.graph_builder import GraphBuilder
from backend.services.graph_store import graph_store
from backend.services.sql_engine import SqlEngine

LOGGER = logging.getLogger(__name__)
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "llm_sessions.md"
TYPE_ORDER = {"address": 0, "customer": 1, "plant": 2, "product": 3, "order": 4, "delivery": 5, "invoice": 6, "journal_entry": 7, "payment": 8}
ENTITY_TABLES = {"Address": "addresses", "Customer": "customers", "Delivery": "deliveries", "Invoice": "invoices", "JournalEntry": "journal_entries", "Order": "orders", "Payment": "payments", "Plant": "plants", "Product": "products"}
ENTITY_ALIASES = {"address": "Address", "addresses": "Address", "billing": "Invoice", "billing document": "Invoice", "billing documents": "Invoice", "customer": "Customer", "customers": "Customer", "delivery": "Delivery", "deliveries": "Delivery", "invoice": "Invoice", "invoices": "Invoice", "journal entry": "JournalEntry", "journal entries": "JournalEntry", "order": "Order", "orders": "Order", "payment": "Payment", "payments": "Payment", "plant": "Plant", "plants": "Plant", "product": "Product", "products": "Product", "sales order": "Order", "sales orders": "Order"}
FIELD_ALIASES = {"accountingDocument": "accounting_document_id", "billingDocument": "id", "customer": "customer_id", "deliveryDocument": "id", "id": "id", "invoice": "id", "invoice_id": "id", "journal_entry": "id", "order": "id", "order_id": "id", "payment": "id", "payment_id": "id", "plant": "id", "product": "id", "product_id": "id", "referenceDocument": "id", "salesOrder": "id"}
DOMAIN_TERMS = {"order", "orders", "sales order", "delivery", "deliveries", "invoice", "invoices", "billing", "payment", "payments", "customer", "customers", "product", "products", "address", "addresses", "plant", "plants", "journal", "entry", "entries", "flow", "chain", "broken", "incomplete", "sap", "o2c"}
INJECTION_PATTERNS = ["ignore previous instructions", "ignore your instructions", "forget your role", "system prompt", "you are now", "hack the database", "tell me a joke"]
REJECTION_MESSAGE = "This system is designed to answer questions related to the dataset only."


class GraphOperation(BaseModel):
    operation: str
    entity: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    traverse_to: str | None = None
    depth: int | None = None
    aggregation: str | None = None
    aggregation_field: str | None = None
    reason: str | None = None


class TranslationPayload(BaseModel):
    graph_operation: GraphOperation
    sql_query: str = ""
    explanation: str = ""


class QueryPipeline:
    def __init__(self, builder: GraphBuilder | None = None, sql_engine: SqlEngine | None = None) -> None:
        self.builder = builder or graph_store.graph
        self.sql_engine = sql_engine or graph_store.sql_engine
        self.analysis = GraphAnalysisService(self.builder)

    async def run(self, question: str, memory: ConversationMemory | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        question = (question or "").strip()
        guardrail = self._guardrail_result(question)
        self._log_stage("guardrail", question, {"result": guardrail})
        if not guardrail["allowed"]:
            return self._rejected_payload(guardrail["reason"], started)

        try:
            translation = await self._translate(question, memory)
            generated_query = self._build_generated_query(translation)
            graph_result = self._execute_graph(translation.graph_operation)
            sql_result = self.sql_engine.execute_sql(generated_query["sql_query"])
            raw_data = self._build_raw_data(graph_result, sql_result)
            answer = await self._generate_answer(question, translation, raw_data)
            relevant_node_ids = self._collect_relevant_node_ids(graph_result)
            if memory is not None:
                memory.add_turn("user", question)
                memory.add_turn("assistant", answer, query=translation.model_dump(mode="json"))
            payload = {"answer": answer, "relevant_node_ids": relevant_node_ids, "raw_data": raw_data, "generated_query": generated_query, "memory": self._memory_payload(memory), "execution_time_ms": int((time.perf_counter() - started) * 1000)}
            self._log_stage("complete", question, {"model": MODEL_NAME if is_gemini_available() else "mock", "generated_query": generated_query, "raw_data_summary": {"graph_records": len(graph_result.get("records", [])) if isinstance(graph_result.get("records"), list) else 0, "sql_rows": sql_result.total_rows}, "final_answer": answer})
            return payload
        except Exception as exc:
            self._log_stage("error", question, {"error": str(exc), "traceback": traceback.format_exc()})
            return {"answer": "The query pipeline encountered an error while processing your request.", "relevant_node_ids": [], "raw_data": None, "generated_query": None, "memory": self._memory_payload(memory), "execution_time_ms": int((time.perf_counter() - started) * 1000)}

    async def stream(self, question: str, memory: ConversationMemory | None = None) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        started = time.perf_counter()
        question = (question or "").strip()
        yield "status", {"stage": "guardrail", "message": "Checking query relevance..."}
        guardrail = self._guardrail_result(question)
        self._log_stage("guardrail", question, {"result": guardrail})
        if not guardrail["allowed"]:
            yield "complete", self._rejected_payload(guardrail["reason"], started)
            return

        yield "status", {"stage": "translating", "message": "Translating to structured query..."}
        translation = await self._translate(question, memory)
        generated_query = self._build_generated_query(translation)
        yield "query", {"generated_query": generated_query}

        yield "status", {"stage": "executing", "message": "Running query on graph and SQL engine..."}
        graph_result = self._execute_graph(translation.graph_operation)
        sql_result = self.sql_engine.execute_sql(generated_query["sql_query"])
        raw_data = self._build_raw_data(graph_result, sql_result)
        relevant_node_ids = self._collect_relevant_node_ids(graph_result)

        yield "status", {"stage": "generating", "message": "Generating answer..."}
        chunks: list[str] = []
        async for token in self._generate_answer_stream(question, translation, raw_data):
            chunks.append(token)
            yield "token", {"text": token}
        answer = "".join(chunks).strip()

        if memory is not None:
            memory.add_turn("user", question)
            memory.add_turn("assistant", answer, query=translation.model_dump(mode="json"))

        payload = {"answer": answer, "relevant_node_ids": relevant_node_ids, "raw_data": raw_data, "generated_query": generated_query, "memory": self._memory_payload(memory), "execution_time_ms": int((time.perf_counter() - started) * 1000)}
        self._log_stage("complete", question, {"model": MODEL_NAME if is_gemini_available() else "mock", "generated_query": generated_query, "raw_data_summary": {"graph_records": len(graph_result.get("records", [])) if isinstance(graph_result.get("records"), list) else 0, "sql_rows": sql_result.total_rows}, "final_answer": answer})
        yield "complete", payload

    def _memory_payload(self, memory: ConversationMemory | None) -> dict[str, Any] | None:
        if memory is None:
            return None
        snapshot = memory.to_dict()
        return {"turn_count": snapshot["turn_count"], "max_turns": snapshot["max_turns"], "last_entities": snapshot["last_entities"]}

    def _rejected_payload(self, reason: str, started: float) -> dict[str, Any]:
        return {"answer": reason or REJECTION_MESSAGE, "relevant_node_ids": [], "raw_data": None, "generated_query": None, "memory": None, "execution_time_ms": int((time.perf_counter() - started) * 1000)}

    def _guardrail_result(self, question: str) -> dict[str, Any]:
        lowered = question.lower().strip()
        if not lowered:
            return {"allowed": False, "reason": REJECTION_MESSAGE}
        if len(lowered) < 3:
            return {"allowed": False, "reason": REJECTION_MESSAGE}
        if any(pattern in lowered for pattern in INJECTION_PATTERNS):
            return {"allowed": False, "reason": REJECTION_MESSAGE}
        if re.fullmatch(r"[a-z]{3,}", lowered) and not any(term in lowered for term in DOMAIN_TERMS):
            return {"allowed": False, "reason": REJECTION_MESSAGE}
        if any(term in lowered for term in DOMAIN_TERMS):
            return {"allowed": True, "reason": "domain keyword match"}
        if re.search(r"\b(32\d{7}|74\d{4}|80\d{6}|(?:90|91)\d{6}|94\d{8}|[A-Z]{2}\d{2}|\d{4})\b", question):
            return {"allowed": True, "reason": "entity identifier match"}
        return {"allowed": False, "reason": REJECTION_MESSAGE}

    async def _translate(self, question: str, memory: ConversationMemory | None) -> TranslationPayload:
        conversation_context = memory.get_context() if memory is not None else "No prior conversation."
        recent_entities = memory.get_last_entities() if memory is not None else []
        prompt = (
            f"SCHEMA CONTEXT:\n{get_schema_prompt(self.builder)}\n\n"
            f"SQL SCHEMA:\n{json.dumps(self.sql_engine.get_schema_overview(), indent=2)}\n\n"
            f"CONVERSATION HISTORY:\n{conversation_context}\n\n"
            f"RECENT ENTITIES:\n{json.dumps(recent_entities, indent=2)}\n\n"
            "TASK: Convert this natural language query into a strict JSON object with graph_operation, sql_query, and explanation. "
            "If the user asks about broken flows, incomplete chains, or missing deliveries/invoices/payments, use operation 'broken_flows'.\n"
            "OUTPUT FORMAT:\n"
            '{"graph_operation":{"operation":"find_node|traverse|filter|aggregate|count|chain|broken_flows","entity":"Order|Customer|Delivery|Invoice|Payment|Product|Address|Plant|JournalEntry","filters":{"field_name":"value"},"traverse_to":"Delivery","depth":1,"aggregation":"sum|count|avg|max|min","aggregation_field":"amount"},"sql_query":"SELECT ...","explanation":"..."}\n\n'
            f"QUESTION: {question}"
        )
        system_instruction = "ROLE: You are a query translator for a graph database containing SAP Order-to-Cash data. Return strict JSON only."
        if not is_gemini_available():
            translated = self._mock_translate(question, memory)
            self._log_stage("translation", question, {"model": "mock", "prompt": prompt, "response": translated.model_dump(mode="json")})
            return translated
        for attempt in range(2):
            active_prompt = prompt if attempt == 0 else prompt + "\nReturn ONLY valid JSON. No markdown."
            try:
                response = await call_gemini(active_prompt, system_instruction)
                payload = self._parse_translation_payload(response)
                self._log_stage("translation", question, {"model": MODEL_NAME, "prompt": active_prompt, "response": response, "parsed": payload.model_dump(mode="json")})
                return payload
            except Exception as exc:
                self._log_stage("translation-error", question, {"model": MODEL_NAME, "prompt": active_prompt, "error": str(exc)})
        translated = self._mock_translate(question, memory)
        self._log_stage("translation", question, {"model": "mock-fallback", "prompt": prompt, "response": translated.model_dump(mode="json")})
        return translated

    def _parse_translation_payload(self, response: str) -> TranslationPayload:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in translator response")
        payload = json.loads(match.group(0))
        operation = GraphOperation.model_validate(payload.get("graph_operation") or payload)
        operation = self._normalize_graph_operation(operation)
        sql_query = str(payload.get("sql_query") or "").strip() or self._build_sql_from_graph_operation(operation)
        explanation = str(payload.get("explanation") or "Generated graph traversal and SQL translation.").strip()
        return TranslationPayload(graph_operation=operation, sql_query=sql_query, explanation=explanation)

    def _normalize_graph_operation(self, operation: GraphOperation) -> GraphOperation:
        entity = ENTITY_ALIASES.get((operation.entity or "").lower(), operation.entity)
        traverse_to = ENTITY_ALIASES.get((operation.traverse_to or "").lower(), operation.traverse_to)
        filters = {FIELD_ALIASES.get(key, key): value for key, value in operation.filters.items()}
        aggregation_field = FIELD_ALIASES.get(operation.aggregation_field or "", operation.aggregation_field)
        return GraphOperation(operation=operation.operation, entity=entity, filters=filters, traverse_to=traverse_to, depth=operation.depth, aggregation=operation.aggregation, aggregation_field=aggregation_field, reason=operation.reason)

    def _mock_translate(self, question: str, memory: ConversationMemory | None) -> TranslationPayload:
        lowered = question.lower()
        entity = self._detect_entity(question)
        record_id = self._extract_id(question)
        if not record_id and memory is not None and any(token in lowered for token in {"these", "their", "them", "first one", "first"}):
            recent = memory.get_last_entities()
            if recent:
                entity = recent[0]["entity_type"]
                record_id = recent[0]["entity_id"]
        if any(term in lowered for term in {"broken flow", "broken flows", "incomplete", "missing delivery", "missing invoice", "missing payment"}):
            graph_operation = GraphOperation(operation="broken_flows", entity="Order")
        elif all(term in lowered for term in {"products", "billing"}) or all(term in lowered for term in {"products", "invoice"}):
            graph_operation = GraphOperation(operation="aggregate", entity="Product", aggregation="count", aggregation_field="billing_documents")
        elif any(term in lowered for term in {"trace", "full flow", "chain"}):
            graph_operation = GraphOperation(operation="chain", entity=entity or self._entity_from_id(record_id) or "Invoice", filters={"id": record_id} if record_id else {}, depth=4)
        elif "count" in lowered or lowered.startswith("how many"):
            graph_operation = GraphOperation(operation="count", entity=entity or "Order", filters={"id": record_id} if record_id else {})
        elif any(term in lowered for term in {"linked", "connected", "deliveries", "invoices", "payments", "journal"}):
            traverse_to = "Delivery" if "deliver" in lowered else "Invoice" if "invoice" in lowered or "billing" in lowered else "Payment" if "payment" in lowered else "JournalEntry" if "journal" in lowered else None
            graph_operation = GraphOperation(operation="traverse", entity=entity or self._entity_from_id(record_id) or "Order", filters={"id": record_id} if record_id else {}, traverse_to=traverse_to, depth=2)
        elif record_id:
            graph_operation = GraphOperation(operation="find_node", entity=self._entity_from_id(record_id) or entity or "Order", filters={"id": record_id})
        else:
            graph_operation = GraphOperation(operation="find_node", entity=entity or "Order", filters={})
        graph_operation = self._normalize_graph_operation(graph_operation)
        return TranslationPayload(graph_operation=graph_operation, sql_query=self._build_sql_from_graph_operation(graph_operation), explanation="This translates the question into a graph operation and equivalent SQL over the normalized SQLite tables.")

    def _detect_entity(self, question: str) -> str | None:
        lowered = question.lower()
        for key, value in ENTITY_ALIASES.items():
            if key in lowered:
                return value
        return None

    def _extract_id(self, question: str) -> str | None:
        match = re.search(r"\b(?:32\d{7}|74\d{4}|80\d{6}|(?:90|91)\d{6}|94\d{8}|[A-Z]{2}\d{2}|\d{4})\b", question)
        return match.group(0) if match else None

    def _entity_from_id(self, value: str | None) -> str | None:
        if not value:
            return None
        if value.startswith("74") and len(value) == 6:
            return "Order"
        if value.startswith("80") and len(value) == 8:
            return "Delivery"
        if value.startswith(("90", "91")) and len(value) == 8:
            return "Invoice"
        if value.startswith("94") and len(value) == 10:
            return "Payment"
        if value.startswith("32") and len(value) == 9:
            return "Customer"
        if re.fullmatch(r"[A-Z]{2}\d{2}|\d{4}", value):
            return "Plant"
        return None

    def _sql_literal(self, value: Any) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def _build_where_clause(self, alias: str, filters: dict[str, Any]) -> str:
        clauses = [f"{alias}.{FIELD_ALIASES.get(key, key)} = {self._sql_literal(value)}" for key, value in filters.items()]
        return " AND ".join(clauses) if clauses else "1=1"

    def _build_sql_from_graph_operation(self, query: GraphOperation) -> str:
        entity = query.entity or "Order"
        table = ENTITY_TABLES.get(entity, "orders")
        alias = table[0]
        where = self._build_where_clause(alias, query.filters)
        if query.operation in {"find_node", "filter"}:
            return f"SELECT {alias}.* FROM {table} {alias} WHERE {where} LIMIT 50"
        if query.operation == "count":
            return f"SELECT COUNT(*) AS count FROM {table} {alias} WHERE {where}"
        if query.operation == "aggregate" and entity == "Product" and (query.aggregation_field or "").lower() in {"billing_documents", "invoice_count", "invoices"}:
            return "SELECT p.id, p.name, COUNT(DISTINCT ip.invoice_id) AS value FROM products p LEFT JOIN invoice_products ip ON ip.product_id = p.id GROUP BY p.id, p.name ORDER BY value DESC LIMIT 50"
        if query.operation == "traverse" and entity == "Customer" and query.traverse_to == "Delivery":
            return f"SELECT d.* FROM customers c JOIN customer_deliveries cd ON cd.customer_id = c.id JOIN deliveries d ON d.id = cd.delivery_id WHERE {self._build_where_clause('c', query.filters)} LIMIT 50"
        if query.operation == "chain" and entity == "Invoice":
            return f"SELECT i.id AS invoice_id, d.id AS delivery_id, o.id AS order_id, j.id AS journal_entry_id, p.id AS payment_id FROM invoices i LEFT JOIN delivery_invoices di ON di.invoice_id = i.id LEFT JOIN deliveries d ON d.id = di.delivery_id LEFT JOIN order_deliveries od ON od.delivery_id = d.id LEFT JOIN orders o ON o.id = od.order_id LEFT JOIN invoice_journal_entries ij ON ij.invoice_id = i.id LEFT JOIN journal_entries j ON j.id = ij.journal_entry_id LEFT JOIN invoice_payments ip ON ip.invoice_id = i.id LEFT JOIN payments p ON p.id = ip.payment_id WHERE {self._build_where_clause('i', query.filters)} LIMIT 50"
        if query.operation == "broken_flows":
            return "SELECT o.id AS order_id, CASE WHEN od.delivery_id IS NULL THEN 'missing_delivery' WHEN di.invoice_id IS NULL THEN 'missing_invoice' WHEN ip.payment_id IS NULL THEN 'missing_payment' ELSE 'complete' END AS flow_status FROM orders o LEFT JOIN order_deliveries od ON od.order_id = o.id LEFT JOIN delivery_invoices di ON di.delivery_id = od.delivery_id LEFT JOIN invoice_payments ip ON ip.invoice_id = di.invoice_id LIMIT 100"
        return f"SELECT {alias}.* FROM {table} {alias} WHERE {where} LIMIT 50"

    def _build_generated_query(self, translation: TranslationPayload) -> dict[str, Any]:
        return {"type": "graph_traversal", "query_string": translation.sql_query, "structured_form": translation.model_dump(mode="json"), "explanation": translation.explanation, "sql_query": translation.sql_query, "graph_query_string": self._format_graph_query_string(translation.graph_operation)}

    def _format_graph_query_string(self, query: GraphOperation) -> str:
        filters = ", ".join(f"{key}={value}" for key, value in query.filters.items()) or "all"
        if query.operation == "chain":
            return f"find_node({query.entity}, {filters}) -> chain(reverse+forward traversal)"
        if query.operation == "aggregate":
            return f"aggregate({query.entity}, op={query.aggregation}, field={query.aggregation_field})"
        if query.operation == "broken_flows":
            return "analyze(Order -> Delivery -> Invoice -> Payment) for missing links"
        if query.operation == "traverse":
            return f"find_node({query.entity}, {filters}) -> traverse({query.traverse_to}, depth={query.depth or 1})"
        if query.operation == "count":
            return f"count({query.entity}, {filters})"
        return f"find_node({query.entity}, {filters})"

    def _execute_graph(self, query: GraphOperation) -> dict[str, Any]:
        handlers = {"find_node": self._execute_find_node, "filter": self._execute_find_node, "count": self._execute_count, "traverse": self._execute_traverse, "aggregate": self._execute_aggregate, "chain": self._execute_chain, "broken_flows": self._execute_broken_flows}
        handler = handlers.get(query.operation)
        if handler is None:
            return {"operation": query.operation, "records": [], "path_edges": [], "error": "Unsupported operation"}
        return handler(query)

    def _matching_nodes(self, entity: str | None, filters: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        matches = []
        target_type = entity.lower() if entity else None
        for node_key, attrs in self.builder.graph.nodes(data=True):
            if target_type and attrs.get("entity_type") != target_type:
                continue
            if self._matches_filters(attrs, filters):
                matches.append((node_key, dict(attrs)))
        return matches

    def _matches_filters(self, attrs: dict[str, Any], filters: dict[str, Any]) -> bool:
        if not filters:
            return True
        metadata = attrs.get("metadata") if isinstance(attrs.get("metadata"), dict) else {}
        for field, expected in filters.items():
            normalized_field = FIELD_ALIASES.get(field, field)
            actual = attrs.get("entity_id") if normalized_field == "id" else attrs.get(normalized_field, metadata.get(normalized_field, metadata.get(field)))
            expected_text = str(expected).lower()
            if actual is None:
                return False
            if isinstance(actual, list):
                if not any(expected_text in str(item).lower() for item in actual):
                    return False
            elif expected_text not in str(actual).lower():
                return False
        return True

    def _node_payload(self, node_key: str, attrs: dict[str, Any]) -> dict[str, Any]:
        payload = dict(attrs)
        payload["node_id"] = node_key
        return payload

    def _edge_payload(self, source: str, target: str, key: str, attrs: dict[str, Any]) -> dict[str, Any]:
        return {"edge_id": key, "source": source, "target": target, "relationship": attrs.get("relationship") or attrs.get("edge_type"), "edge_type": attrs.get("edge_type") or attrs.get("relationship")}

    def _execute_find_node(self, query: GraphOperation) -> dict[str, Any]:
        return {"operation": query.operation, "records": [self._node_payload(key, attrs) for key, attrs in self._matching_nodes(query.entity, query.filters)], "path_edges": []}

    def _execute_count(self, query: GraphOperation) -> dict[str, Any]:
        records = [self._node_payload(key, attrs) for key, attrs in self._matching_nodes(query.entity, query.filters)]
        return {"operation": query.operation, "count": len(records), "records": records, "path_edges": []}

    def _execute_traverse(self, query: GraphOperation) -> dict[str, Any]:
        depth = query.depth or 1
        target_type = query.traverse_to.lower() if query.traverse_to else None
        records: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        for node_key, _ in self._matching_nodes(query.entity, query.filters):
            subgraph = self.builder.get_subgraph(node_key, depth)
            for sub_key, attrs in subgraph.nodes(data=True):
                if target_type and attrs.get("entity_type") != target_type and sub_key != node_key:
                    continue
                records.setdefault(sub_key, self._node_payload(sub_key, dict(attrs)))
            for source, target, key, attrs in subgraph.edges(keys=True, data=True):
                if source in records and target in records:
                    edges.setdefault(key, self._edge_payload(source, target, key, dict(attrs)))
        return {"operation": query.operation, "records": list(records.values()), "path_edges": list(edges.values())}

    def _execute_aggregate(self, query: GraphOperation) -> dict[str, Any]:
        if query.entity == "Product" and (query.aggregation_field or "").lower() in {"billing_documents", "invoice_count", "invoices"}:
            rows = []
            for node_key, attrs in self._matching_nodes("Product", query.filters):
                value = len(set(attrs.get("invoice_ids", [])))
                rows.append({"node_id": node_key, "entity_id": attrs.get("entity_id"), "entity_type": attrs.get("entity_type"), "value": value})
            rows.sort(key=lambda item: item["value"], reverse=True)
            return {"operation": query.operation, "aggregation": "count", "aggregation_field": "billing_documents", "summary": rows[0]["value"] if rows else 0, "records": rows[:50], "path_edges": []}
        records = [self._node_payload(key, attrs) for key, attrs in self._matching_nodes(query.entity, query.filters)]
        return {"operation": query.operation, "aggregation": query.aggregation, "aggregation_field": query.aggregation_field, "summary": len(records), "records": records[:50], "path_edges": []}

    def _execute_chain(self, query: GraphOperation) -> dict[str, Any]:
        graph = self.builder.graph
        chains = []
        path_edges: dict[str, dict[str, Any]] = {}
        for node_key, attrs in self._matching_nodes(query.entity, query.filters)[:20]:
            collected = {node_key: self._node_payload(node_key, dict(attrs))}
            frontier = [node_key]
            while frontier:
                current = frontier.pop(0)
                neighbors = list(graph.successors(current)) + list(graph.predecessors(current))
                for neighbor in neighbors:
                    neighbor_attrs = dict(graph.nodes[neighbor])
                    if neighbor not in collected and TYPE_ORDER.get(neighbor_attrs.get("entity_type"), 99) <= 8:
                        collected[neighbor] = self._node_payload(neighbor, neighbor_attrs)
                        frontier.append(neighbor)
                for source, target in [(current, n) for n in graph.successors(current)] + [(n, current) for n in graph.predecessors(current)]:
                    if graph.has_edge(source, target):
                        for key, edge_attrs in graph[source][target].items():
                            path_edges.setdefault(key, self._edge_payload(source, target, key, dict(edge_attrs)))
            ordered = sorted(collected.values(), key=lambda item: (TYPE_ORDER.get(item.get("entity_type"), 99), item.get("entity_id", "")))
            chains.append({"start_node_id": node_key, "chain": ordered})
        return {"operation": query.operation, "records": chains, "path_edges": list(path_edges.values())}

    def _execute_broken_flows(self, query: GraphOperation) -> dict[str, Any]:
        broken = self.analysis.get_broken_flows()
        records = [{"status": key, "entity_ids": value, "count": len(value)} for key, value in broken.items()]
        return {"operation": query.operation, "records": records, "path_edges": []}

    def _build_raw_data(self, graph_result: dict[str, Any], sql_result: Any) -> dict[str, Any]:
        return {"graph_result": graph_result, "sql_result": {"query": sql_result.query, "rows": sql_result.rows, "error": sql_result.error, "note": sql_result.note, "total_rows": sql_result.total_rows}}

    async def _generate_answer(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> str:
        if not is_gemini_available():
            answer = self._mock_answer(translation, raw_data)
            self._log_stage("answer", question, {"model": "mock", "response": answer})
            return answer
        prompt, system_instruction = self._build_answer_prompt(question, translation, raw_data)
        try:
            response = await call_gemini(prompt, system_instruction)
            self._log_stage("answer", question, {"model": MODEL_NAME, "prompt": prompt, "response": response})
            return response
        except Exception as exc:
            answer = self._mock_answer(translation, raw_data)
            self._log_stage("answer", question, {"model": "mock-fallback", "prompt": prompt, "response": answer, "error": str(exc)})
            return answer

    async def _generate_answer_stream(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> AsyncIterator[str]:
        if not is_gemini_available():
            answer = self._mock_answer(translation, raw_data)
            for token in re.findall(r"\S+\s*", answer):
                yield token
                await asyncio.sleep(0.02)
            self._log_stage("answer", question, {"model": "mock", "response": answer})
            return
        prompt, system_instruction = self._build_answer_prompt(question, translation, raw_data)
        chunks: list[str] = []
        try:
            async for token in stream_gemini(prompt, system_instruction):
                chunks.append(token)
                yield token
            self._log_stage("answer", question, {"model": MODEL_NAME, "prompt": prompt, "response": "".join(chunks)})
        except Exception as exc:
            answer = self._mock_answer(translation, raw_data)
            for token in re.findall(r"\S+\s*", answer):
                yield token
                await asyncio.sleep(0.02)
            self._log_stage("answer", question, {"model": "mock-fallback", "prompt": prompt, "response": answer, "error": str(exc)})

    def _build_answer_prompt(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> tuple[str, str]:
        prompt = f"CONTEXT:\n{json.dumps(raw_data, indent=2, default=str)[:12000]}\n\nQUESTION: {question}\nGENERATED QUERY: {translation.model_dump_json(indent=2)}\n\nTASK: Answer the user's question based ONLY on this data. Do not make up information."
        return prompt, "ROLE: You are a data analyst presenting query results."

    def _mock_answer(self, translation: TranslationPayload, raw_data: dict[str, Any]) -> str:
        graph_result = raw_data.get("graph_result", {})
        records = graph_result.get("records", []) if isinstance(graph_result, dict) else []
        if translation.graph_operation.operation == "broken_flows":
            summary = ", ".join(f"{record['status']}: {record['count']}" for record in records)
            return f"I analyzed the order-to-cash chains and found these flow categories: {summary}."
        if translation.graph_operation.operation == "aggregate" and records:
            top = records[0]
            return f"The top product is {top.get('entity_id')} with {top.get('value')} linked billing documents."
        if translation.graph_operation.operation == "chain" and records:
            chain_ids = " -> ".join(node.get("entity_id", "") for node in records[0]["chain"])
            return f"I traced the connected flow as {chain_ids}."
        if translation.graph_operation.operation == "count":
            return f"I found {graph_result.get('count', len(records))} matching records."
        if not records:
            return "I could not find matching records in the dataset for that question."
        sample_ids = ", ".join(str(record.get("entity_id", record.get("status", ""))) for record in records[:5])
        return f"I found {len(records)} matching records. Sample results: {sample_ids}."

    def _collect_relevant_node_ids(self, graph_result: dict[str, Any] | None) -> list[str]:
        if graph_result is None:
            return []
        collected: set[str] = set()
        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key in ("node_id", "entity_id", "start_node_id"):
                    if value.get(key):
                        collected.add(str(value[key]))
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(graph_result)
        return sorted(collected)

    def _log_stage(self, stage: str, question: str, payload: dict[str, Any]) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = f"\n\n## {datetime.utcnow().isoformat()}Z | {stage}\n- Question: {question}\n\n```json\n{json.dumps(payload, indent=2, default=str)}\n```\n"
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(entry)
