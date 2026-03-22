from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.agents.llm_client import call_gemini, is_gemini_available
from backend.agents.schema_context import get_schema_prompt
from backend.services.graph_builder import GraphBuilder
from backend.services.graph_store import graph_store

LOGGER = logging.getLogger(__name__)
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "llm_sessions.md"
TYPE_ORDER = {
    "address": 0,
    "customer": 1,
    "order": 2,
    "delivery": 3,
    "invoice": 4,
    "payment": 5,
    "product": 6,
}


class StructuredQuery(BaseModel):
    operation: str
    entity: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    traverse_to: str | None = None
    depth: int | None = None
    aggregation: str | None = None
    aggregation_field: str | None = None
    reason: str | None = None


class QueryPipeline:
    DOMAIN_TERMS = {
        "order", "orders", "delivery", "deliveries", "invoice", "invoices",
        "payment", "payments", "customer", "customers", "product", "products",
        "address", "addresses", "billing", "billing document", "sales order",
        "graph", "flow", "chain", "sap", "o2c",
    }
    REJECTION_MESSAGE = "This system is designed to answer questions related to the dataset only."

    def __init__(self, builder: GraphBuilder | None = None) -> None:
        self.builder = builder or graph_store.graph

    async def run(self, question: str) -> dict[str, Any]:
        question = question.strip()
        if not self._passes_guardrail(question):
            self._append_log(
                stage="guardrail",
                question=question,
                prompt="",
                response=self.REJECTION_MESSAGE,
                notes="Rejected as out-of-domain query.",
            )
            return {
                "answer": self.REJECTION_MESSAGE,
                "relevant_node_ids": [],
                "raw_data": None,
            }

        structured_query = await self._translate(question)
        if structured_query.operation == "rejected":
            self._append_log(
                stage="translation",
                question=question,
                prompt="",
                response=structured_query.model_dump_json(indent=2),
                notes="Translation rejected by guardrail or parser.",
            )
            return {
                "answer": structured_query.reason or self.REJECTION_MESSAGE,
                "relevant_node_ids": [],
                "raw_data": None,
            }

        self._append_log(
            stage="translation-refinement",
            question=question,
            prompt="Normalized structured query prepared for graph execution",
            response=structured_query.model_dump_json(indent=2),
            notes="Structured query accepted and passed to the Python executor.",
        )

        raw_data = self._execute(structured_query)
        answer = await self._generate_answer(question, structured_query, raw_data)
        return {
            "answer": answer,
            "relevant_node_ids": self._collect_relevant_node_ids(raw_data),
            "raw_data": raw_data,
        }

    def _passes_guardrail(self, question: str) -> bool:
        lowered = question.lower()
        if any(term in lowered for term in self.DOMAIN_TERMS):
            return True
        if re.search(r"\b(74\d{4}|80\d{6}|90\d{6}|91\d{6}|94\d{8})\b", lowered):
            return True
        return False

    async def _translate(self, question: str) -> StructuredQuery:
        if not is_gemini_available():
            LOGGER.warning("No Gemini API key found, using mock mode")
            translated = self._mock_translate(question)
            self._append_log(
                stage="translation-mock",
                question=question,
                prompt="Mock translator used",
                response=translated.model_dump_json(indent=2),
                notes="No Gemini API key found, using mock mode",
            )
            return translated

        schema_prompt = get_schema_prompt(self.builder)
        system_instruction = (
            "ROLE: You are a query translator for a graph database containing SAP Order-to-Cash data. "
            "You convert user questions into strict JSON only."
        )
        prompt = (
            f"SCHEMA CONTEXT:\n{schema_prompt}\n\n"
            "TASK: Convert this natural language query into a structured JSON query.\n"
            "OUTPUT FORMAT:\n"
            "{\n"
            '  "operation": "find_node" | "traverse" | "filter" | "aggregate" | "count" | "chain",\n'
            '  "entity": "Order" | "Customer" | "Delivery" | "Invoice" | "Payment" | "Product" | "Address",\n'
            '  "filters": {"field_name": "value"},\n'
            '  "traverse_to": "Delivery",\n'
            '  "depth": 1,\n'
            '  "aggregation": "sum" | "count" | "avg" | "max" | "min",\n'
            '  "aggregation_field": "amount"\n'
            "}\n\n"
            f"QUESTION: {question}"
        )

        for attempt in range(2):
            active_prompt = prompt if attempt == 0 else prompt + "\n\nReturn ONLY valid JSON. No markdown, no commentary."
            try:
                response = await call_gemini(active_prompt, system_instruction)
                parsed = self._parse_structured_query(response)
                self._append_log(
                    stage=f"translation-llm-attempt-{attempt + 1}",
                    question=question,
                    prompt=active_prompt,
                    response=response,
                    notes="Translation successful.",
                )
                return parsed
            except Exception as exc:
                self._append_log(
                    stage=f"translation-llm-attempt-{attempt + 1}",
                    question=question,
                    prompt=active_prompt,
                    response=str(exc),
                    notes="Translation attempt failed.",
                )
        return StructuredQuery(operation="rejected", reason="Unable to translate the query into a supported graph operation.")

    def _parse_structured_query(self, response: str) -> StructuredQuery:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in translator response")
        payload = json.loads(match.group(0))
        return StructuredQuery.model_validate(payload)

    def _mock_translate(self, question: str) -> StructuredQuery:
        lowered = question.lower()
        entity = self._detect_entity(question)
        record_id = self._extract_id(question)

        if any(term in lowered for term in ["chain", "flow", "trace"]):
            return StructuredQuery(
                operation="chain",
                entity=entity or self._entity_from_id(record_id) or "Order",
                filters={"id": record_id} if record_id else {},
                depth=4,
            )
        if "count" in lowered:
            return StructuredQuery(operation="count", entity=entity or "Order", filters={})
        if "highest" in lowered or "max" in lowered:
            return StructuredQuery(
                operation="aggregate",
                entity=entity or "Product",
                filters={},
                aggregation="max",
                aggregation_field="invoices",
            )
        customer_match = re.search(r"orders? for customer\s+([\w-]+)", lowered)
        if customer_match:
            return StructuredQuery(
                operation="filter",
                entity="Order",
                filters={"customer_id": customer_match.group(1)},
            )
        if record_id:
            return StructuredQuery(
                operation="find_node",
                entity=self._entity_from_id(record_id) or entity or "Order",
                filters={"id": record_id},
            )
        if "all" in lowered or "show" in lowered or "list" in lowered:
            return StructuredQuery(operation="find_node", entity=entity or "Order", filters={})
        return StructuredQuery(operation="filter", entity=entity or "Order", filters={})

    def _detect_entity(self, question: str) -> str | None:
        lowered = question.lower()
        mapping = {
            "order": "Order",
            "delivery": "Delivery",
            "invoice": "Invoice",
            "payment": "Payment",
            "customer": "Customer",
            "product": "Product",
            "address": "Address",
        }
        for key, value in mapping.items():
            if key in lowered or f"{key}s" in lowered:
                return value
        return None

    def _extract_id(self, question: str) -> str | None:
        match = re.search(r"\b\d{6,10}\b", question)
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
        return None

    def _execute(self, query: StructuredQuery) -> dict[str, Any]:
        handlers = {
            "find_node": self._execute_find_node,
            "traverse": self._execute_traverse,
            "filter": self._execute_filter,
            "aggregate": self._execute_aggregate,
            "count": self._execute_count,
            "chain": self._execute_chain,
        }
        handler = handlers.get(query.operation)
        if handler is None:
            return {"operation": query.operation, "records": [], "error": "Unsupported operation"}
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
            if expected is None:
                continue
            expected_str = str(expected).lower()
            if field == "id":
                actual = attrs.get("entity_id")
            else:
                actual = attrs.get(field, metadata.get(field))
            if actual is None:
                return False
            if isinstance(actual, list):
                if not any(expected_str in str(item).lower() for item in actual):
                    return False
            else:
                if expected_str not in str(actual).lower():
                    return False
        return True

    def _node_payload(self, node_key: str, attrs: dict[str, Any]) -> dict[str, Any]:
        payload = dict(attrs)
        payload["node_id"] = node_key
        return payload

    def _execute_find_node(self, query: StructuredQuery) -> dict[str, Any]:
        matches = [self._node_payload(key, attrs) for key, attrs in self._matching_nodes(query.entity, query.filters)]
        return {"operation": query.operation, "records": matches}

    def _execute_filter(self, query: StructuredQuery) -> dict[str, Any]:
        return self._execute_find_node(query)

    def _execute_count(self, query: StructuredQuery) -> dict[str, Any]:
        matches = [self._node_payload(key, attrs) for key, attrs in self._matching_nodes(query.entity, query.filters)]
        return {"operation": query.operation, "count": len(matches), "records": matches}

    def _execute_traverse(self, query: StructuredQuery) -> dict[str, Any]:
        depth = query.depth or 1
        start_nodes = self._matching_nodes(query.entity, query.filters)
        seen: dict[str, dict[str, Any]] = {}
        target_type = query.traverse_to.lower() if query.traverse_to else None
        for node_key, _ in start_nodes:
            subgraph = self.builder.get_subgraph(node_key, depth)
            for sub_key, attrs in subgraph.nodes(data=True):
                if target_type and attrs.get("entity_type") != target_type:
                    continue
                seen.setdefault(sub_key, self._node_payload(sub_key, dict(attrs)))
        return {"operation": query.operation, "records": list(seen.values())}

    def _execute_aggregate(self, query: StructuredQuery) -> dict[str, Any]:
        matches = self._matching_nodes(query.entity, query.filters)
        aggregation = (query.aggregation or "count").lower()
        field = query.aggregation_field
        rows = []
        for node_key, attrs in matches:
            if field:
                value = attrs.get(field)
                if value is None and isinstance(attrs.get("metadata"), dict):
                    value = attrs["metadata"].get(field)
            else:
                value = None

            if aggregation == "count":
                metric = len(value) if isinstance(value, list) else (1 if value is not None else 1)
            else:
                metric = self._to_number(value)
                if metric is None:
                    continue
            rows.append({
                "node_id": node_key,
                "entity_id": attrs.get("entity_id"),
                "entity_type": attrs.get("entity_type"),
                "value": metric,
            })

        if aggregation == "max":
            rows = sorted(rows, key=lambda item: item["value"], reverse=True)
        elif aggregation == "min":
            rows = sorted(rows, key=lambda item: item["value"])
        summary = None
        values = [row["value"] for row in rows]
        if values and aggregation in {"sum", "avg", "max", "min"}:
            if aggregation == "sum":
                summary = sum(values)
            elif aggregation == "avg":
                summary = sum(values) / len(values)
            elif aggregation == "max":
                summary = max(values)
            elif aggregation == "min":
                summary = min(values)
        return {"operation": query.operation, "aggregation": aggregation, "aggregation_field": field, "summary": summary, "records": rows[:50]}

    def _execute_chain(self, query: StructuredQuery) -> dict[str, Any]:
        start_nodes = self._matching_nodes(query.entity, query.filters)
        graph = self.builder.graph
        chains = []

        for node_key, attrs in start_nodes[:20]:
            entity_type = attrs.get("entity_type")
            collected: dict[str, dict[str, Any]] = {node_key: self._node_payload(node_key, dict(attrs))}

            if entity_type == "order":
                delivery_keys = [key for key in graph.successors(node_key) if graph.nodes[key].get("entity_type") == "delivery"]
                invoice_keys = []
                payment_keys = []
                for delivery_key in delivery_keys:
                    collected[delivery_key] = self._node_payload(delivery_key, dict(graph.nodes[delivery_key]))
                    for invoice_key in graph.successors(delivery_key):
                        if graph.nodes[invoice_key].get("entity_type") == "invoice":
                            invoice_keys.append(invoice_key)
                for invoice_key in invoice_keys:
                    collected[invoice_key] = self._node_payload(invoice_key, dict(graph.nodes[invoice_key]))
                    for payment_key in graph.successors(invoice_key):
                        if graph.nodes[payment_key].get("entity_type") == "payment":
                            payment_keys.append(payment_key)
                for payment_key in payment_keys:
                    collected[payment_key] = self._node_payload(payment_key, dict(graph.nodes[payment_key]))

            elif entity_type == "delivery":
                order_keys = [key for key in graph.predecessors(node_key) if graph.nodes[key].get("entity_type") == "order"]
                invoice_keys = [key for key in graph.successors(node_key) if graph.nodes[key].get("entity_type") == "invoice"]
                payment_keys = []
                for order_key in order_keys:
                    collected[order_key] = self._node_payload(order_key, dict(graph.nodes[order_key]))
                for invoice_key in invoice_keys:
                    collected[invoice_key] = self._node_payload(invoice_key, dict(graph.nodes[invoice_key]))
                    for payment_key in graph.successors(invoice_key):
                        if graph.nodes[payment_key].get("entity_type") == "payment":
                            payment_keys.append(payment_key)
                for payment_key in payment_keys:
                    collected[payment_key] = self._node_payload(payment_key, dict(graph.nodes[payment_key]))

            elif entity_type == "invoice":
                delivery_keys = [key for key in graph.predecessors(node_key) if graph.nodes[key].get("entity_type") == "delivery"]
                payment_keys = [key for key in graph.successors(node_key) if graph.nodes[key].get("entity_type") == "payment"]
                order_keys = []
                for delivery_key in delivery_keys:
                    collected[delivery_key] = self._node_payload(delivery_key, dict(graph.nodes[delivery_key]))
                    for order_key in graph.predecessors(delivery_key):
                        if graph.nodes[order_key].get("entity_type") == "order":
                            order_keys.append(order_key)
                for order_key in order_keys:
                    collected[order_key] = self._node_payload(order_key, dict(graph.nodes[order_key]))
                for payment_key in payment_keys:
                    collected[payment_key] = self._node_payload(payment_key, dict(graph.nodes[payment_key]))

            elif entity_type == "payment":
                invoice_keys = [key for key in graph.predecessors(node_key) if graph.nodes[key].get("entity_type") == "invoice"]
                delivery_keys = []
                order_keys = []
                for invoice_key in invoice_keys:
                    collected[invoice_key] = self._node_payload(invoice_key, dict(graph.nodes[invoice_key]))
                    for delivery_key in graph.predecessors(invoice_key):
                        if graph.nodes[delivery_key].get("entity_type") == "delivery":
                            delivery_keys.append(delivery_key)
                for delivery_key in delivery_keys:
                    collected[delivery_key] = self._node_payload(delivery_key, dict(graph.nodes[delivery_key]))
                    for order_key in graph.predecessors(delivery_key):
                        if graph.nodes[order_key].get("entity_type") == "order":
                            order_keys.append(order_key)
                for order_key in order_keys:
                    collected[order_key] = self._node_payload(order_key, dict(graph.nodes[order_key]))

            ordered = sorted(
                collected.values(),
                key=lambda item: (TYPE_ORDER.get(item.get("entity_type"), 99), item.get("node_id", "")),
            )
            chains.append({"start_node_id": node_key, "chain": ordered})

        return {"operation": query.operation, "records": chains}

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

    async def _generate_answer(self, question: str, structured_query: StructuredQuery, raw_data: dict[str, Any]) -> str:
        records = raw_data.get("records", []) if isinstance(raw_data, dict) else []
        if not is_gemini_available():
            answer = self._mock_answer(question, structured_query, raw_data)
            self._append_log(
                stage="answer-mock",
                question=question,
                prompt="Mock answer generator used",
                response=answer,
                notes="No Gemini API key found, using mock mode",
            )
            return answer

        truncated = json.dumps(raw_data, indent=2, default=str)[:12000]
        system_instruction = "ROLE: You are a data analyst presenting query results."
        prompt = (
            f"CONTEXT:\n{truncated}\n\n"
            f"QUESTION: {question}\n"
            f"STRUCTURED QUERY: {structured_query.model_dump_json(indent=2)}\n\n"
            "TASK: Answer the user's question based ONLY on this data. Do not make up information.\n"
            "FORMAT: Respond with a clear natural language paragraph. If the data is tabular, include a brief summary."
        )
        try:
            response = await call_gemini(prompt, system_instruction)
            self._append_log(
                stage="answer-llm",
                question=question,
                prompt=prompt,
                response=response,
                notes=f"Generated from {min(len(records), 50)} records.",
            )
            return response
        except Exception as exc:
            answer = self._mock_answer(question, structured_query, raw_data)
            self._append_log(
                stage="answer-llm-fallback",
                question=question,
                prompt=prompt,
                response=answer,
                notes=f"Gemini failed, fallback used: {exc}",
            )
            return answer

    def _mock_answer(self, question: str, structured_query: StructuredQuery, raw_data: dict[str, Any]) -> str:
        records = raw_data.get("records", []) if isinstance(raw_data, dict) else []
        if structured_query.operation == "count":
            return f"I found {raw_data.get('count', 0)} matching {structured_query.entity or 'records'} in the graph."
        if structured_query.operation == "aggregate":
            if not records:
                return "I could not find any records for that aggregation."
            top = records[0]
            return (
                f"I analyzed the matching {structured_query.entity or 'records'} and found the top result has value "
                f"{top.get('value')} for node {top.get('entity_id')}."
            )
        if structured_query.operation == "chain" and records:
            chain = records[0]["chain"]
            chain_ids = " -> ".join(node.get("entity_id", "") for node in chain)
            return f"I found a related chain in the graph: {chain_ids}."
        if not records:
            return "I could not find matching records in the dataset for that question."
        sample_ids = ", ".join(record.get("entity_id", "") for record in records[:5])
        return f"I found {len(records)} matching records for your question. Sample IDs: {sample_ids}."

    def _collect_relevant_node_ids(self, raw_data: dict[str, Any] | None) -> list[str]:
        if raw_data is None:
            return []
        collected: set[str] = set()

        def _walk(value: Any) -> None:
            if isinstance(value, dict):
                for key in ("node_id", "entity_id", "start_node_id"):
                    if key in value and value[key]:
                        collected.add(str(value[key]))
                for nested in value.values():
                    _walk(nested)
            elif isinstance(value, list):
                for item in value:
                    _walk(item)

        _walk(raw_data)
        return sorted(collected)

    def _append_log(self, *, stage: str, question: str, prompt: str, response: str, notes: str) -> None:
        timestamp = datetime.utcnow().isoformat() + "Z"
        entry = (
            f"\n\n## {timestamp} | {stage}\n"
            f"- Question: {question}\n"
            f"- Notes: {notes}\n\n"
            "### Prompt\n"
            f"```text\n{prompt}\n```\n\n"
            "### Response\n"
            f"```text\n{response}\n```\n"
        )
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(entry)
