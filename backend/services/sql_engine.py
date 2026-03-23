from __future__ import annotations

import json
import re
import sqlite3
import time
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
    note: str | None = None
    total_rows: int = 0


class SqlEngine:
    def __init__(self, data: NormalizedData) -> None:
        self.data = data
        self.connection = sqlite3.connect(":memory:", check_same_thread=False, timeout=5.0)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._create_tables()
        self._load_data()

    def _create_tables(self) -> None:
        cursor = self.connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE customers (id TEXT PRIMARY KEY, business_partner_id TEXT, name TEXT, language TEXT, is_blocked INTEGER, is_archived INTEGER, address_ids_json TEXT, company_codes_json TEXT, sales_areas_json TEXT, delivery_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE addresses (id TEXT PRIMARY KEY, business_partner_id TEXT, city TEXT, country TEXT, postal_code TEXT, region TEXT, street TEXT, timezone TEXT, valid_from TEXT, valid_to TEXT, metadata_json TEXT);
            CREATE TABLE plants (id TEXT PRIMARY KEY, name TEXT, valuation_area TEXT, plant_customer TEXT, plant_supplier TEXT, factory_calendar TEXT, default_purchasing_organization TEXT, sales_organization TEXT, address_id TEXT, plant_category TEXT, distribution_channel TEXT, division TEXT, language TEXT, is_archived INTEGER, product_ids_json TEXT, delivery_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE products (id TEXT PRIMARY KEY, name TEXT, base_unit TEXT, product_type TEXT, product_group TEXT, division TEXT, legacy_product_id TEXT, is_deleted INTEGER, plant_ids_json TEXT, invoice_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE orders (id TEXT PRIMARY KEY, customer_id TEXT, order_type TEXT, status TEXT, amount TEXT, currency TEXT, created_at TEXT, requested_delivery_date TEXT, product_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE deliveries (id TEXT PRIMARY KEY, customer_id TEXT, shipping_point TEXT, status TEXT, created_at TEXT, goods_movement_at TEXT, order_ids_json TEXT, delivery_item_ids_json TEXT, product_ids_json TEXT, plant_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE invoices (id TEXT PRIMARY KEY, customer_id TEXT, accounting_document_id TEXT, company_code TEXT, fiscal_year TEXT, amount TEXT, currency TEXT, invoice_date TEXT, created_at TEXT, is_cancelled INTEGER, delivery_ids_json TEXT, product_ids_json TEXT, journal_entry_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE journal_entries (id TEXT PRIMARY KEY, invoice_id TEXT, customer_id TEXT, company_code TEXT, fiscal_year TEXT, accounting_document_item TEXT, gl_account TEXT, cost_center TEXT, profit_center TEXT, transaction_currency TEXT, amount_in_transaction_currency TEXT, company_code_currency TEXT, amount_in_company_code_currency TEXT, posting_date TEXT, document_date TEXT, accounting_document_type TEXT, assignment_reference TEXT, last_change_at TEXT, financial_account_type TEXT, clearing_date TEXT, clearing_accounting_document TEXT, clearing_doc_fiscal_year TEXT, metadata_json TEXT);
            CREATE TABLE payments (id TEXT PRIMARY KEY, customer_id TEXT, amount TEXT, currency TEXT, company_code TEXT, fiscal_year TEXT, posting_date TEXT, clearing_document_id TEXT, invoice_ids_json TEXT, metadata_json TEXT);
            CREATE TABLE customer_addresses (customer_id TEXT, address_id TEXT);
            CREATE TABLE customer_deliveries (customer_id TEXT, delivery_id TEXT);
            CREATE TABLE order_products (order_id TEXT, product_id TEXT);
            CREATE TABLE order_deliveries (order_id TEXT, delivery_id TEXT);
            CREATE TABLE delivery_products (delivery_id TEXT, product_id TEXT);
            CREATE TABLE delivery_plants (delivery_id TEXT, plant_id TEXT);
            CREATE TABLE delivery_invoices (delivery_id TEXT, invoice_id TEXT);
            CREATE TABLE invoice_products (invoice_id TEXT, product_id TEXT);
            CREATE TABLE invoice_journal_entries (invoice_id TEXT, journal_entry_id TEXT);
            CREATE TABLE invoice_payments (invoice_id TEXT, payment_id TEXT);
            CREATE TABLE product_plants (product_id TEXT, plant_id TEXT);
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
        if isinstance(value, (list, dict)):
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
        self._insert_many("customers", [{"id": r.id, "business_partner_id": r.business_partner_id, "name": r.name, "language": r.language, "is_blocked": r.is_blocked, "is_archived": r.is_archived, "address_ids_json": r.address_ids, "company_codes_json": r.company_codes, "sales_areas_json": r.sales_areas, "delivery_ids_json": r.delivery_ids, "metadata_json": r.metadata} for r in self.data.customers])
        self._insert_many("addresses", [{"id": r.id, "business_partner_id": r.business_partner_id, "city": r.city, "country": r.country, "postal_code": r.postal_code, "region": r.region, "street": r.street, "timezone": r.timezone, "valid_from": r.valid_from, "valid_to": r.valid_to, "metadata_json": r.metadata} for r in self.data.addresses])
        self._insert_many("plants", [{"id": r.id, "name": r.name, "valuation_area": r.valuation_area, "plant_customer": r.plant_customer, "plant_supplier": r.plant_supplier, "factory_calendar": r.factory_calendar, "default_purchasing_organization": r.default_purchasing_organization, "sales_organization": r.sales_organization, "address_id": r.address_id, "plant_category": r.plant_category, "distribution_channel": r.distribution_channel, "division": r.division, "language": r.language, "is_archived": r.is_archived, "product_ids_json": r.product_ids, "delivery_ids_json": r.delivery_ids, "metadata_json": r.metadata} for r in self.data.plants])
        self._insert_many("products", [{"id": r.id, "name": r.name, "base_unit": r.base_unit, "product_type": r.product_type, "product_group": r.product_group, "division": r.division, "legacy_product_id": r.legacy_product_id, "is_deleted": r.is_deleted, "plant_ids_json": r.plant_ids, "invoice_ids_json": r.invoice_ids, "metadata_json": r.metadata} for r in self.data.products])
        self._insert_many("orders", [{"id": r.id, "customer_id": r.customer_id, "order_type": r.order_type, "status": r.status, "amount": r.amount, "currency": r.currency, "created_at": r.created_at, "requested_delivery_date": r.requested_delivery_date, "product_ids_json": r.product_ids, "metadata_json": r.metadata} for r in self.data.orders])
        self._insert_many("deliveries", [{"id": r.id, "customer_id": r.customer_id, "shipping_point": r.shipping_point, "status": r.status, "created_at": r.created_at, "goods_movement_at": r.goods_movement_at, "order_ids_json": r.order_ids, "delivery_item_ids_json": r.delivery_item_ids, "product_ids_json": r.product_ids, "plant_ids_json": r.plant_ids, "metadata_json": r.metadata} for r in self.data.deliveries])
        self._insert_many("invoices", [{"id": r.id, "customer_id": r.customer_id, "accounting_document_id": r.accounting_document_id, "company_code": r.company_code, "fiscal_year": r.fiscal_year, "amount": r.amount, "currency": r.currency, "invoice_date": r.invoice_date, "created_at": r.created_at, "is_cancelled": r.is_cancelled, "delivery_ids_json": r.delivery_ids, "product_ids_json": r.product_ids, "journal_entry_ids_json": r.journal_entry_ids, "metadata_json": r.metadata} for r in self.data.invoices])
        self._insert_many("journal_entries", [{"id": r.id, "invoice_id": r.invoice_id, "customer_id": r.customer_id, "company_code": r.company_code, "fiscal_year": r.fiscal_year, "accounting_document_item": r.accounting_document_item, "gl_account": r.gl_account, "cost_center": r.cost_center, "profit_center": r.profit_center, "transaction_currency": r.transaction_currency, "amount_in_transaction_currency": r.amount_in_transaction_currency, "company_code_currency": r.company_code_currency, "amount_in_company_code_currency": r.amount_in_company_code_currency, "posting_date": r.posting_date, "document_date": r.document_date, "accounting_document_type": r.accounting_document_type, "assignment_reference": r.assignment_reference, "last_change_at": r.last_change_at, "financial_account_type": r.financial_account_type, "clearing_date": r.clearing_date, "clearing_accounting_document": r.clearing_accounting_document, "clearing_doc_fiscal_year": r.clearing_doc_fiscal_year, "metadata_json": r.metadata} for r in self.data.journal_entries])
        self._insert_many("payments", [{"id": r.id, "customer_id": r.customer_id, "amount": r.amount, "currency": r.currency, "company_code": r.company_code, "fiscal_year": r.fiscal_year, "posting_date": r.posting_date, "clearing_document_id": r.clearing_document_id, "invoice_ids_json": r.invoice_ids, "metadata_json": r.metadata} for r in self.data.payments])
        self._insert_many("customer_addresses", [{"customer_id": c.id, "address_id": a} for c in self.data.customers for a in c.address_ids])
        self._insert_many("customer_deliveries", [{"customer_id": c.id, "delivery_id": d} for c in self.data.customers for d in c.delivery_ids])
        self._insert_many("order_products", [{"order_id": o.id, "product_id": p} for o in self.data.orders for p in o.product_ids])
        self._insert_many("order_deliveries", [{"order_id": o, "delivery_id": d.id} for d in self.data.deliveries for o in d.order_ids])
        self._insert_many("delivery_products", [{"delivery_id": d.id, "product_id": p} for d in self.data.deliveries for p in d.product_ids])
        self._insert_many("delivery_plants", [{"delivery_id": d.id, "plant_id": p} for d in self.data.deliveries for p in d.plant_ids])
        self._insert_many("delivery_invoices", [{"delivery_id": d, "invoice_id": i.id} for i in self.data.invoices for d in i.delivery_ids])
        self._insert_many("invoice_products", [{"invoice_id": i.id, "product_id": p} for i in self.data.invoices for p in i.product_ids])
        self._insert_many("invoice_journal_entries", [{"invoice_id": i.id, "journal_entry_id": j} for i in self.data.invoices for j in i.journal_entry_ids])
        self._insert_many("invoice_payments", [{"invoice_id": i, "payment_id": p.id} for p in self.data.payments for i in p.invoice_ids])
        self._insert_many("product_plants", [{"product_id": p.id, "plant_id": plant_id} for p in self.data.products for plant_id in p.plant_ids])
        self.connection.commit()

    def validate_sql(self, query_string: str) -> str:
        query = query_string.strip().rstrip(";")
        if not query:
            raise ValueError("Generated SQL is empty.")
        lowered = query.lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise ValueError("Only SELECT statements are allowed.")
        for pattern in BANNED_SQL_PATTERNS:
            if pattern.search(query):
                raise ValueError("Unsafe SQL detected.")
        if " limit " not in f" {lowered} ":
            query = f"{query} LIMIT 1000"
        return query

    def execute_sql(self, query_string: str) -> SqlExecutionResult:
        try:
            query = self.validate_sql(query_string)
            started = time.perf_counter()

            def progress_handler() -> int:
                if time.perf_counter() - started > 5:
                    raise TimeoutError("Query timed out. Try a more specific query.")
                return 0

            self.connection.set_progress_handler(progress_handler, 1000)
            cursor = self.connection.execute(query)
            rows = [dict(row) for row in cursor.fetchall()]
            self.connection.set_progress_handler(None, 0)
            total_rows = len(rows)
            note = None
            if total_rows > 500:
                rows = rows[:500]
                note = f"Showing first 500 of {total_rows} results."
            return SqlExecutionResult(query=query, rows=rows, note=note, total_rows=total_rows)
        except TimeoutError as exc:
            self.connection.set_progress_handler(None, 0)
            return SqlExecutionResult(query=query_string, rows=[], error=str(exc))
        except Exception as exc:
            self.connection.set_progress_handler(None, 0)
            return SqlExecutionResult(query=query_string, rows=[], error=str(exc))

    def get_schema_overview(self) -> dict[str, list[str]]:
        schema: dict[str, list[str]] = {}
        cursor = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for (table,) in cursor.fetchall():
            pragma = self.connection.execute(f"PRAGMA table_info({table})")
            schema[table] = [row[1] for row in pragma.fetchall()]
        return schema
