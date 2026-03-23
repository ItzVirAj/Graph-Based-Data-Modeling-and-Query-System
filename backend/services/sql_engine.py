from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from backend.services.data_loader import NormalizedData

BANNED_SQL_PATTERNS = [
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b", re.IGNORECASE),
    re.compile(r"\bINSERT\b", re.IGNORECASE),
    re.compile(r"\bALTER\b", re.IGNORECASE),
    re.compile(r";.+\S", re.DOTALL),
]


@dataclass
class SqlExecutionResult:
    query: str
    rows: list[dict[str, Any]]
    error: str | None = None


class SqlEngine:
    def __init__(self, data: NormalizedData) -> None:
        self.data = data
        self.connection = sqlite3.connect(":memory:", check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._create_tables()
        self._load_data()

    def _create_tables(self) -> None:
        cursor = self.connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE customers (
                id TEXT PRIMARY KEY,
                business_partner_id TEXT,
                name TEXT,
                language TEXT,
                is_blocked INTEGER,
                is_archived INTEGER,
                address_ids_json TEXT,
                company_codes_json TEXT,
                sales_areas_json TEXT,
                metadata_json TEXT
            );
            CREATE TABLE addresses (
                id TEXT PRIMARY KEY,
                business_partner_id TEXT,
                city TEXT,
                country TEXT,
                postal_code TEXT,
                region TEXT,
                street TEXT,
                timezone TEXT,
                valid_from TEXT,
                valid_to TEXT,
                metadata_json TEXT
            );
            CREATE TABLE products (
                id TEXT PRIMARY KEY,
                name TEXT,
                base_unit TEXT,
                product_type TEXT,
                product_group TEXT,
                division TEXT,
                legacy_product_id TEXT,
                is_deleted INTEGER,
                metadata_json TEXT
            );
            CREATE TABLE orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT,
                order_type TEXT,
                status TEXT,
                amount TEXT,
                currency TEXT,
                created_at TEXT,
                requested_delivery_date TEXT,
                product_ids_json TEXT,
                metadata_json TEXT
            );
            CREATE TABLE deliveries (
                id TEXT PRIMARY KEY,
                shipping_point TEXT,
                status TEXT,
                created_at TEXT,
                goods_movement_at TEXT,
                order_ids_json TEXT,
                delivery_item_ids_json TEXT,
                product_ids_json TEXT,
                metadata_json TEXT
            );
            CREATE TABLE invoices (
                id TEXT PRIMARY KEY,
                customer_id TEXT,
                accounting_document_id TEXT,
                company_code TEXT,
                fiscal_year TEXT,
                amount TEXT,
                currency TEXT,
                invoice_date TEXT,
                created_at TEXT,
                is_cancelled INTEGER,
                delivery_ids_json TEXT,
                product_ids_json TEXT,
                metadata_json TEXT
            );
            CREATE TABLE payments (
                id TEXT PRIMARY KEY,
                customer_id TEXT,
                amount TEXT,
                currency TEXT,
                company_code TEXT,
                fiscal_year TEXT,
                posting_date TEXT,
                clearing_document_id TEXT,
                invoice_ids_json TEXT,
                metadata_json TEXT
            );
            CREATE TABLE customer_addresses (
                customer_id TEXT,
                address_id TEXT
            );
            CREATE TABLE order_products (
                order_id TEXT,
                product_id TEXT
            );
            CREATE TABLE order_deliveries (
                order_id TEXT,
                delivery_id TEXT
            );
            CREATE TABLE delivery_products (
                delivery_id TEXT,
                product_id TEXT
            );
            CREATE TABLE delivery_invoices (
                delivery_id TEXT,
                invoice_id TEXT
            );
            CREATE TABLE invoice_products (
                invoice_id TEXT,
                product_id TEXT
            );
            CREATE TABLE invoice_payments (
                invoice_id TEXT,
                payment_id TEXT
            );
            """
        )
        self.connection.commit()

    def _serialize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return json.dumps(value)
        if isinstance(value, dict):
            return json.dumps(value)
        return value

    def _insert_many(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        values = [tuple(self._serialize(row[column]) for column in columns) for row in rows]
        self.connection.executemany(sql, values)

    def _load_data(self) -> None:
        self._insert_many(
            "customers",
            [
                {
                    "id": record.id,
                    "business_partner_id": record.business_partner_id,
                    "name": record.name,
                    "language": record.language,
                    "is_blocked": record.is_blocked,
                    "is_archived": record.is_archived,
                    "address_ids_json": record.address_ids,
                    "company_codes_json": record.company_codes,
                    "sales_areas_json": record.sales_areas,
                    "metadata_json": record.metadata,
                }
                for record in self.data.customers
            ],
        )
        self._insert_many(
            "addresses",
            [
                {
                    "id": record.id,
                    "business_partner_id": record.business_partner_id,
                    "city": record.city,
                    "country": record.country,
                    "postal_code": record.postal_code,
                    "region": record.region,
                    "street": record.street,
                    "timezone": record.timezone,
                    "valid_from": record.valid_from,
                    "valid_to": record.valid_to,
                    "metadata_json": record.metadata,
                }
                for record in self.data.addresses
            ],
        )
        self._insert_many(
            "products",
            [
                {
                    "id": record.id,
                    "name": record.name,
                    "base_unit": record.base_unit,
                    "product_type": record.product_type,
                    "product_group": record.product_group,
                    "division": record.division,
                    "legacy_product_id": record.legacy_product_id,
                    "is_deleted": record.is_deleted,
                    "metadata_json": record.metadata,
                }
                for record in self.data.products
            ],
        )
        self._insert_many(
            "orders",
            [
                {
                    "id": record.id,
                    "customer_id": record.customer_id,
                    "order_type": record.order_type,
                    "status": record.status,
                    "amount": record.amount,
                    "currency": record.currency,
                    "created_at": record.created_at,
                    "requested_delivery_date": record.requested_delivery_date,
                    "product_ids_json": record.product_ids,
                    "metadata_json": record.metadata,
                }
                for record in self.data.orders
            ],
        )
        self._insert_many(
            "deliveries",
            [
                {
                    "id": record.id,
                    "shipping_point": record.shipping_point,
                    "status": record.status,
                    "created_at": record.created_at,
                    "goods_movement_at": record.goods_movement_at,
                    "order_ids_json": record.order_ids,
                    "delivery_item_ids_json": record.delivery_item_ids,
                    "product_ids_json": record.product_ids,
                    "metadata_json": record.metadata,
                }
                for record in self.data.deliveries
            ],
        )
        self._insert_many(
            "invoices",
            [
                {
                    "id": record.id,
                    "customer_id": record.customer_id,
                    "accounting_document_id": record.accounting_document_id,
                    "company_code": record.company_code,
                    "fiscal_year": record.fiscal_year,
                    "amount": record.amount,
                    "currency": record.currency,
                    "invoice_date": record.invoice_date,
                    "created_at": record.created_at,
                    "is_cancelled": record.is_cancelled,
                    "delivery_ids_json": record.delivery_ids,
                    "product_ids_json": record.product_ids,
                    "metadata_json": record.metadata,
                }
                for record in self.data.invoices
            ],
        )
        self._insert_many(
            "payments",
            [
                {
                    "id": record.id,
                    "customer_id": record.customer_id,
                    "amount": record.amount,
                    "currency": record.currency,
                    "company_code": record.company_code,
                    "fiscal_year": record.fiscal_year,
                    "posting_date": record.posting_date,
                    "clearing_document_id": record.clearing_document_id,
                    "invoice_ids_json": record.invoice_ids,
                    "metadata_json": record.metadata,
                }
                for record in self.data.payments
            ],
        )
        self._insert_many(
            "customer_addresses",
            [
                {"customer_id": customer.id, "address_id": address_id}
                for customer in self.data.customers
                for address_id in customer.address_ids
            ],
        )
        self._insert_many(
            "order_products",
            [
                {"order_id": order.id, "product_id": product_id}
                for order in self.data.orders
                for product_id in order.product_ids
            ],
        )
        self._insert_many(
            "order_deliveries",
            [
                {"order_id": order_id, "delivery_id": delivery.id}
                for delivery in self.data.deliveries
                for order_id in delivery.order_ids
            ],
        )
        self._insert_many(
            "delivery_products",
            [
                {"delivery_id": delivery.id, "product_id": product_id}
                for delivery in self.data.deliveries
                for product_id in delivery.product_ids
            ],
        )
        self._insert_many(
            "delivery_invoices",
            [
                {"delivery_id": delivery_id, "invoice_id": invoice.id}
                for invoice in self.data.invoices
                for delivery_id in invoice.delivery_ids
            ],
        )
        self._insert_many(
            "invoice_products",
            [
                {"invoice_id": invoice.id, "product_id": product_id}
                for invoice in self.data.invoices
                for product_id in invoice.product_ids
            ],
        )
        self._insert_many(
            "invoice_payments",
            [
                {"invoice_id": invoice_id, "payment_id": payment.id}
                for payment in self.data.payments
                for invoice_id in payment.invoice_ids
            ],
        )
        self.connection.commit()

    def validate_sql(self, query_string: str) -> None:
        query = query_string.strip()
        if not query:
            raise ValueError("Generated SQL is empty.")
        lowered = query.lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise ValueError("Only SELECT statements are allowed.")
        for pattern in BANNED_SQL_PATTERNS:
            if pattern.search(query):
                raise ValueError("Unsafe SQL detected.")

    def execute_sql(self, query_string: str) -> SqlExecutionResult:
        try:
            self.validate_sql(query_string)
            cursor = self.connection.execute(query_string)
            rows = [dict(row) for row in cursor.fetchall()]
            return SqlExecutionResult(query=query_string, rows=rows)
        except Exception as exc:
            return SqlExecutionResult(query=query_string, rows=[], error=str(exc))

    def get_schema_overview(self) -> dict[str, list[str]]:
        schema: dict[str, list[str]] = {}
        cursor = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            pragma = self.connection.execute(f"PRAGMA table_info({table})")
            schema[table] = [row[1] for row in pragma.fetchall()]
        return schema
