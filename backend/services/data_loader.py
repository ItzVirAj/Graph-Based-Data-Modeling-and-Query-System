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
    delivery_ids: list[str] = Field(default_factory=list)


class PlantRecord(EntityModel):
    name: str | None = None
    valuation_area: str | None = None
    plant_customer: str | None = None
    plant_supplier: str | None = None
    factory_calendar: str | None = None
    default_purchasing_organization: str | None = None
    sales_organization: str | None = None
    address_id: str | None = None
    plant_category: str | None = None
    distribution_channel: str | None = None
    division: str | None = None
    language: str | None = None
    is_archived: bool | None = None
    product_ids: list[str] = Field(default_factory=list)
    delivery_ids: list[str] = Field(default_factory=list)


class ProductRecord(EntityModel):
    name: str | None = None
    base_unit: str | None = None
    product_type: str | None = None
    product_group: str | None = None
    division: str | None = None
    legacy_product_id: str | None = None
    is_deleted: bool | None = None
    plant_ids: list[str] = Field(default_factory=list)
    invoice_ids: list[str] = Field(default_factory=list)


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
    customer_id: str | None = None
    order_ids: list[str] = Field(default_factory=list)
    delivery_item_ids: list[str] = Field(default_factory=list)
    product_ids: list[str] = Field(default_factory=list)
    plant_ids: list[str] = Field(default_factory=list)
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
    journal_entry_ids: list[str] = Field(default_factory=list)


class JournalEntryRecord(EntityModel):
    invoice_id: str | None = None
    customer_id: str | None = None
    company_code: str | None = None
    fiscal_year: str | None = None
    accounting_document_item: str | None = None
    gl_account: str | None = None
    cost_center: str | None = None
    profit_center: str | None = None
    transaction_currency: str | None = None
    amount_in_transaction_currency: Decimal | None = None
    company_code_currency: str | None = None
    amount_in_company_code_currency: Decimal | None = None
    posting_date: datetime | None = None
    document_date: datetime | None = None
    accounting_document_type: str | None = None
    assignment_reference: str | None = None
    last_change_at: datetime | None = None
    financial_account_type: str | None = None
    clearing_date: datetime | None = None
    clearing_accounting_document: str | None = None
    clearing_doc_fiscal_year: str | None = None


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
    journal_entries: list[JournalEntryRecord] = Field(default_factory=list)
    orders: list[OrderRecord] = Field(default_factory=list)
    payments: list[PaymentRecord] = Field(default_factory=list)
    plants: list[PlantRecord] = Field(default_factory=list)
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
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
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
    if value is not None and target.get(key) is None:
        target[key] = value


