"""API routes for receipt synchronization with mobile app."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, request
from flask_restful import Api, Resource
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Receipt, ReceiptLineItem, Shop, Category, User

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")
api = Api(api_bp)


class ReceiptResource(Resource):
    """Resource for individual receipt operations."""

    def get(self, receipt_id: int):
        """Get a specific receipt by ID."""
        receipt = Receipt.query.get_or_404(receipt_id)
        return self._serialize_receipt(receipt)

    def put(self, receipt_id: int):
        """Update a specific receipt."""
        receipt = Receipt.query.get_or_404(receipt_id)
        data = request.get_json()
        
        if not data:
            return {"error": "No data provided"}, 400

        try:
            self._update_receipt_from_data(receipt, data)
            db.session.commit()
            return self._serialize_receipt(receipt)
        except Exception as e:
            db.session.rollback()
            return {"error": str(e)}, 400

    def delete(self, receipt_id: int):
        """Delete a specific receipt."""
        receipt = Receipt.query.get_or_404(receipt_id)
        
        try:
            db.session.delete(receipt)
            db.session.commit()
            return {"message": "Receipt deleted successfully"}, 200
        except Exception as e:
            db.session.rollback()
            return {"error": str(e)}, 400

    def _serialize_receipt(self, receipt: Receipt) -> Dict:
        """Convert receipt model to JSON-serializable dict."""
        return {
            "id": receipt.id,
            "source": receipt.source,
            "external_ref": receipt.external_ref,
            "issued_at": receipt.issued_at.isoformat(),
            "total_amount": receipt.total_amount,
            "currency": receipt.currency,
            "tax_amount": receipt.tax_amount,
            "payment_method": receipt.payment_method,
            "receipt_number": receipt.receipt_number,
            "vendor_name": receipt.vendor_name,
            "vendor_address": receipt.vendor_address,
            "shop_id": receipt.shop_id,
            "shop_name": receipt.shop.name if receipt.shop else receipt.vendor_name,
            "shop_address": receipt.shop.address if receipt.shop else receipt.vendor_address,
            "category_id": receipt.category_id,
            "status": receipt.status,
            "processing_engine": receipt.processing_engine,
            "confidence_score": receipt.confidence_score,
            "language_detected": receipt.language_detected,
            "attachment_path": receipt.attachment_path,
            "created_at": receipt.created_at.isoformat(),
            "updated_at": receipt.updated_at.isoformat(),
            "items": [self._serialize_receipt_item(item) for item in receipt.items]
        }

    def _serialize_receipt_item(self, item: ReceiptLineItem) -> Dict:
        """Convert receipt item model to JSON-serializable dict."""
        return {
            "id": item.id,
            "item_name": item.item_name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "total_price": item.total_price,
            "category_id": item.category_id,
            "description": item.description,
            "created_at": item.created_at.isoformat(),
        }

    def _update_receipt_from_data(self, receipt: Receipt, data: Dict):
        """Update receipt model from request data."""
        # Update basic receipt fields
        if "issued_at" in data:
            receipt.issued_at = datetime.fromisoformat(data["issued_at"])
        if "total_amount" in data:
            receipt.total_amount = float(data["total_amount"])
        if "currency" in data:
            receipt.currency = data["currency"]
        if "tax_amount" in data:
            receipt.tax_amount = float(data["tax_amount"]) if data["tax_amount"] else None
        if "payment_method" in data:
            receipt.payment_method = data["payment_method"]
        if "receipt_number" in data:
            receipt.receipt_number = data["receipt_number"]
        if "vendor_name" in data:
            receipt.vendor_name = data["vendor_name"]
        if "vendor_address" in data:
            receipt.vendor_address = data["vendor_address"]
        if "status" in data:
            receipt.status = data["status"]
        if "confidence_score" in data:
            receipt.confidence_score = float(data["confidence_score"]) if data["confidence_score"] else None
        if "language_detected" in data:
            receipt.language_detected = data["language_detected"]

        # Handle shop association
        if "shop_name" in data:
            shop_address = data.get("shop_address", data.get("vendor_address"))
            shop = self._get_or_create_shop(data["shop_name"], shop_address)
            receipt.shop_id = shop.id

        # Handle items
        if "items" in data:
            # Clear existing items
            ReceiptLineItem.query.filter_by(receipt_id=receipt.id).delete()
            
            # Add new items
            for item_data in data["items"]:
                item = ReceiptLineItem(
                    receipt_id=receipt.id,
                    item_name=item_data["item_name"],
                    quantity=float(item_data.get("quantity", 1.0)),
                    unit_price=float(item_data["unit_price"]),
                    total_price=float(item_data["total_price"]),
                    description=item_data.get("description")
                )
                db.session.add(item)

    def _get_or_create_shop(self, shop_name: str, shop_address: Optional[str] = None) -> Shop:
        """Get existing shop or create new one."""
        shop = Shop.query.filter_by(name=shop_name).first()
        if not shop:
            shop = Shop(name=shop_name, address=shop_address)
            db.session.add(shop)
            db.session.flush()  # Get ID without committing
        elif shop_address and not shop.address:
            # Update shop address if it was empty
            shop.address = shop_address
        return shop


class ReceiptListResource(Resource):
    """Resource for receipt collection operations."""

    def get(self):
        """Get list of receipts with optional filtering."""
        # Query parameters
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 50)), 100)  # Max 100 per page
        currency = request.args.get("currency")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        status = request.args.get("status")
        shop_id = request.args.get("shop_id")

        # Build query
        query = Receipt.query

        if currency:
            query = query.filter(Receipt.currency == currency)
        if start_date:
            query = query.filter(Receipt.issued_at >= datetime.fromisoformat(start_date))
        if end_date:
            query = query.filter(Receipt.issued_at <= datetime.fromisoformat(end_date))
        if status:
            query = query.filter(Receipt.status == status)
        if shop_id:
            query = query.filter(Receipt.shop_id == int(shop_id))

        # Order by date descending
        query = query.order_by(Receipt.issued_at.desc())

        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        receipts = pagination.items

        return {
            "receipts": [ReceiptResource()._serialize_receipt(receipt) for receipt in receipts],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            }
        }

    def post(self):
        """Create a new receipt."""
        data = request.get_json()
        
        if not data:
            return {"error": "No data provided"}, 400

        # Validate required fields
        required_fields = ["total_amount", "issued_at"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return {
                "error": f"Missing required fields: {', '.join(missing_fields)}",
                "missing_fields": missing_fields
            }, 400

        # Validate data types
        try:
            float(data["total_amount"])
        except (ValueError, TypeError):
            return {"error": "total_amount must be a valid number"}, 400

        try:
            datetime.fromisoformat(data["issued_at"])
        except (ValueError, TypeError):
            return {"error": "issued_at must be a valid ISO format date"}, 400

        try:
            # Get or create default user (for now, single user setup)
            user = User.query.first()
            if not user:
                user = User(email="default@local", password_hash="dummy", role="owner")
                db.session.add(user)
                db.session.flush()

            # Check for duplicates using external_ref (mobile app's local ID)
            external_ref = data.get("external_ref")
            if external_ref:
                existing = Receipt.query.filter_by(
                    external_ref=external_ref,
                    source=data.get("source", "mobile_app")
                ).first()
                
                if existing:
                    # Return existing receipt instead of creating duplicate
                    return {
                        "message": "Receipt already exists",
                        "receipt": self._serialize_receipt(existing),
                        "duplicate": True
                    }, 200

            # Create receipt
            receipt = Receipt(
                user_id=user.id,
                source=data.get("source", "mobile_app"),
                external_ref=data.get("external_ref"),
                issued_at=datetime.fromisoformat(data["issued_at"]) if "issued_at" in data else datetime.now(),
                total_amount=float(data["total_amount"]),
                currency=data.get("currency", "USD"),
                tax_amount=float(data["tax_amount"]) if data.get("tax_amount") else None,
                payment_method=data.get("payment_method"),
                receipt_number=data.get("receipt_number"),
                vendor_name=data.get("vendor_name", data.get("shop_name")),
                vendor_address=data.get("vendor_address", data.get("shop_address")),
                status=data.get("status", "processed"),
                raw_payload=data.get("raw_ocr_text"),
                processing_engine=data.get("processing_engine", "unknown"),
                confidence_score=float(data["confidence_score"]) if data.get("confidence_score") else None,
                language_detected=data.get("language_detected"),
            )

            # Handle shop association
            if "shop_name" in data:
                shop_address = data.get("shop_address", data.get("vendor_address"))
                shop = self._get_or_create_shop(data["shop_name"], shop_address)
                receipt.shop_id = shop.id

            db.session.add(receipt)
            db.session.flush()  # Get receipt ID

            # Add items
            if "items" in data:
                for item_data in data["items"]:
                    item = ReceiptLineItem(
                        receipt_id=receipt.id,
                        item_name=item_data["item_name"],
                        quantity=float(item_data.get("quantity", 1.0)),
                        unit_price=float(item_data["unit_price"]),
                        total_price=float(item_data["total_price"]),
                        description=item_data.get("description")
                    )
                    db.session.add(item)

            db.session.commit()
            return ReceiptResource()._serialize_receipt(receipt), 201

        except IntegrityError as e:
            db.session.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            return {
                "error": "Receipt with this external reference already exists",
                "detail": error_msg
            }, 409
        except ValueError as e:
            db.session.rollback()
            return {
                "error": "Invalid data format",
                "detail": str(e)
            }, 400
        except Exception as e:
            db.session.rollback()
            return {
                "error": "Failed to create receipt",
                "detail": str(e),
                "type": type(e).__name__
            }, 400

    def _get_or_create_shop(self, shop_name: str, shop_address: Optional[str] = None) -> Shop:
        """Get existing shop or create new one."""
        shop = Shop.query.filter_by(name=shop_name).first()
        if not shop:
            shop = Shop(name=shop_name, address=shop_address)
            db.session.add(shop)
            db.session.flush()
        elif shop_address and not shop.address:
            # Update shop address if it was empty
            shop.address = shop_address
        return shop


class SyncStatusResource(Resource):
    """Resource for checking sync status and stats."""

    def get(self):
        """Get sync statistics and status."""
        total_receipts = Receipt.query.count()
        pending_receipts = Receipt.query.filter_by(status="pending").count()
        processed_receipts = Receipt.query.filter_by(status="processed").count()
        
        # Get recent receipts (last 24 hours)
        last_24h = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        recent_receipts = Receipt.query.filter(Receipt.created_at >= last_24h).count()

        # Get currency breakdown
        currency_stats = db.session.query(
            Receipt.currency,
            db.func.count(Receipt.id).label('count'),
            db.func.sum(Receipt.total_amount).label('total')
        ).group_by(Receipt.currency).all()

        return {
            "sync_status": "active",
            "last_sync": datetime.now().isoformat(),
            "statistics": {
                "total_receipts": total_receipts,
                "pending_receipts": pending_receipts,
                "processed_receipts": processed_receipts,
                "recent_receipts_24h": recent_receipts,
                "currency_breakdown": [
                    {
                        "currency": stat.currency,
                        "count": stat.count,
                        "total_amount": float(stat.total)
                    }
                    for stat in currency_stats
                ]
            }
        }


# Register API resources
api.add_resource(ReceiptListResource, "/receipts")
api.add_resource(ReceiptResource, "/receipts/<int:receipt_id>")
api.add_resource(SyncStatusResource, "/sync/status")


@api_bp.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "pfm-api", "version": "1.0.0"})