"""Import utilities for ingesting data exports into the database."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .extensions import db
from .models import Receipt, ReceiptLineItem, Shop


@dataclass
class ImportResult:
    receipts_created: int = 0
    receipts_skipped: int = 0
    line_items_created: int = 0


def load_receipts_export(path: Path) -> dict:
    """Load a JSON export file produced by the Android app."""
    payload = json.loads(path.read_text())
    if "receipts" not in payload:
        raise ValueError("Invalid export: missing receipts key")
    return payload


def import_receipts_export(payload: dict) -> ImportResult:
    """Persist receipts payload into the relational schema."""
    result = ImportResult()

    for receipt_data in payload.get("receipts", []):
        created = _upsert_receipt(receipt_data)
        if created:
            result.receipts_created += 1
            result.line_items_created += len(receipt_data.get("items", []))
        else:
            result.receipts_skipped += 1

    db.session.commit()
    return result


def _upsert_receipt(receipt_data: dict) -> bool:
    external_ref = str(receipt_data["id"])
    existing = Receipt.query.filter_by(external_ref=external_ref).first()
    if existing:
        return False

    receipt = Receipt(
        external_ref=external_ref,
        source="android",
        issued_at=_parse_datetime(receipt_data.get("date")),
        total_amount=receipt_data.get("total_amount"),
        currency=receipt_data.get("currency", "USD"),
        tax_amount=receipt_data.get("tax_amount"),
        payment_method=receipt_data.get("payment_method"),
        receipt_number=receipt_data.get("receipt_number"),
        raw_payload=json.dumps(receipt_data, ensure_ascii=False),
        processing_engine=receipt_data.get("processing_engine", "unknown"),
        confidence_score=receipt_data.get("confidence_score"),
        language_detected=receipt_data.get("language_detected"),
        vendor_name=receipt_data.get("shop_name"),
    )

    shop = _get_or_create_shop(receipt_data.get("shop_name"))
    receipt.shop = shop

    for item in receipt_data.get("items", []):
        receipt.items.append(_build_receipt_item(item))

    db.session.add(receipt)
    return True


def _build_receipt_item(item_data: dict) -> ReceiptLineItem:
    return ReceiptLineItem(
        item_name=item_data.get("name"),
        quantity=item_data.get("quantity", 1.0),
        unit_price=item_data.get("unit_price"),
        total_price=item_data.get("total_price"),
        description=item_data.get("description"),
    )


def _get_or_create_shop(name: str | None) -> Shop | None:
    if not name:
        return None
    shop = Shop.query.filter_by(name=name).first()
    if shop:
        return shop
    shop = Shop(name=name)
    db.session.add(shop)
    return shop


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.utcnow()