def _merge_collection(target: dict[str, Any], key: str, values: Iterable[str | None]) -> None:
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
            records = payload.get("records") if isinstance(payload.get("records"), list) else [payload]
            for record in records:
                if isinstance(record, dict):
                    yield _clean_dict(record)
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

        source_files = sorted(path for path in self.data_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES)
        dataset_counts: defaultdict[str, int] = defaultdict(int)
        source_record_count = 0

        addresses: dict[str, dict[str, Any]] = {}
        customers: dict[str, dict[str, Any]] = {}
        deliveries: dict[str, dict[str, Any]] = {}
        invoices: dict[str, dict[str, Any]] = {}
        journal_entries: dict[str, dict[str, Any]] = {}
        orders: dict[str, dict[str, Any]] = {}
        payments: dict[str, dict[str, Any]] = {}
        plants: dict[str, dict[str, Any]] = {}
        products: dict[str, dict[str, Any]] = {}

        ar_invoice_links: defaultdict[tuple[str | None, str | None, str | None], set[str]] = defaultdict(set)
        delivery_item_products: dict[tuple[str, str], str] = {}
        order_item_products: dict[tuple[str, str], str] = {}
        pending_delivery_refs: list[tuple[str, str | None, str | None, str | None, str | None]] = []

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
                    deliveries=deliveries,
                    invoices=invoices,
                    journal_entries=journal_entries,
                    orders=orders,
                    payments=payments,
                    plants=plants,
                    products=products,
                    ar_invoice_links=ar_invoice_links,
                    delivery_item_products=delivery_item_products,
                    order_item_products=order_item_products,
                    pending_delivery_refs=pending_delivery_refs,
                )

        for delivery_id, order_id, order_item_id, delivery_item_id, plant_id in pending_delivery_refs:
            product_id = order_item_products.get((order_id, order_item_id)) if order_id and order_item_id else None
            delivery = deliveries.get(delivery_id)
            if not delivery:
                continue
            if product_id:
                _merge_collection(delivery, "product_ids", [product_id])
                if delivery_item_id:
                    delivery_item_products[(delivery_id, delivery_item_id)] = product_id
                product = self._ensure_entity(products, product_id, "outbound_delivery_items")
                if product:
                    product["metadata"].setdefault("deliveries", []).append(delivery_id)
            if plant_id:
                _merge_collection(delivery, "plant_ids", [plant_id])
                plant = self._ensure_entity(plants, plant_id, "outbound_delivery_items")
                if plant:
                    _merge_collection(plant, "delivery_ids", [delivery_id])
                    if product_id:
                        _merge_collection(plant, "product_ids", [product_id])

        for delivery in deliveries.values():
            customer_ids = {
                orders.get(order_id, {}).get("customer_id")
                for order_id in delivery.get("order_ids", set())
                if orders.get(order_id, {}).get("customer_id")
            }
            if customer_ids:
                customer_id = sorted(customer_ids)[0]
                delivery["customer_id"] = customer_id
                customer = self._ensure_entity(customers, customer_id, "delivery_customer_derivation")
                if customer:
                    _merge_collection(customer, "delivery_ids", [delivery["id"]])

        for payment in payments.values():
            payment_key = (payment.get("customer_id"), payment.get("clearing_document_id"), payment.get("fiscal_year"))
            payment["invoice_ids"] = sorted(ar_invoice_links.get(payment_key, set()))

        return NormalizedData(
            addresses=self._finalize_records(AddressRecord, addresses),
            customers=self._finalize_records(CustomerRecord, customers),
            deliveries=self._finalize_records(DeliveryRecord, deliveries),
            invoices=self._finalize_records(InvoiceRecord, invoices),
            journal_entries=self._finalize_records(JournalEntryRecord, journal_entries),
            orders=self._finalize_records(OrderRecord, orders),
            payments=self._finalize_records(PaymentRecord, payments),
            plants=self._finalize_records(PlantRecord, plants),
            products=self._finalize_records(ProductRecord, products),
            source_file_count=len(source_files),
            source_record_count=source_record_count,
            dataset_record_counts=dict(sorted(dataset_counts.items())),
        )

    def _ensure_entity(self, bucket: dict[str, dict[str, Any]], entity_id: str | None, dataset_name: str) -> dict[str, Any] | None:
        if not entity_id:
            return None
        entity = bucket.setdefault(entity_id, {"id": entity_id, "metadata": {}, "source_datasets": set()})
        entity["source_datasets"].add(dataset_name)
        return entity

    def _normalize_record(
        self,
        *,
        dataset_name: str,
        record: dict[str, Any],
        addresses: dict[str, dict[str, Any]],
        customers: dict[str, dict[str, Any]],
        deliveries: dict[str, dict[str, Any]],
        invoices: dict[str, dict[str, Any]],
        journal_entries: dict[str, dict[str, Any]],
        orders: dict[str, dict[str, Any]],
        payments: dict[str, dict[str, Any]],
        plants: dict[str, dict[str, Any]],
        products: dict[str, dict[str, Any]],
        ar_invoice_links: defaultdict[tuple[str | None, str | None, str | None], set[str]],
        delivery_item_products: dict[tuple[str, str], str],
        order_item_products: dict[tuple[str, str], str],
        pending_delivery_refs: list[tuple[str, str | None, str | None, str | None, str | None]],
    ) -> None:
        if dataset_name == "business_partners":
            customer_id = _normalize_id(record.get("customer") or record.get("businessPartner"))
            customer = self._ensure_entity(customers, customer_id, dataset_name)
            if not customer:
                return
            _merge_scalar(customer, "business_partner_id", _normalize_id(record.get("businessPartner")))
            _merge_scalar(customer, "name", record.get("businessPartnerName") or record.get("businessPartnerFullName") or record.get("organizationBpName1"))
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
            if customer:
                _merge_collection(customer, "company_codes", [_normalize_id(record.get("companyCode"))])
                customer["metadata"].setdefault("company_assignments", []).append(record)
            return

        if dataset_name == "customer_sales_area_assignments":
            customer = self._ensure_entity(customers, _normalize_id(record.get("customer")), dataset_name)
            if customer:
                sales_area = ":".join(filter(None, [_normalize_id(record.get("salesOrganization")), _normalize_id(record.get("distributionChannel")), _normalize_id(record.get("division"))]))
                _merge_collection(customer, "sales_areas", [sales_area])
                customer["metadata"].setdefault("sales_area_assignments", []).append(record)
            return

        if dataset_name == "plants":
            plant_id = _normalize_id(record.get("plant"))
            plant = self._ensure_entity(plants, plant_id, dataset_name)
            if not plant:
                return
            _merge_scalar(plant, "name", _normalize_id(record.get("plantName")))
            _merge_scalar(plant, "valuation_area", _normalize_id(record.get("valuationArea")))
            _merge_scalar(plant, "plant_customer", _normalize_id(record.get("plantCustomer")))
            _merge_scalar(plant, "plant_supplier", _normalize_id(record.get("plantSupplier")))
            _merge_scalar(plant, "factory_calendar", _normalize_id(record.get("factoryCalendar")))
            _merge_scalar(plant, "default_purchasing_organization", _normalize_id(record.get("defaultPurchasingOrganization")))
            _merge_scalar(plant, "sales_organization", _normalize_id(record.get("salesOrganization")))
            _merge_scalar(plant, "address_id", _normalize_id(record.get("addressId")))
            _merge_scalar(plant, "plant_category", _normalize_id(record.get("plantCategory")))
            _merge_scalar(plant, "distribution_channel", _normalize_id(record.get("distributionChannel")))
            _merge_scalar(plant, "division", _normalize_id(record.get("division")))
            _merge_scalar(plant, "language", _normalize_id(record.get("language")))
            _merge_scalar(plant, "is_archived", record.get("isMarkedForArchiving"))
            plant["metadata"].update(record)
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
            if product:
                _merge_scalar(product, "name", _normalize_id(record.get("productDescription")))
                product["metadata"].setdefault("descriptions", []).append(record)
            return

        if dataset_name == "product_plants":
            product_id = _normalize_id(record.get("product"))
            plant_id = _normalize_id(record.get("plant"))
            product = self._ensure_entity(products, product_id, dataset_name)
            plant = self._ensure_entity(plants, plant_id, dataset_name)
            if product:
                _merge_collection(product, "plant_ids", [plant_id])
                product["metadata"].setdefault("product_plants", []).append(record)
            if plant:
                _merge_collection(plant, "product_ids", [product_id])
                plant["metadata"].setdefault("product_plants", []).append(record)
            return

        if dataset_name == "product_storage_locations":
            product_id = _normalize_id(record.get("product"))
            plant_id = _normalize_id(record.get("plant"))
            product = self._ensure_entity(products, product_id, dataset_name)
            plant = self._ensure_entity(plants, plant_id, dataset_name)
            if product:
                _merge_collection(product, "plant_ids", [plant_id])
                product["metadata"].setdefault("storage_locations", []).append(record)
            if plant:
                plant["metadata"].setdefault("storage_locations", []).append(record)
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
                    order_item_products[(order_id, item_id)] = product_id
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
                _merge_scalar(delivery, "created_at", _combine_date_time(record.get("creationDate"), record.get("creationTime")))
                _merge_scalar(delivery, "goods_movement_at", _combine_date_time(record.get("actualGoodsMovementDate"), record.get("actualGoodsMovementTime")))
                delivery["metadata"].update(record)
            else:
                order_id = _normalize_id(record.get("referenceSdDocument"))
                order_item_id = _normalize_item_id(record.get("referenceSdDocumentItem"))
                delivery_item_id = _normalize_item_id(record.get("deliveryDocumentItem"))
                plant_id = _normalize_id(record.get("plant"))
                _merge_collection(delivery, "order_ids", [order_id])
                _merge_collection(delivery, "delivery_item_ids", [delivery_item_id])
                _merge_collection(delivery, "plant_ids", [plant_id])
                delivery["metadata"].setdefault("items", []).append(record)
                pending_delivery_refs.append((delivery_id, order_id, order_item_id, delivery_item_id, plant_id))
            return

        if dataset_name in {"billing_document_headers", "billing_document_items", "billing_document_cancellations"}:
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
                _merge_scalar(invoice, "created_at", _combine_date_time(record.get("creationDate"), record.get("creationTime")))
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
                if not product_id and delivery_id and delivery_item_id:
                    product_id = delivery_item_products.get((delivery_id, delivery_item_id))
                _merge_collection(invoice, "product_ids", [product_id])
                invoice["metadata"].setdefault("items", []).append(record)
                product = self._ensure_entity(products, product_id, dataset_name)
                if product:
                    _merge_collection(product, "invoice_ids", [invoice_id])
                    product["metadata"].setdefault("invoices", []).append(invoice_id)
            return

        if dataset_name == "journal_entry_items_accounts_receivable":
            journal_entry_id = _normalize_id(record.get("accountingDocument"))
            journal_entry = self._ensure_entity(journal_entries, journal_entry_id, dataset_name)
            if not journal_entry:
                return
            invoice_id = _normalize_id(record.get("referenceDocument"))
            customer_id = _normalize_id(record.get("customer"))
            clearing_document_id = _normalize_id(record.get("clearingAccountingDocument"))
            fiscal_year = _normalize_id(record.get("clearingDocFiscalYear"))
            _merge_scalar(journal_entry, "invoice_id", invoice_id)
            _merge_scalar(journal_entry, "customer_id", customer_id)
            _merge_scalar(journal_entry, "company_code", _normalize_id(record.get("companyCode")))
            _merge_scalar(journal_entry, "fiscal_year", _normalize_id(record.get("fiscalYear")))
            _merge_scalar(journal_entry, "accounting_document_item", _normalize_id(record.get("accountingDocumentItem")))
            _merge_scalar(journal_entry, "gl_account", _normalize_id(record.get("glAccount")))
            _merge_scalar(journal_entry, "cost_center", _normalize_id(record.get("costCenter")))
            _merge_scalar(journal_entry, "profit_center", _normalize_id(record.get("profitCenter")))
            _merge_scalar(journal_entry, "transaction_currency", _normalize_id(record.get("transactionCurrency")))
            _merge_scalar(journal_entry, "amount_in_transaction_currency", _to_decimal(record.get("amountInTransactionCurrency")))
            _merge_scalar(journal_entry, "company_code_currency", _normalize_id(record.get("companyCodeCurrency")))
            _merge_scalar(journal_entry, "amount_in_company_code_currency", _to_decimal(record.get("amountInCompanyCodeCurrency")))
            _merge_scalar(journal_entry, "posting_date", _to_datetime(record.get("postingDate")))
            _merge_scalar(journal_entry, "document_date", _to_datetime(record.get("documentDate")))
            _merge_scalar(journal_entry, "accounting_document_type", _normalize_id(record.get("accountingDocumentType")))
            _merge_scalar(journal_entry, "assignment_reference", _normalize_id(record.get("assignmentReference")))
            _merge_scalar(journal_entry, "last_change_at", _to_datetime(record.get("lastChangeDateTime")))
            _merge_scalar(journal_entry, "financial_account_type", _normalize_id(record.get("financialAccountType")))
            _merge_scalar(journal_entry, "clearing_date", _to_datetime(record.get("clearingDate")))
            _merge_scalar(journal_entry, "clearing_accounting_document", clearing_document_id)
            _merge_scalar(journal_entry, "clearing_doc_fiscal_year", fiscal_year)
            journal_entry["metadata"].update(record)
            if clearing_document_id:
                ar_invoice_links[(customer_id, clearing_document_id, fiscal_year)].add(invoice_id)
            invoice = self._ensure_entity(invoices, invoice_id, dataset_name)
            if invoice:
                _merge_collection(invoice, "journal_entry_ids", [journal_entry_id])
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

    def _finalize_records(self, model: type[BaseModel], bucket: dict[str, dict[str, Any]]) -> list[Any]:
        records: list[Any] = []
        for entity_id in sorted(bucket):
            payload = dict(bucket[entity_id])
            payload["source_datasets"] = sorted(payload.get("source_datasets", set()))
            for key, value in list(payload.items()):
                if isinstance(value, set):
                    payload[key] = sorted(value)
            records.append(model.model_validate(payload))
        return records
