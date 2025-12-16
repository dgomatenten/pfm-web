"""API routes for receipt synchronization with mobile app."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, request
from flask_restful import Api, Resource
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Receipt, ReceiptLineItem, Shop, Category, User, AmazonOrder, AmazonOrderItem

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
        device_user_id = request.args.get("user_id")

        # Build query
        query = Receipt.query

        # Filter by user_id if provided
        if device_user_id:
            user = User.query.filter_by(email=f"{device_user_id}@device").first()
            if user:
                query = query.filter(Receipt.user_id == user.id)
            else:
                # No user found, return empty result
                return {
                    "receipts": [],
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": 0,
                        "pages": 0,
                        "has_next": False,
                        "has_prev": False,
                    }
                }

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
        
        print(f"[API] Received POST request to /receipts")
        print(f"[API] Request data keys: {list(data.keys()) if data else 'None'}")
        print(f"[API] User ID from request: {data.get('user_id') if data else 'None'}")
        
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
            # Get user_id from request data (device ID from mobile app)
            device_user_id = data.get("user_id")
            
            if device_user_id:
                # Get or create user with device ID as email
                user = User.query.filter_by(email=f"{device_user_id}@device").first()
                if not user:
                    print(f"Creating new user for device: {device_user_id}")
                    user = User(
                        email=f"{device_user_id}@device",
                        password_hash="device_auth",
                        role="owner"
                    )
                    db.session.add(user)
                    db.session.flush()
            else:
                # Fallback to default user for backward compatibility
                user = User.query.first()
                if not user:
                    user = User(email="default@local", password_hash="dummy", role="owner")
                    db.session.add(user)
                    db.session.flush()

            # Check for duplicates using external_ref (mobile app's local ID)
            external_ref = data.get("external_ref")
            if external_ref:
                # First check if receipt exists with ANY user (for migration from old data)
                existing = Receipt.query.filter_by(
                    external_ref=external_ref,
                    source=data.get("source", "mobile_app")
                ).first()
                
                if existing:
                    # If receipt exists but with wrong user, update the user_id
                    if existing.user_id != user.id:
                        print(f"[API] Migrating receipt {existing.id} from user {existing.user_id} to user {user.id}")
                        existing.user_id = user.id
                        db.session.commit()
                    
                    # Return existing receipt
                    return {
                        "message": "Receipt already exists",
                        "receipt": ReceiptResource()._serialize_receipt(existing),
                        "duplicate": True
                    }, 200

            print(f"[API] Creating receipt for user_id: {user.id}, email: {user.email}")
            
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
            print(f"[API] Receipt created successfully with ID: {receipt.id}")
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


@api_bp.route("/amazon-orders")
def get_amazon_orders_api():
    """Get Amazon orders for syncing to mobile app."""
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', type=int, default=1000)
    offset = request.args.get('offset', type=int, default=0)
    
    query = AmazonOrder.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    orders = query.order_by(AmazonOrder.order_date.desc()).limit(limit).offset(offset).all()
    
    # Serialize orders
    serialized_orders = []
    for order in orders:
        serialized_orders.append({
            'id': order.id,
            'order_id': order.order_number,  # Use order_number instead of order_id
            'order_date': order.order_date.isoformat(),
            'total_amount': float(order.total_amount),
            'currency': order.currency,
            'status': order.shipment_status,  # Use shipment_status instead of status
            'user_id': order.user_id,
            'user_email': order.user.email if order.user else None,
            'items_count': len(order.items) if order.items else 0
        })
    
    return jsonify({
        'orders': serialized_orders,
        'total': total,
        'limit': limit,
        'offset': offset,
        'has_more': (offset + len(orders)) < total
    })


@api_bp.route("/amazon-orders/<int:order_id>/items")
def get_amazon_order_items_api(order_id):
    """Get items for a specific Amazon order."""
    order = AmazonOrder.query.get_or_404(order_id)
    
    # Serialize items
    serialized_items = []
    for item in order.items:
        serialized_items.append({
            'id': item.id,
            'title': item.item_name,  # Use item_name instead of title
            'category': item.category.name if item.category else None,  # Get category name
            'quantity': int(item.quantity),
            'price': float(item.unit_price),  # Use unit_price instead of price
            'currency': order.currency,  # Get currency from order
            'asin': item.asin
        })
    
    return jsonify({
        'order_id': order.id,
        'items': serialized_items,
        'count': len(serialized_items)
    })


@api_bp.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "pfm-api", "version": "1.0.0"})


@api_bp.route("/spending/unified")
def unified_spending_api():
    """Get unified spending data from receipts and Amazon orders."""
    from .services.spending_analyzer import SpendingAnalyzer
    
    # Get query parameters
    user_id = request.args.get('user_id', type=int)
    source = request.args.get('source')  # 'receipt', 'amazon', or None for all
    currency = request.args.get('currency')
    limit = request.args.get('limit', type=int, default=100)
    
    # Get unified spending data
    items = SpendingAnalyzer.get_unified_spending(user_id=user_id, limit=limit)
    
    # Apply filters
    if source:
        items = [item for item in items if item.source == source]
    if currency:
        items = [item for item in items if item.currency == currency]
    
    # Get summary
    summary = SpendingAnalyzer.get_spending_summary(user_id=user_id)
    
    # Serialize items
    serialized_items = []
    for item in items:
        serialized_items.append({
            'id': item.id,
            'source': item.source,
            'date': item.date.isoformat(),
            'vendor': item.vendor,
            'total_amount': item.total_amount,
            'currency': item.currency,
            'payment_method': item.payment_method,
            'category': item.category,
            'item_count': item.item_count,
            'user_email': item.user_email,
            'user_id': item.user_id,
            'status': item.status,
            'order_number': item.order_number,
            'display_id': item.display_id,
            'source_icon': item.source_icon,
        })
    
    return jsonify({
        'items': serialized_items,
        'summary': summary,
        'count': len(serialized_items),
    })