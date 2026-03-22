from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "sap-o2c-data"
SUPPORTED_SUFFIXES = {".csv", ".json", ".jsonl"}


class EntityModel(BaseModel):
    id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_datasets: list[str] = Field(default_factory=list)


class AddressRecord(EntityModel):
    business_partner_id: str | None = None
    city: str | None = None
    country: str | None = None
    postal_code: str | None = None
    region: str | None = None
    street: str | None = None
    timezone: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class CustomerRecord(EntityModel):
    business_partner_id: str | None = None
    name: str | None = None
    language: str | None = None
    is_blocked: bool | None = None
    is_archived: bool | None = None
    address_ids: list[str] = Field(default_factory=list)
    company_codes: list[str] = Field(default_factory=list)
    sales_areas: list[str] = Field(default_factory=list)


class ProductRecord(EntityModel):
    name: str | None = None
    base_unit: str | None = None
    product_type: str | None = None
    product_group: str | None = None
    division: str | None = None
    legacy_product_id: str | None = None
    is_deleted: bool | None = None


class OrderRecord(EntityModel):
    customer_id: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    order_type: str | None = None
    status: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    created_at: datetime | None = None
    requested_delivery_date: datetime | None = None


class DeliveryRecord(EntityModel):
    order_ids: list[str] = Field(default_factory=list)
    delivery_item_ids: list[str] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)
    shipping_point: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    goods_movement_at: datetime | None = None


class InvoiceRecord(EntityModel):
    customer_id: str | None = None
    delivery_ids: list[str] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)
    accounting_document_id: str | None = None
    company_code: str | None = None
    fiscal_year: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    invoice_date: datetime | None = None
    created_at: datetime | None = None
    is_cancelled: bool | None = None


class PaymentRecord(EntityModel):
    customer_id: str | None = None
    invoice_ids: list[str] = Field(default_factory=list)
    amount: Decimal | None = None
    currency: str | None = None
    company_code: str | None = None
    fiscal_year: str | None = None
    posting_date: datetime | None = None
    clearing_document_id: str | None = None


class NormalizedData(BaseModel):
    addresses: list[AddressRecord] = Field(default_factory=list)
    customers: list[CustomerRecord] = Field(default_factory=list)
    deliveries: list[DeliveryRecord] = Field(default_factory=list)
    invoices: list[InvoiceRecord] = Field(default_factory=list)
    orders: list[OrderRecord] = Field(default_factory=list)
    payments: list[PaymentRecord] = Field(default_factory=list)
    products: list[ProductRecord] = Field(default_factory=list)
    source_file_count: int = 0
    source_record_count: int = 0
    dataset_record_counts: dict[str, int] = Field(default_factory=dict)


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
    return value


def _clean_dict(record: dict[str, Any]) -> dict[str, Any]:
    return {key: _clean_value(value) for key, value in record.items()}


def _normalize_id(value: Any) -> str | None:
    value = _clean_value(value)
    if value is None:
        return None
    return str(value)


def _normalize_item_id(value: Any) -> str | None:
    value = _normalize_id(value)
    if value is None:
        return None
    stripped = value.lstrip("0")
    return stripped or "0"


