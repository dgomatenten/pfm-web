"""HTML routes for receipt management."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, abort, request, flash
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Receipt, ReceiptLineItem, Category, Shop

web_bp = Blueprint("web", __name__, template_folder="templates")


@web_bp.get("/")
def index():
    """Home page with navigation to all features."""
    return render_template("home.html")


@web_bp.get("/analytics")
def analytics_dashboard():
    """Analytics dashboard combining receipts and Amazon orders."""
    return render_template("analytics_dashboard.html")


@web_bp.get("/receipts")
def receipts_list():
    receipts = (
        Receipt.query.options(
            selectinload(Receipt.shop),
            selectinload(Receipt.items),
        )
        .order_by(Receipt.issued_at.desc())
        .limit(100)
        .all()
    )
    return render_template("receipts/list.html", receipts=receipts)


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
