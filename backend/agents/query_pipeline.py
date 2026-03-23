from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field

from backend.agents.llm_client import call_gemini, is_gemini_available, stream_gemini
from backend.agents.memory import ConversationMemory
from backend.agents.schema_context import get_schema_prompt
from backend.services.graph_builder import GraphBuilder
from backend.services.graph_store import graph_store
from backend.services.sql_engine import SqlEngine

LOGGER = logging.getLogger(__name__)
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "llm_sessions.md"
TYPE_ORDER = {"address": 0, "customer": 1, "order": 2, "delivery": 3, "invoice": 4, "payment": 5, "product": 6}
ENTITY_TABLES = {"Address": "addresses", "Customer": "customers", "Delivery": "deliveries", "Invoice": "invoices", "Order": "orders", "Payment": "payments", "Product": "products"}
ENTITY_ALIASES = {
    "address": "Address", "addresses": "Address", "billing": "Invoice", "billing document": "Invoice", "billing documents": "Invoice",
    "customer": "Customer", "customers": "Customer", "delivery": "Delivery", "deliveries": "Delivery", "invoice": "Invoice",
    "invoices": "Invoice", "order": "Order", "orders": "Order", "payment": "Payment", "payments": "Payment", "product": "Product",
    "products": "Product", "sales order": "Order", "sales orders": "Order",
}
FIELD_ALIASES = {
    "accountingDocument": "accounting_document_id", "billingDocument": "id", "customer": "customer_id", "deliveryDocument": "id", "id": "id",
    "invoice": "id", "invoice_id": "id", "order": "id", "order_id": "id", "payment": "id", "payment_id": "id", "product": "id",
    "product_id": "id", "referenceDocument": "id", "salesOrder": "id",
}


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
    DOMAIN_TERMS = {"order", "orders", "delivery", "deliveries", "invoice", "invoices", "payment", "payments", "customer", "customers", "product", "products", "address", "addresses", "billing", "billing document", "sales order", "graph", "flow", "chain", "sap", "o2c", "journal", "entry"}
    REJECTION_MESSAGE = "This system is designed to answer questions related to the dataset only."

    def __init__(self, builder: GraphBuilder | None = None, sql_engine: SqlEngine | None = None) -> None:
        self.builder = builder or graph_store.graph
        self.sql_engine = sql_engine or graph_store.sql_engine

    async def run(self, question: str, memory: ConversationMemory | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        payload = await self._run_internal(question.strip(), memory)
        payload["execution_time_ms"] = int((time.perf_counter() - started) * 1000)
        return payload

    async def stream(self, question: str, memory: ConversationMemory | None = None) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        started = time.perf_counter()
        question = question.strip()
        yield "status", {"stage": "guardrail", "message": "Checking query relevance..."}
        if not self._passes_guardrail(question):
            self._append_log(stage="guardrail", question=question, prompt="", response=self.REJECTION_MESSAGE, notes="Rejected as out-of-domain query.")
            result = self._build_rejected_response()
            result["execution_time_ms"] = int((time.perf_counter() - started) * 1000)
            yield "complete", result
            return

        yield "status", {"stage": "translating", "message": "Translating to structured query and SQL..."}
        translation = await self._translate(question, memory)
        generated_query = self._build_generated_query(translation)
        yield "query", {"generated_query": generated_query}

        if translation.graph_operation.operation == "rejected":
            result = {**self._build_rejected_response(translation.graph_operation.reason or self.REJECTION_MESSAGE), "generated_query": generated_query}
            result["execution_time_ms"] = int((time.perf_counter() - started) * 1000)
            yield "complete", result
            return

        yield "status", {"stage": "executing", "message": "Running graph and SQL queries..."}
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

        self._append_log(stage="complete", question=question, prompt="Streaming response complete", response=answer, notes=f"Returned {len(relevant_node_ids)} relevant nodes.")
        result = {
            "answer": answer,
            "relevant_node_ids": relevant_node_ids,
            "raw_data": raw_data,
            "generated_query": generated_query,
            "memory": self._memory_payload(memory),
            "execution_time_ms": int((time.perf_counter() - started) * 1000),
        }
        yield "complete", result

    async def _run_internal(self, question: str, memory: ConversationMemory | None) -> dict[str, Any]:
        if not self._passes_guardrail(question):
            self._append_log(stage="guardrail", question=question, prompt="", response=self.REJECTION_MESSAGE, notes="Rejected as out-of-domain query.")
            return self._build_rejected_response()
        translation = await self._translate(question, memory)
        generated_query = self._build_generated_query(translation)
        if translation.graph_operation.operation == "rejected":
            return {**self._build_rejected_response(translation.graph_operation.reason or self.REJECTION_MESSAGE), "generated_query": generated_query, "memory": self._memory_payload(memory)}
        graph_result = self._execute_graph(translation.graph_operation)
        sql_result = self.sql_engine.execute_sql(generated_query["sql_query"])
        raw_data = self._build_raw_data(graph_result, sql_result)
        answer = await self._generate_answer(question, translation, raw_data)
        relevant_node_ids = self._collect_relevant_node_ids(graph_result)
        if memory is not None:
            memory.add_turn("user", question)
            memory.add_turn("assistant", answer, query=translation.model_dump(mode="json"))
        self._append_log(stage="complete", question=question, prompt="Non-streaming response complete", response=answer, notes=f"Returned {len(relevant_node_ids)} relevant nodes.")
        return {"answer": answer, "relevant_node_ids": relevant_node_ids, "raw_data": raw_data, "generated_query": generated_query, "memory": self._memory_payload(memory)}

    def _build_rejected_response(self, answer: str | None = None) -> dict[str, Any]:
        return {"answer": answer or self.REJECTION_MESSAGE, "relevant_node_ids": [], "raw_data": None, "generated_query": None, "memory": None}

    def _memory_payload(self, memory: ConversationMemory | None) -> dict[str, Any] | None:
        if memory is None:
            return None
        snapshot = memory.to_dict()
        return {"turn_count": snapshot["turn_count"], "max_turns": snapshot["max_turns"], "last_entities": snapshot["last_entities"]}

    def _passes_guardrail(self, question: str) -> bool:
        lowered = question.lower()
        if any(term in lowered for term in self.DOMAIN_TERMS):
            return True
        return re.search(r"\b(32\d{7}|74\d{4}|80\d{6}|90\d{6}|91\d{6}|94\d{8})\b", lowered) is not None

    async def _translate(self, question: str, memory: ConversationMemory | None) -> TranslationPayload:
        conversation_context = memory.get_context() if memory is not None else "No prior conversation."
        recent_entities = memory.get_last_entities() if memory is not None else []
        schema_prompt = get_schema_prompt(self.builder)
        sql_schema_prompt = self._get_sql_schema_prompt()
        system_instruction = "ROLE: You are a query translator for a graph database containing SAP Order-to-Cash data. Return strict JSON only."
        prompt = (
            f"SCHEMA CONTEXT:\n{schema_prompt}\n\nSQL SCHEMA:\n{sql_schema_prompt}\n\n"
            f"CONVERSATION HISTORY:\n{conversation_context}\n\nRECENT ENTITIES:\n{json.dumps(recent_entities, indent=2)}\n\n"
            "TASK: Convert this natural language query into both a graph operation and an equivalent SQL query.\n"
            "OUTPUT FORMAT:\n"
            "{\n"
            '  "graph_operation": {"operation": "find_node" | "traverse" | "filter" | "aggregate" | "count" | "chain", "entity": "Order" | "Customer" | "Delivery" | "Invoice" | "Payment" | "Product" | "Address", "filters": {"field_name": "value"}, "traverse_to": "Delivery", "depth": 1, "aggregation": "sum" | "count" | "avg" | "max" | "min", "aggregation_field": "amount"},\n'
            '  "sql_query": "SELECT ...",\n'
            '  "explanation": "1-2 sentence explanation of what the query does"\n'
            "}\n\n"
            f"QUESTION: {question}"
        )
        if not is_gemini_available():
            LOGGER.warning("No Gemini API key found, using mock mode")
            translated = self._mock_translate(question, memory)
            self._append_log(stage="translation-mock", question=question, prompt=prompt, response=translated.model_dump_json(indent=2), notes="Mock translator used.")
            return translated

        for attempt in range(2):
            active_prompt = prompt if attempt == 0 else prompt + "\n\nReturn ONLY valid JSON. No markdown, no commentary."
            try:
                response = await call_gemini(active_prompt, system_instruction)
                parsed = self._parse_translation_payload(response, question)
                self._append_log(stage=f"translation-llm-attempt-{attempt + 1}", question=question, prompt=active_prompt, response=response, notes="Translation successful.")
                return parsed
            except Exception as exc:
                self._append_log(stage=f"translation-llm-attempt-{attempt + 1}", question=question, prompt=active_prompt, response=str(exc), notes="Translation attempt failed.")

        fallback = self._mock_translate(question, memory)
        self._append_log(stage="translation-fallback", question=question, prompt=prompt, response=fallback.model_dump_json(indent=2), notes="LLM translation failed; deterministic fallback used.")
        return fallback

    def _parse_translation_payload(self, response: str, question: str) -> TranslationPayload:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in translator response")
        payload = json.loads(match.group(0))
        graph_operation = GraphOperation.model_validate(payload.get("graph_operation") or payload)
        normalized = self._normalize_graph_operation(graph_operation)
        sql_query = str(payload.get("sql_query") or "").strip() or self._build_sql_from_graph_operation(normalized)
        explanation = str(payload.get("explanation") or "").strip() or "Generated graph traversal and SQL translation for the dataset query."
        parsed = TranslationPayload(graph_operation=normalized, sql_query=sql_query, explanation=explanation)
        self._append_log(stage="translation-refinement", question=question, prompt="Normalized translation payload prepared for execution.", response=parsed.model_dump_json(indent=2), notes="Structured graph operation and SQL query accepted.")
        return parsed

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
            recent_entities = memory.get_last_entities()
            if recent_entities:
                entity = recent_entities[0]["entity_type"]
                record_id = recent_entities[0]["entity_id"]

        if any(term in lowered for term in ["chain", "flow", "trace", "full path"]):
            graph_operation = GraphOperation(operation="chain", entity=entity or self._entity_from_id(record_id) or "Invoice", filters={"id": record_id} if record_id else {}, depth=4)
        elif any(term in lowered for term in ["highest", "most", "top"]):
            graph_operation = GraphOperation(operation="aggregate", entity=entity or "Product", filters={}, aggregation="max", aggregation_field="invoices")
        elif "count" in lowered or lowered.startswith("how many"):
            graph_operation = GraphOperation(operation="count", entity=entity or "Order", filters={"id": record_id} if record_id else {})
        elif any(term in lowered for term in ["linked", "connected", "deliveries", "invoices", "payments"]):
            traverse_to = "Delivery" if "deliver" in lowered else "Invoice" if "invoice" in lowered or "billing" in lowered else "Payment" if "payment" in lowered or "journal" in lowered else None
            graph_operation = GraphOperation(operation="traverse", entity=entity or self._entity_from_id(record_id) or "Order", filters={"id": record_id} if record_id else {}, traverse_to=traverse_to, depth=2)
        elif record_id:
            graph_operation = GraphOperation(operation="find_node", entity=self._entity_from_id(record_id) or entity or "Order", filters={"id": record_id})
        else:
            graph_operation = GraphOperation(operation="find_node", entity=entity or "Order", filters={})

        graph_operation = self._normalize_graph_operation(graph_operation)
        sql_query = self._build_sql_from_graph_operation(graph_operation)
        explanation = "This translates the request into a graph traversal and an equivalent SQL query over the normalized in-memory SQLite tables."
        return TranslationPayload(graph_operation=graph_operation, sql_query=sql_query, explanation=explanation)

    def _detect_entity(self, question: str) -> str | None:
        lowered = question.lower()
        for key, value in ENTITY_ALIASES.items():
            if key in lowered:
                return value
        return None

    def _extract_id(self, question: str) -> str | None:
        match = re.search(r"\b(?:32\d{7}|74\d{4}|80\d{6}|90\d{6}|91\d{6}|94\d{8})\b", question)
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
        return None

    def _get_sql_schema_prompt(self) -> str:
        return "\n".join(f"- {table}: columns [{', '.join(columns)}]" for table, columns in self.sql_engine.get_schema_overview().items())

    def _build_generated_query(self, translation: TranslationPayload) -> dict[str, Any]:
        graph_query_string = self._format_graph_query_string(translation.graph_operation)
        sql_query = translation.sql_query.strip() or self._build_sql_from_graph_operation(translation.graph_operation)
        return {
            "type": "graph_traversal",
            "query_string": sql_query,
            "structured_form": translation.model_dump(mode="json"),
            "explanation": translation.explanation,
            "sql_query": sql_query,
            "graph_query_string": graph_query_string,
        }

    def _format_graph_query_string(self, query: GraphOperation) -> str:
        filters = ", ".join(f"{key}={value}" for key, value in query.filters.items()) or "all"
        if query.operation == "chain":
            return f"find_node({query.entity}, {filters}) -> chain(Order -> Delivery -> Invoice -> Payment)"
        if query.operation == "traverse":
            return f"find_node({query.entity}, {filters}) -> traverse({query.traverse_to}, depth={query.depth or 1})"
        if query.operation == "aggregate":
            return f"aggregate({query.entity}, field={query.aggregation_field}, op={query.aggregation})"
        if query.operation == "count":
            return f"count({query.entity}, {filters})"
        return f"find_node({query.entity}, {filters})"

    def _sql_literal(self, value: Any) -> str:
        escaped = str(value).replace("'", "''")
        return "'" + escaped + "'"

    def _build_where_clause(self, alias: str, filters: dict[str, Any]) -> str:
        clauses = [f"{alias}.{FIELD_ALIASES.get(key, key)} = {self._sql_literal(value)}" for key, value in filters.items()]
        return " AND ".join(clauses) if clauses else "1=1"

    def _build_sql_from_graph_operation(self, query: GraphOperation) -> str:
        entity = query.entity or "Order"
        table = ENTITY_TABLES.get(entity, "orders")
        alias = table[0]
        where_clause = self._build_where_clause(alias, query.filters)
        if query.operation in {"find_node", "filter"}:
            return f"SELECT {alias}.* FROM {table} {alias} WHERE {where_clause} LIMIT 50"
        if query.operation == "count":
            return f"SELECT COUNT(*) AS count FROM {table} {alias} WHERE {where_clause}"
        if query.operation == "aggregate":
            if entity == "Product" and (query.aggregation_field or "").lower() in {"invoice", "invoices", "billing", "billing_documents"}:
                return "SELECT p.id, p.name, COUNT(DISTINCT ip.invoice_id) AS value FROM products p LEFT JOIN invoice_products ip ON ip.product_id = p.id GROUP BY p.id, p.name ORDER BY value DESC LIMIT 50"
            field = FIELD_ALIASES.get(query.aggregation_field or "amount", query.aggregation_field or "amount")
            aggregation = (query.aggregation or "count").upper()
            if aggregation == "COUNT":
                return f"SELECT COUNT(*) AS value FROM {table} {alias} WHERE {where_clause}"
            return f"SELECT {alias}.id, {aggregation}(CAST({alias}.{field} AS REAL)) AS value FROM {table} {alias} WHERE {where_clause} GROUP BY {alias}.id ORDER BY value DESC LIMIT 50"
        if query.operation == "traverse":
            target = query.traverse_to or entity
            if entity == "Order" and target == "Delivery":
                return f"SELECT d.* FROM orders o JOIN order_deliveries od ON od.order_id = o.id JOIN deliveries d ON d.id = od.delivery_id WHERE {self._build_where_clause('o', query.filters)} LIMIT 50"
            if entity == "Delivery" and target == "Invoice":
                return f"SELECT i.* FROM deliveries d JOIN delivery_invoices di ON di.delivery_id = d.id JOIN invoices i ON i.id = di.invoice_id WHERE {self._build_where_clause('d', query.filters)} LIMIT 50"
            if entity == "Invoice" and target == "Payment":
                return f"SELECT p.* FROM invoices i JOIN invoice_payments ip ON ip.invoice_id = i.id JOIN payments p ON p.id = ip.payment_id WHERE {self._build_where_clause('i', query.filters)} LIMIT 50"
            if entity == "Order" and target == "Customer":
                return f"SELECT c.* FROM orders o JOIN customers c ON c.id = o.customer_id WHERE {self._build_where_clause('o', query.filters)} LIMIT 50"
            if entity == "Order" and target == "Product":
                return f"SELECT p.* FROM orders o JOIN order_products op ON op.order_id = o.id JOIN products p ON p.id = op.product_id WHERE {self._build_where_clause('o', query.filters)} LIMIT 50"
            if entity == "Customer" and target == "Address":
                return f"SELECT a.* FROM customers c JOIN customer_addresses ca ON ca.customer_id = c.id JOIN addresses a ON a.id = ca.address_id WHERE {self._build_where_clause('c', query.filters)} LIMIT 50"
            if entity == "Customer" and target == "Delivery":
                return f"SELECT DISTINCT d.* FROM customers c JOIN orders o ON o.customer_id = c.id JOIN order_deliveries od ON od.order_id = o.id JOIN deliveries d ON d.id = od.delivery_id WHERE {self._build_where_clause('c', query.filters)} LIMIT 50"
            return f"SELECT {alias}.* FROM {table} {alias} WHERE {where_clause} LIMIT 50"
        if query.operation == "chain":
            if entity == "Invoice":
                return f"SELECT i.id AS invoice_id, d.id AS delivery_id, o.id AS order_id, p.id AS payment_id FROM invoices i LEFT JOIN delivery_invoices di ON di.invoice_id = i.id LEFT JOIN deliveries d ON d.id = di.delivery_id LEFT JOIN order_deliveries od ON od.delivery_id = d.id LEFT JOIN orders o ON o.id = od.order_id LEFT JOIN invoice_payments ip ON ip.invoice_id = i.id LEFT JOIN payments p ON p.id = ip.payment_id WHERE {self._build_where_clause('i', query.filters)} LIMIT 50"
            if entity == "Order":
                return f"SELECT o.id AS order_id, d.id AS delivery_id, i.id AS invoice_id, p.id AS payment_id FROM orders o LEFT JOIN order_deliveries od ON od.order_id = o.id LEFT JOIN deliveries d ON d.id = od.delivery_id LEFT JOIN delivery_invoices di ON di.delivery_id = d.id LEFT JOIN invoices i ON i.id = di.invoice_id LEFT JOIN invoice_payments ip ON ip.invoice_id = i.id LEFT JOIN payments p ON p.id = ip.payment_id WHERE {self._build_where_clause('o', query.filters)} LIMIT 50"
        return f"SELECT {alias}.* FROM {table} {alias} WHERE {where_clause} LIMIT 50"

    def _execute_graph(self, query: GraphOperation) -> dict[str, Any]:
        handlers = {"find_node": self._execute_find_node, "traverse": self._execute_traverse, "filter": self._execute_filter, "aggregate": self._execute_aggregate, "count": self._execute_count, "chain": self._execute_chain}
        handler = handlers.get(query.operation)
        return handler(query) if handler is not None else {"operation": query.operation, "records": [], "path_edges": [], "error": "Unsupported operation"}

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
            if actual is None:
                return False
            expected_str = str(expected).lower()
            if isinstance(actual, list):
                if not any(expected_str in str(item).lower() for item in actual):
                    return False
            elif expected_str not in str(actual).lower():
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

    def _execute_filter(self, query: GraphOperation) -> dict[str, Any]:
        return self._execute_find_node(query)

    def _execute_count(self, query: GraphOperation) -> dict[str, Any]:
        records = [self._node_payload(key, attrs) for key, attrs in self._matching_nodes(query.entity, query.filters)]
        return {"operation": query.operation, "count": len(records), "records": records, "path_edges": []}

    def _execute_traverse(self, query: GraphOperation) -> dict[str, Any]:
        depth = query.depth or 1
        start_nodes = self._matching_nodes(query.entity, query.filters)
        seen: dict[str, dict[str, Any]] = {}
        path_edges: dict[str, dict[str, Any]] = {}
        target_type = query.traverse_to.lower() if query.traverse_to else None
        for node_key, _ in start_nodes:
            subgraph = self.builder.get_subgraph(node_key, depth)
            for sub_key, attrs in subgraph.nodes(data=True):
                if target_type and attrs.get("entity_type") != target_type and sub_key != node_key:
                    continue
                seen.setdefault(sub_key, self._node_payload(sub_key, dict(attrs)))
            for source, target, key, attrs in subgraph.edges(keys=True, data=True):
                if source in seen and target in seen:
                    path_edges.setdefault(key, self._edge_payload(source, target, key, dict(attrs)))
        return {"operation": query.operation, "records": list(seen.values()), "path_edges": list(path_edges.values())}

    def _execute_aggregate(self, query: GraphOperation) -> dict[str, Any]:
        matches = self._matching_nodes(query.entity, query.filters)
        aggregation = (query.aggregation or "count").lower()
        field = FIELD_ALIASES.get(query.aggregation_field or "", query.aggregation_field)
        rows = []
        for node_key, attrs in matches:
            value = attrs.get(field) if field else None
            if value is None and isinstance(attrs.get("metadata"), dict) and field:
                value = attrs["metadata"].get(field)
            if aggregation == "count":
                metric = len(value) if isinstance(value, list) else 1
            elif aggregation == "max" and isinstance(value, list):
                metric = len(value)
            else:
                metric = self._to_number(value)
                if metric is None:
                    continue
            rows.append({"node_id": node_key, "entity_id": attrs.get("entity_id"), "entity_type": attrs.get("entity_type"), "value": metric})
        rows = sorted(rows, key=lambda item: item["value"], reverse=aggregation != "min")
        values = [row["value"] for row in rows]
        summary = sum(values) if values and aggregation == "sum" else (sum(values) / len(values) if values and aggregation == "avg" else max(values) if values and aggregation == "max" else min(values) if values and aggregation == "min" else len(rows) if aggregation == "count" else None)
        return {"operation": query.operation, "aggregation": aggregation, "aggregation_field": field, "summary": summary, "records": rows[:50], "path_edges": []}

    def _execute_chain(self, query: GraphOperation) -> dict[str, Any]:
        start_nodes = self._matching_nodes(query.entity, query.filters)
        graph = self.builder.graph
        chains = []
        path_edges: dict[str, dict[str, Any]] = {}

        def add_chain_edge(source: str, target: str) -> None:
            if graph.has_edge(source, target):
                for key, attrs in graph[source][target].items():
                    path_edges.setdefault(key, self._edge_payload(source, target, key, dict(attrs)))

        for node_key, attrs in start_nodes[:20]:
            entity_type = attrs.get("entity_type")
            collected: dict[str, dict[str, Any]] = {node_key: self._node_payload(node_key, dict(attrs))}
            if entity_type == "order":
                delivery_keys = [key for key in graph.successors(node_key) if graph.nodes[key].get("entity_type") == "delivery"]
                invoice_keys: list[str] = []
                payment_keys: list[str] = []
                for delivery_key in delivery_keys:
                    collected[delivery_key] = self._node_payload(delivery_key, dict(graph.nodes[delivery_key]))
                    add_chain_edge(node_key, delivery_key)
                    for invoice_key in graph.successors(delivery_key):
                        if graph.nodes[invoice_key].get("entity_type") == "invoice":
                            invoice_keys.append(invoice_key)
                for invoice_key in invoice_keys:
                    collected[invoice_key] = self._node_payload(invoice_key, dict(graph.nodes[invoice_key]))
                    for delivery_key in delivery_keys:
                        add_chain_edge(delivery_key, invoice_key)
                    for payment_key in graph.successors(invoice_key):
                        if graph.nodes[payment_key].get("entity_type") == "payment":
                            payment_keys.append(payment_key)
                for payment_key in payment_keys:
                    collected[payment_key] = self._node_payload(payment_key, dict(graph.nodes[payment_key]))
                    for invoice_key in invoice_keys:
                        add_chain_edge(invoice_key, payment_key)
            elif entity_type == "invoice":
                delivery_keys = [key for key in graph.predecessors(node_key) if graph.nodes[key].get("entity_type") == "delivery"]
                payment_keys = [key for key in graph.successors(node_key) if graph.nodes[key].get("entity_type") == "payment"]
                order_keys: list[str] = []
                for delivery_key in delivery_keys:
                    collected[delivery_key] = self._node_payload(delivery_key, dict(graph.nodes[delivery_key]))
                    add_chain_edge(delivery_key, node_key)
                    for order_key in graph.predecessors(delivery_key):
                        if graph.nodes[order_key].get("entity_type") == "order":
                            order_keys.append(order_key)
                for order_key in order_keys:
                    collected[order_key] = self._node_payload(order_key, dict(graph.nodes[order_key]))
                    for delivery_key in delivery_keys:
                        add_chain_edge(order_key, delivery_key)
                for payment_key in payment_keys:
                    collected[payment_key] = self._node_payload(payment_key, dict(graph.nodes[payment_key]))
                    add_chain_edge(node_key, payment_key)
            elif entity_type == "payment":
                invoice_keys = [key for key in graph.predecessors(node_key) if graph.nodes[key].get("entity_type") == "invoice"]
                delivery_keys: list[str] = []
                order_keys: list[str] = []
                for invoice_key in invoice_keys:
                    collected[invoice_key] = self._node_payload(invoice_key, dict(graph.nodes[invoice_key]))
                    add_chain_edge(invoice_key, node_key)
                    for delivery_key in graph.predecessors(invoice_key):
                        if graph.nodes[delivery_key].get("entity_type") == "delivery":
                            delivery_keys.append(delivery_key)
                for delivery_key in delivery_keys:
                    collected[delivery_key] = self._node_payload(delivery_key, dict(graph.nodes[delivery_key]))
                    for invoice_key in invoice_keys:
                        add_chain_edge(delivery_key, invoice_key)
                    for order_key in graph.predecessors(delivery_key):
                        if graph.nodes[order_key].get("entity_type") == "order":
                            order_keys.append(order_key)
                for order_key in order_keys:
                    collected[order_key] = self._node_payload(order_key, dict(graph.nodes[order_key]))
                    for delivery_key in delivery_keys:
                        add_chain_edge(order_key, delivery_key)
            ordered = sorted(collected.values(), key=lambda item: (TYPE_ORDER.get(item.get("entity_type"), 99), item.get("node_id", "")))
            chains.append({"start_node_id": node_key, "chain": ordered})
        return {"operation": query.operation, "records": chains, "path_edges": list(path_edges.values())}

    def _to_number(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def _build_raw_data(self, graph_result: dict[str, Any], sql_result: Any) -> dict[str, Any]:
        return {"graph_result": graph_result, "sql_result": {"query": sql_result.query, "rows": sql_result.rows, "error": sql_result.error}}

    async def _generate_answer(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> str:
        if not is_gemini_available():
            answer = self._mock_answer(question, translation, raw_data)
            self._append_log(stage="answer-mock", question=question, prompt="Mock answer generator used", response=answer, notes="No Gemini API key found, using mock mode")
            return answer
        prompt, system_instruction = self._build_answer_prompt(question, translation, raw_data)
        try:
            response = await call_gemini(prompt, system_instruction)
            self._append_log(stage="answer-llm", question=question, prompt=prompt, response=response, notes="Answer generated from graph and SQL results.")
            return response
        except Exception as exc:
            answer = self._mock_answer(question, translation, raw_data)
            self._append_log(stage="answer-llm-fallback", question=question, prompt=prompt, response=answer, notes=f"Gemini failed, fallback used: {exc}")
            return answer

    async def _generate_answer_stream(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> AsyncIterator[str]:
        if not is_gemini_available():
            answer = self._mock_answer(question, translation, raw_data)
            for token in self._tokenize(answer):
                yield token
                await asyncio.sleep(0.02)
            self._append_log(stage="answer-stream-mock", question=question, prompt="Mock answer stream used", response=answer, notes="No Gemini API key found, using mock streaming mode.")
            return
        prompt, system_instruction = self._build_answer_prompt(question, translation, raw_data)
        chunks: list[str] = []
        try:
            async for token in stream_gemini(prompt, system_instruction):
                chunks.append(token)
                yield token
            self._append_log(stage="answer-stream-llm", question=question, prompt=prompt, response="".join(chunks), notes="Streaming answer generated from graph and SQL results.")
        except Exception as exc:
            answer = self._mock_answer(question, translation, raw_data)
            for token in self._tokenize(answer):
                yield token
                await asyncio.sleep(0.02)
            self._append_log(stage="answer-stream-fallback", question=question, prompt=prompt, response=answer, notes=f"Streaming Gemini failed, fallback used: {exc}")

    def _build_answer_prompt(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> tuple[str, str]:
        truncated = json.dumps(raw_data, indent=2, default=str)[:12000]
        system_instruction = "ROLE: You are a data analyst presenting query results."
        prompt = (
            f"CONTEXT:\n{truncated}\n\nQUESTION: {question}\nGENERATED QUERY: {translation.model_dump_json(indent=2)}\n\n"
            "TASK: Answer the user's question based ONLY on this data. Do not make up information.\n"
            "FORMAT: Respond with a clear natural language paragraph. If the data is tabular, include a brief summary."
        )
        return prompt, system_instruction

    def _mock_answer(self, question: str, translation: TranslationPayload, raw_data: dict[str, Any]) -> str:
        graph_result = raw_data.get("graph_result", {})
        records = graph_result.get("records", []) if isinstance(graph_result, dict) else []
        if translation.graph_operation.operation == "count":
            count = graph_result.get("count", len(records))
            return f"I found {count} matching {translation.graph_operation.entity or 'records'} in the graph and validated the count against the SQLite tables."
        if translation.graph_operation.operation == "aggregate" and records:
            top = records[0]
            return f"The top matching {translation.graph_operation.entity or 'record'} is {top.get('entity_id')} with value {top.get('value')}."
        if translation.graph_operation.operation == "chain" and records:
            chain_ids = " -> ".join(node.get("entity_id", "") for node in records[0]["chain"])
            return f"I traced the connected flow as {chain_ids}."
        if not records:
            return "I could not find matching records in the dataset for that question."
        sample_ids = ", ".join(str(record.get("entity_id", "")) for record in records[:5])
        return f"I found {len(records)} graph matches for your question. Sample IDs: {sample_ids}."

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"\S+\s*", text)
        return tokens or [text]

    def _collect_relevant_node_ids(self, graph_result: dict[str, Any] | None) -> list[str]:
        if graph_result is None:
            return []
        collected: set[str] = set()
        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key in ("node_id", "entity_id", "start_node_id"):
                    if key in value and value[key]:
                        collected.add(str(value[key]))
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(graph_result)
        return sorted(collected)

    def _append_log(self, *, stage: str, question: str, prompt: str, response: str, notes: str) -> None:
        timestamp = datetime.utcnow().isoformat() + "Z"
        entry = f"\n\n## {timestamp} | {stage}\n- Question: {question}\n- Notes: {notes}\n\n### Prompt\n```text\n{prompt}\n```\n\n### Response\n```text\n{response}\n```\n"
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(entry)