def _to_decimal(value: Any) -> Decimal | None:
    value = _clean_value(value)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_datetime(value: Any) -> datetime | None:
    value = _clean_value(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _combine_date_time(date_value: Any, time_value: Any) -> datetime | None:
    parsed_date = _to_datetime(date_value)
    if parsed_date is None:
        return None
    if isinstance(time_value, dict):
        hours = int(time_value.get("hours", 0) or 0)
        minutes = int(time_value.get("minutes", 0) or 0)
        seconds = int(time_value.get("seconds", 0) or 0)
        return parsed_date.replace(hour=hours, minute=minutes, second=seconds)
    return parsed_date


def _merge_scalar(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    current = target.get(key)
    if current is None:
        target[key] = value


def _merge_collection(target: dict[str, Any], key: str, values: Iterable[str]) -> None:
    bucket = target.setdefault(key, set())
    for value in values:
        if value:
            bucket.add(value)


def _iter_records_from_file(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield _clean_dict(json.loads(line))
        return

    if suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, list):
            for record in payload:
                if isinstance(record, dict):
                    yield _clean_dict(record)
        elif isinstance(payload, dict):
            if "records" in payload and isinstance(payload["records"], list):
                for record in payload["records"]:
                    if isinstance(record, dict):
                        yield _clean_dict(record)
            else:
                yield _clean_dict(payload)
        return

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield _clean_dict(dict(row))
        return

    raise ValueError(f"Unsupported file type: {path}")


class DataLoader:
    def __init__(self, data_dir: Path | str = DEFAULT_DATA_DIR) -> None:
        self.data_dir = Path(data_dir)

    def load_all(self) -> NormalizedData:
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Dataset directory not found: {self.data_dir}")

        source_files = sorted(
            path
            for path in self.data_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )

        dataset_counts: defaultdict[str, int] = defaultdict(int)
        source_record_count = 0

        addresses: dict[str, dict[str, Any]] = {}
        customers: dict[str, dict[str, Any]] = {}
        products: dict[str, dict[str, Any]] = {}
        orders: dict[str, dict[str, Any]] = {}
        deliveries: dict[str, dict[str, Any]] = {}
        invoices: dict[str, dict[str, Any]] = {}
        payments: dict[str, dict[str, Any]] = {}

        ar_invoice_links: defaultdict[tuple[str | None, str | None, str | None], set[str]] = defaultdict(set)
        delivery_item_products: dict[tuple[str, str], str] = {}

        for path in source_files:
            dataset_name = path.parent.name if path.parent != self.data_dir else path.stem
            for record in _iter_records_from_file(path):
                dataset_counts[dataset_name] += 1
                source_record_count += 1
                self._normalize_record(
                    dataset_name=dataset_name,
                    record=record,
                    addresses=addresses,
                    customers=customers,
                    products=products,
                    orders=orders,
                    deliveries=deliveries,
                    invoices=invoices,
                    payments=payments,
                    ar_invoice_links=ar_invoice_links,
                    delivery_item_products=delivery_item_products,
                )

        for payment in payments.values():
            payment_key = (
                payment.get("customer_id"),
                payment.get("clearing_document_id"),
                payment.get("fiscal_year"),
            )
            payment["invoice_ids"] = sorted(ar_invoice_links.get(payment_key, set()))

        return NormalizedData(
            addresses=self._finalize_records(AddressRecord, addresses),
            customers=self._finalize_records(CustomerRecord, customers),
            deliveries=self._finalize_records(DeliveryRecord, deliveries),
            invoices=self._finalize_records(InvoiceRecord, invoices),
            orders=self._finalize_records(OrderRecord, orders),
            payments=self._finalize_records(PaymentRecord, payments),
            products=self._finalize_records(ProductRecord, products),
            source_file_count=len(source_files),
            source_record_count=source_record_count,
            dataset_record_counts=dict(sorted(dataset_counts.items())),
        )

    def _ensure_entity(
        self,
        bucket: dict[str, dict[str, Any]],
        entity_id: str | None,
        dataset_name: str,
    ) -> dict[str, Any] | None:
        if not entity_id:
            return None
        entity = bucket.setdefault(
            entity_id,
            {
                "id": entity_id,
                "metadata": {},
                "source_datasets": set(),
            },
        )
        entity["source_datasets"].add(dataset_name)
        return entity

    def _normalize_record(
        self,
        *,
        dataset_name: str,
        record: dict[str, Any],
        addresses: dict[str, dict[str, Any]],
        customers: dict[str, dict[str, Any]],
        products: dict[str, dict[str, Any]],
        orders: dict[str, dict[str, Any]],
        deliveries: dict[str, dict[str, Any]],
        invoices: dict[str, dict[str, Any]],
        payments: dict[str, dict[str, Any]],
        ar_invoice_links: defaultdict[tuple[str | None, str | None, str | None], set[str]],
        delivery_item_products: dict[tuple[str, str], str],
    ) -> None:
        if dataset_name == "business_partners":
            customer_id = _normalize_id(record.get("customer") or record.get("businessPartner"))
            customer = self._ensure_entity(customers, customer_id, dataset_name)
            if not customer:
                return
            _merge_scalar(customer, "business_partner_id", _normalize_id(record.get("businessPartner")))
            _merge_scalar(
                customer,
                "name",
                record.get("businessPartnerName")
                or record.get("businessPartnerFullName")
                or record.get("organizationBpName1"),
            )
            _merge_scalar(customer, "language", _normalize_id(record.get("correspondenceLanguage")))
            _merge_scalar(customer, "is_blocked", record.get("businessPartnerIsBlocked"))
            _merge_scalar(customer, "is_archived", record.get("isMarkedForArchiving"))
            customer["metadata"].update(record)
            return

        if dataset_name == "business_partner_addresses":
            address_id = _normalize_id(record.get("addressId"))
            address = self._ensure_entity(addresses, address_id, dataset_name)
            if not address:
                return
            business_partner_id = _normalize_id(record.get("businessPartner"))
            _merge_scalar(address, "business_partner_id", business_partner_id)
            _merge_scalar(address, "city", _normalize_id(record.get("cityName")))
            _merge_scalar(address, "country", _normalize_id(record.get("country")))
            _merge_scalar(address, "postal_code", _normalize_id(record.get("postalCode")))
            _merge_scalar(address, "region", _normalize_id(record.get("region")))
            _merge_scalar(address, "street", _normalize_id(record.get("streetName")))
            _merge_scalar(address, "timezone", _normalize_id(record.get("addressTimeZone")))
            _merge_scalar(address, "valid_from", _to_datetime(record.get("validityStartDate")))
            _merge_scalar(address, "valid_to", _to_datetime(record.get("validityEndDate")))
            address["metadata"].update(record)

            customer = self._ensure_entity(customers, business_partner_id, dataset_name)
            if customer:
                _merge_scalar(customer, "business_partner_id", business_partner_id)
                _merge_collection(customer, "address_ids", [address_id])
            return

        if dataset_name == "customer_company_assignments":
            customer = self._ensure_entity(customers, _normalize_id(record.get("customer")), dataset_name)
            if not customer:
                return
            company_code = _normalize_id(record.get("companyCode"))
            _merge_collection(customer, "company_codes", [company_code])
            customer["metadata"].setdefault("company_assignments", []).append(record)
            return

        if dataset_name == "customer_sales_area_assignments":
            customer = self._ensure_entity(customers, _normalize_id(record.get("customer")), dataset_name)
            if not customer:
                return
            sales_area = ":".join(
                filter(
                    None,
                    [
                        _normalize_id(record.get("salesOrganization")),
                        _normalize_id(record.get("distributionChannel")),
                        _normalize_id(record.get("division")),
                    ],
                )
            )
            _merge_collection(customer, "sales_areas", [sales_area])
            customer["metadata"].setdefault("sales_area_assignments", []).append(record)
            return

        if dataset_name == "products":
            product = self._ensure_entity(products, _normalize_id(record.get("product")), dataset_name)
            if not product:
                return
            _merge_scalar(product, "base_unit", _normalize_id(record.get("baseUnit")))
            _merge_scalar(product, "product_type", _normalize_id(record.get("productType")))
            _merge_scalar(product, "product_group", _normalize_id(record.get("productGroup")))
            _merge_scalar(product, "division", _normalize_id(record.get("division")))
            _merge_scalar(product, "legacy_product_id", _normalize_id(record.get("productOldId")))
            _merge_scalar(product, "is_deleted", record.get("isMarkedForDeletion"))
            product["metadata"].update(record)
            return

        if dataset_name == "product_descriptions":
            product = self._ensure_entity(products, _normalize_id(record.get("product")), dataset_name)
            if not product:
                return
            _merge_scalar(product, "name", _normalize_id(record.get("productDescription")))
            product["metadata"].setdefault("descriptions", []).append(record)
            return

        if dataset_name in {"sales_order_headers", "sales_order_items", "sales_order_schedule_lines"}:
            order_id = _normalize_id(record.get("salesOrder"))
            order = self._ensure_entity(orders, order_id, dataset_name)
            if not order:
                return
            if dataset_name == "sales_order_headers":
                customer_id = _normalize_id(record.get("soldToParty"))
                _merge_scalar(order, "customer_id", customer_id)
                _merge_scalar(order, "order_type", _normalize_id(record.get("salesOrderType")))
                _merge_scalar(order, "status", _normalize_id(record.get("overallDeliveryStatus")))
                _merge_scalar(order, "amount", _to_decimal(record.get("totalNetAmount")))
                _merge_scalar(order, "currency", _normalize_id(record.get("transactionCurrency")))
                _merge_scalar(order, "created_at", _to_datetime(record.get("creationDate")))
                _merge_scalar(order, "requested_delivery_date", _to_datetime(record.get("requestedDeliveryDate")))
                order["metadata"].update(record)
                customer = self._ensure_entity(customers, customer_id, dataset_name)
                if customer:
                    customer["metadata"].setdefault("orders", []).append(order_id)
            elif dataset_name == "sales_order_items":
                product_id = _normalize_id(record.get("material"))
                item_id = _normalize_item_id(record.get("salesOrderItem"))
                _merge_collection(order, "product_ids", [product_id])
                order["metadata"].setdefault("items", []).append(record)
                if item_id and product_id:
                    order["metadata"].setdefault("item_to_product", {})[item_id] = product_id
                product = self._ensure_entity(products, product_id, dataset_name)
                if product:
                    product["metadata"].setdefault("orders", []).append(order_id)
            else:
                order["metadata"].setdefault("schedule_lines", []).append(record)
            return

        if dataset_name in {"outbound_delivery_headers", "outbound_delivery_items"}:
            delivery_id = _normalize_id(record.get("deliveryDocument"))
            delivery = self._ensure_entity(deliveries, delivery_id, dataset_name)
            if not delivery:
                return
            if dataset_name == "outbound_delivery_headers":
                _merge_scalar(delivery, "shipping_point", _normalize_id(record.get("shippingPoint")))
                _merge_scalar(delivery, "status", _normalize_id(record.get("overallGoodsMovementStatus")))
                _merge_scalar(
                    delivery,
                    "created_at",
                    _combine_date_time(record.get("creationDate"), record.get("creationTime")),
                )
                _merge_scalar(
                    delivery,
                    "goods_movement_at",
                    _combine_date_time(
                        record.get("actualGoodsMovementDate"),
                        record.get("actualGoodsMovementTime"),
                    ),
                )
                delivery["metadata"].update(record)
            else:
                order_id = _normalize_id(record.get("referenceSdDocument"))
                item_id = _normalize_item_id(record.get("referenceSdDocumentItem"))
                delivery_item_id = _normalize_item_id(record.get("deliveryDocumentItem"))
                _merge_collection(delivery, "order_ids", [order_id])
                _merge_collection(delivery, "delivery_item_ids", [delivery_item_id])
                delivery["metadata"].setdefault("items", []).append(record)
                product_id = None
                if order_id and item_id:
                    product_id = orders.get(order_id, {}).get("metadata", {}).get("item_to_product", {}).get(item_id)
                if product_id:
                    _merge_collection(delivery, "product_ids", [product_id])
                    delivery_item_products[(delivery_id, delivery_item_id)] = product_id
            return

        if dataset_name in {
            "billing_document_headers",
            "billing_document_items",
            "billing_document_cancellations",
        }:
            invoice_id = _normalize_id(record.get("billingDocument"))
            invoice = self._ensure_entity(invoices, invoice_id, dataset_name)
            if not invoice:
                return
            if dataset_name in {"billing_document_headers", "billing_document_cancellations"}:
                customer_id = _normalize_id(record.get("soldToParty"))
                _merge_scalar(invoice, "customer_id", customer_id)
                _merge_scalar(invoice, "accounting_document_id", _normalize_id(record.get("accountingDocument")))
                _merge_scalar(invoice, "company_code", _normalize_id(record.get("companyCode")))
                _merge_scalar(invoice, "fiscal_year", _normalize_id(record.get("fiscalYear")))
                _merge_scalar(invoice, "amount", _to_decimal(record.get("totalNetAmount")))
                _merge_scalar(invoice, "currency", _normalize_id(record.get("transactionCurrency")))
                _merge_scalar(invoice, "invoice_date", _to_datetime(record.get("billingDocumentDate")))
                _merge_scalar(
                    invoice,
                    "created_at",
                    _combine_date_time(record.get("creationDate"), record.get("creationTime")),
                )
                _merge_scalar(invoice, "is_cancelled", record.get("billingDocumentIsCancelled"))
                invoice["metadata"].update(record)
                customer = self._ensure_entity(customers, customer_id, dataset_name)
                if customer:
                    customer["metadata"].setdefault("invoices", []).append(invoice_id)
            else:
                delivery_id = _normalize_id(record.get("referenceSdDocument"))
                delivery_item_id = _normalize_item_id(record.get("referenceSdDocumentItem"))
                product_id = _normalize_id(record.get("material"))
                _merge_collection(invoice, "delivery_ids", [delivery_id])
                _merge_collection(invoice, "product_ids", [product_id])
                invoice["metadata"].setdefault("items", []).append(record)
                if not product_id and delivery_id and delivery_item_id:
                    product_id = delivery_item_products.get((delivery_id, delivery_item_id))
                    _merge_collection(invoice, "product_ids", [product_id] if product_id else [])
                product = self._ensure_entity(products, product_id, dataset_name)
                if product:
                    product["metadata"].setdefault("invoices", []).append(invoice_id)
            return

        if dataset_name == "journal_entry_items_accounts_receivable":
            invoice_id = _normalize_id(record.get("referenceDocument"))
            customer_id = _normalize_id(record.get("customer"))
            clearing_document_id = _normalize_id(record.get("clearingAccountingDocument"))
            fiscal_year = _normalize_id(record.get("clearingDocFiscalYear"))
            if clearing_document_id:
                ar_invoice_links[(customer_id, clearing_document_id, fiscal_year)].add(invoice_id)

            invoice = self._ensure_entity(invoices, invoice_id, dataset_name)
            if invoice:
                invoice["metadata"].setdefault("journal_entries", []).append(record)
            return

        if dataset_name == "payments_accounts_receivable":
            payment_id = _normalize_id(record.get("accountingDocument"))
            payment = self._ensure_entity(payments, payment_id, dataset_name)
            if not payment:
                return
            customer_id = _normalize_id(record.get("customer"))
            _merge_scalar(payment, "customer_id", customer_id)
            _merge_scalar(payment, "amount", _to_decimal(record.get("amountInTransactionCurrency")))
            _merge_scalar(payment, "currency", _normalize_id(record.get("transactionCurrency")))
            _merge_scalar(payment, "company_code", _normalize_id(record.get("companyCode")))
            _merge_scalar(payment, "fiscal_year", _normalize_id(record.get("clearingDocFiscalYear") or record.get("fiscalYear")))
            _merge_scalar(payment, "posting_date", _to_datetime(record.get("postingDate")))
            _merge_scalar(payment, "clearing_document_id", _normalize_id(record.get("clearingAccountingDocument")))
            payment["metadata"].update(record)
            customer = self._ensure_entity(customers, customer_id, dataset_name)
            if customer:
                customer["metadata"].setdefault("payments", []).append(payment_id)
            return

    def _finalize_records(
        self,
        model: type[BaseModel],
        bucket: dict[str, dict[str, Any]],
    ) -> list[Any]:
        records = []
        for entity_id in sorted(bucket):
            payload = dict(bucket[entity_id])
            payload["source_datasets"] = sorted(payload.get("source_datasets", set()))
            for key, value in list(payload.items()):
                if isinstance(value, set):
                    payload[key] = sorted(value)
            records.append(model.model_validate(payload))
        return records
