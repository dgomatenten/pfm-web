"""HTML routes for receipt management."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, abort, request, flash
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Receipt, ReceiptLineItem, Category, Shop, User, AmazonOrder, AmazonOrderItem
from ..services.spending_analyzer import SpendingAnalyzer

web_bp = Blueprint("web", __name__, template_folder="templates")


@web_bp.get("/")
def index():
    """Home page with navigation to all features."""
    return render_template("home.html")


@web_bp.get("/analytics")
def analytics_dashboard():
    """Analytics dashboard combining receipts and Amazon orders."""
    return render_template("analytics_dashboard.html")


@web_bp.get("/spending")
def unified_spending():
    """Unified view of all spending (receipts + Amazon orders)."""
    # Get filter parameters
    user_id_filter = request.args.get('user_id', 'all')
    source_filter = request.args.get('source', 'all')
    currency_filter = request.args.get('currency', 'all')
    
    # Get all users for the filter dropdown
    users = User.query.order_by(User.email).all()
    
    # Parse user_id
    user_id = None
    if user_id_filter != 'all':
        try:
            user_id = int(user_id_filter)
        except ValueError:
            pass
    
    # Get unified spending data
    items = SpendingAnalyzer.get_unified_spending(user_id=user_id, limit=200)
    
    # Apply source filter
    if source_filter != 'all':
        items = [item for item in items if item.source == source_filter]
    
    # Apply currency filter
    if currency_filter != 'all':
        items = [item for item in items if item.currency == currency_filter]
    
    # Get unique currencies from all items for dropdown
    currencies = sorted(set(item.currency for item in items))
    
    # Get summary statistics (filtered)
    summary = SpendingAnalyzer.get_spending_summary(user_id=user_id)
    
    # Recalculate summary for filtered items
    if currency_filter != 'all' or source_filter != 'all':
        filtered_summary = {
            'total_spending': sum(item.total_amount for item in items),
            'receipt_spending': sum(item.total_amount for item in items if item.source == 'receipt'),
            'amazon_spending': sum(item.total_amount for item in items if item.source == 'amazon'),
            'receipt_count': sum(1 for item in items if item.source == 'receipt'),
            'amazon_count': sum(1 for item in items if item.source == 'amazon'),
            'total_transactions': len(items),
            'average_transaction': sum(item.total_amount for item in items) / len(items) if items else 0,
        }
        summary.update(filtered_summary)
    
    return render_template("spending/unified.html",
                         items=items,
                         summary=summary,
                         users=users,
                         currencies=currencies,
                         selected_user_id=user_id_filter,
                         selected_source=source_filter,
                         selected_currency=currency_filter)


@web_bp.get("/receipts")
def receipts_list():
    # Get user filter parameter
    user_id_filter = request.args.get('user_id', 'all')
    
    # Get all users for the filter dropdown
    users = User.query.order_by(User.email).all()
    
    # Build query
    query = Receipt.query.options(
        selectinload(Receipt.shop),
        selectinload(Receipt.items),
        selectinload(Receipt.user),
    )
    
    # Apply user filter if not 'all'
    if user_id_filter != 'all':
        try:
            user_id = int(user_id_filter)
            query = query.filter(Receipt.user_id == user_id)
        except ValueError:
            pass  # Invalid user_id, show all
    
    receipts = query.order_by(Receipt.issued_at.desc()).limit(100).all()
    
    return render_template("receipts/list.html", 
                         receipts=receipts, 
                         users=users,
                         selected_user_id=user_id_filter)


@web_bp.route("/receipts/new", methods=["GET", "POST"])
def receipt_create():
    """Create a new receipt manually."""
    if request.method == "POST":
        try:
            # Parse basic fields
            vendor_name = request.form.get("vendor_name", "").strip()
            vendor_address = request.form.get("vendor_address", "").strip() or None
            receipt_number = request.form.get("receipt_number", "").strip() or None
            issued_at_str = request.form.get("issued_at")
            total_amount = float(request.form.get("total_amount", 0))
            currency = request.form.get("currency", "USD")
            tax_amount = request.form.get("tax_amount")
            payment_method = request.form.get("payment_method") or None
            category_id = request.form.get("category_id") or None
            shop_id = request.form.get("shop_id") or None
            
            # Validate required fields
            if not vendor_name:
                flash("Vendor name is required", "error")
                return redirect(url_for("web.receipt_create"))
            
            if not issued_at_str:
                flash("Receipt date is required", "error")
                return redirect(url_for("web.receipt_create"))
            
            # Parse date
            issued_at = datetime.fromisoformat(issued_at_str)
            
            # Create receipt
            receipt = Receipt(
                source="manual",
                vendor_name=vendor_name,
                vendor_address=vendor_address,
                receipt_number=receipt_number,
                issued_at=issued_at,
                total_amount=total_amount,
                currency=currency,
                tax_amount=float(tax_amount) if tax_amount else None,
                payment_method=payment_method,
                category_id=int(category_id) if category_id else None,
                shop_id=int(shop_id) if shop_id else None,
                status="completed",
                processing_engine="manual_entry",
                confidence_score=1.0
            )
            
            db.session.add(receipt)
            db.session.flush()  # Get receipt ID
            
            # Process line items if provided
            item_names = request.form.getlist("item_name[]")
            item_quantities = request.form.getlist("item_quantity[]")
            item_prices = request.form.getlist("item_price[]")
            item_totals = request.form.getlist("item_total[]")
            
            for i, item_name in enumerate(item_names):
                if item_name and item_name.strip():
                    quantity = float(item_quantities[i]) if i < len(item_quantities) and item_quantities[i] else 1.0
                    unit_price = float(item_prices[i]) if i < len(item_prices) and item_prices[i] else 0.0
                    total_price = float(item_totals[i]) if i < len(item_totals) and item_totals[i] else (quantity * unit_price)
                    
                    line_item = ReceiptLineItem(
                        receipt_id=receipt.id,
                        item_name=item_name.strip(),
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=total_price
                    )
                    db.session.add(line_item)
            
            db.session.commit()
            flash(f"Receipt created successfully (ID: {receipt.id})", "success")
            return redirect(url_for("web.receipt_detail", receipt_id=receipt.id))
            
        except ValueError as e:
            db.session.rollback()
            flash(f"Invalid input: {str(e)}", "error")
            return redirect(url_for("web.receipt_create"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating receipt: {str(e)}", "error")
            return redirect(url_for("web.receipt_create"))
    
    # GET request - show form
    categories = Category.query.order_by(Category.name).all()
    shops = Shop.query.order_by(Shop.name).all()
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template("receipts/create.html", 
                         categories=categories, 
                         shops=shops,
                         today=today)


@web_bp.get("/receipts/<int:receipt_id>")
def receipt_detail(receipt_id: int):
    receipt = (
        Receipt.query.options(
            selectinload(Receipt.items),
            selectinload(Receipt.shop),
            selectinload(Receipt.category),
        )
        .filter_by(id=receipt_id)
        .first()
    )
    if receipt is None:
        abort(404)
    return render_template("receipts/detail.html", receipt=receipt)


@web_bp.post("/receipts/<int:receipt_id>/delete")
def receipt_delete(receipt_id: int):
    """Delete a receipt."""
    receipt = Receipt.query.filter_by(id=receipt_id).first()
    if receipt is None:
        abort(404)
    
    try:
        # Delete associated items first (cascade should handle this, but being explicit)
        for item in receipt.items:
            db.session.delete(item)
        
        # Delete the receipt
        db.session.delete(receipt)
        db.session.commit()
        
        flash(f"Receipt #{receipt_id} deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting receipt: {str(e)}", "error")
    
    return redirect(url_for("web.receipts_list"))


@web_bp.route("/receipts/<int:receipt_id>/edit", methods=["GET", "POST"])
def receipt_edit(receipt_id: int):
    """Edit a receipt."""
    receipt = (
        Receipt.query.options(
            selectinload(Receipt.items),
            selectinload(Receipt.shop),
        )
        .filter_by(id=receipt_id)
        .first()
    )
    if receipt is None:
        abort(404)
    
    if request.method == "POST":
        try:
            # Update basic fields
            receipt.vendor_name = request.form.get("vendor_name", receipt.vendor_name)
            receipt.vendor_address = request.form.get("vendor_address", receipt.vendor_address)
            receipt.total_amount = float(request.form.get("total_amount", receipt.total_amount))
            receipt.payment_method = request.form.get("payment_method", receipt.payment_method)
            receipt.receipt_number = request.form.get("receipt_number", receipt.receipt_number)
            
            # Update date if provided
            date_str = request.form.get("issued_at")
            if date_str:
                from datetime import datetime
                receipt.issued_at = datetime.fromisoformat(date_str)
            
            db.session.commit()
            flash("Receipt updated successfully", "success")
            return redirect(url_for("web.receipt_detail", receipt_id=receipt.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating receipt: {str(e)}", "error")
    
    return render_template("receipts/edit.html", receipt=receipt)


# Amazon Orders routes
@web_bp.get("/amazon/orders")
def amazon_orders_list():
    """List all Amazon orders with user filter."""
    # Get user filter parameter
    user_id_filter = request.args.get('user_id', 'all')
    
    # Get all users for the filter dropdown
    users = User.query.order_by(User.email).all()
    
    # Build query with user relationship
    query = AmazonOrder.query.options(
        selectinload(AmazonOrder.items),
        selectinload(AmazonOrder.user),
    )
    
    # Apply user filter if not 'all'
    if user_id_filter != 'all':
        try:
            user_id = int(user_id_filter)
            query = query.filter(AmazonOrder.user_id == user_id)
        except ValueError:
            pass  # Invalid user_id, show all
    
    orders = query.order_by(AmazonOrder.order_date.desc()).limit(100).all()
    
    return render_template("amazon/list.html", 
                         orders=orders, 
                         users=users,
                         selected_user_id=user_id_filter)


@web_bp.get("/amazon/orders/<int:order_id>")
def amazon_order_detail(order_id):
    """View Amazon order details."""
    order = (
        AmazonOrder.query.options(
            selectinload(AmazonOrder.items).selectinload(AmazonOrderItem.category),
            selectinload(AmazonOrder.user),
        )
        .filter_by(id=order_id)
        .first()
    )
    if order is None:
        abort(404)
    return render_template("amazon/detail.html", order=order)


@web_bp.route("/amazon/orders/<int:order_id>/delete", methods=["POST"])
def amazon_order_delete(order_id):
    """Delete an Amazon order."""
    order = AmazonOrder.query.filter_by(id=order_id).first()
    if order is None:
        abort(404)
    
    try:
        db.session.delete(order)
        db.session.commit()
        flash("Amazon order deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting order: {str(e)}", "error")
    
    return redirect(url_for("web.amazon_orders_list"))


@web_bp.get("/data-browser")
def data_browser():
    """Browse files in the data directory."""
    import os
    from pathlib import Path
    from flask import current_app, send_from_directory
    
    # Get the data directory path
    data_dir = Path(current_app.root_path).parent / "data"
    
    # Get the requested path (relative to data dir)
    subpath = request.args.get('path', '')
    current_path = data_dir / subpath if subpath else data_dir
    
    # Security: ensure we don't escape the data directory
    try:
        current_path = current_path.resolve()
        data_dir = data_dir.resolve()
        if not str(current_path).startswith(str(data_dir)):
            abort(403)
    except Exception:
        abort(403)
    
    # Check if path exists
    if not current_path.exists():
        abort(404)
    
    # If it's a file, serve it
    if current_path.is_file():
        return send_from_directory(current_path.parent, current_path.name)
    
    # If it's a directory, list contents
    items = []
    if current_path.is_dir():
        for item in sorted(current_path.iterdir()):
            rel_path = item.relative_to(data_dir)
            items.append({
                'name': item.name,
                'path': str(rel_path),
                'is_dir': item.is_dir(),
                'size': item.stat().st_size if item.is_file() else None,
                'modified': datetime.fromtimestamp(item.stat().st_mtime)
            })
    
    # Get breadcrumb path
    breadcrumbs = []
    if subpath:
        parts = Path(subpath).parts
        for i, part in enumerate(parts):
            breadcrumbs.append({
                'name': part,
                'path': str(Path(*parts[:i+1]))
            })
    
    return render_template(
        "data_browser.html",
        items=items,
        current_path=subpath or '/',
        breadcrumbs=breadcrumbs
    )
