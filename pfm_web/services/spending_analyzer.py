"""Service for merging and analyzing spending data from multiple sources."""
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from ..models import Receipt, AmazonOrder, User
from ..extensions import db


@dataclass
class SpendingItem:
    """Unified spending item from any source."""
    id: str  # Format: "receipt_123" or "amazon_456"
    source: str  # "receipt" or "amazon"
    date: datetime
    vendor: str
    total_amount: float
    currency: str
    payment_method: Optional[str]
    category: Optional[str]
    item_count: int
    user_email: Optional[str]
    user_id: Optional[int]
    status: Optional[str] = None
    order_number: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def display_id(self) -> str:
        """Human-readable ID for display."""
        if self.source == "receipt":
            return f"R-{self.id.split('_')[1]}"
        else:
            return f"A-{self.id.split('_')[1]}"
    
    @property
    def source_icon(self) -> str:
        """Icon for the source type."""
        return "📄" if self.source == "receipt" else "📦"


class SpendingAnalyzer:
    """Analyze and merge spending data from receipts and Amazon orders."""
    
    @staticmethod
    def get_unified_spending(
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[SpendingItem]:
        """
        Get unified spending data from all sources.
        
        Args:
            user_id: Filter by user ID (None for all users)
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of items to return
        
        Returns:
            List of SpendingItem objects sorted by date (newest first)
        """
        items = []
        
        # Get receipts
        receipt_query = Receipt.query.options(
            db.joinedload(Receipt.user),
            db.joinedload(Receipt.shop),
            db.joinedload(Receipt.category),
            db.joinedload(Receipt.items),
        )
        
        if user_id:
            receipt_query = receipt_query.filter(Receipt.user_id == user_id)
        if start_date:
            receipt_query = receipt_query.filter(Receipt.issued_at >= start_date)
        if end_date:
            receipt_query = receipt_query.filter(Receipt.issued_at <= end_date)
        
        receipts = receipt_query.order_by(Receipt.issued_at.desc()).limit(limit).all()
        
        for receipt in receipts:
            items.append(SpendingItem(
                id=f"receipt_{receipt.id}",
                source="receipt",
                date=receipt.issued_at,
                vendor=receipt.vendor_name or (receipt.shop.name if receipt.shop else "Unknown"),
                total_amount=receipt.total_amount,
                currency=receipt.currency,
                payment_method=receipt.payment_method,
                category=receipt.category.name if receipt.category else None,
                item_count=len(receipt.items),
                user_email=receipt.user.email if receipt.user else None,
                user_id=receipt.user_id,
                status=receipt.status,
                raw_data={
                    'receipt_number': receipt.receipt_number,
                    'vendor_address': receipt.vendor_address,
                    'tax_amount': receipt.tax_amount,
                }
            ))
        
        # Get Amazon orders
        from ..models import AmazonOrderItem
        amazon_query = AmazonOrder.query.options(
            db.joinedload(AmazonOrder.user),
            db.joinedload(AmazonOrder.items).joinedload(AmazonOrderItem.category),
        )
        
        # Filter by user_id
        if user_id:
            amazon_query = amazon_query.filter(AmazonOrder.user_id == user_id)
        if start_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date >= start_date)
        if end_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date <= end_date)
        
        orders = amazon_query.order_by(AmazonOrder.order_date.desc()).limit(limit).all()
        
        for order in orders:
            # Determine category from items
            categories = [item.category.name for item in order.items if item.category]
            primary_category = categories[0] if categories else None
            
            items.append(SpendingItem(
                id=f"amazon_{order.id}",
                source="amazon",
                date=order.order_date,
                vendor="Amazon",
                total_amount=order.total_amount,
                currency=order.currency,
                payment_method=order.payment_method,
                category=primary_category,
                item_count=len(order.items),
                user_email=order.user.email if order.user else None,
                user_id=order.user_id,
                status=order.shipment_status,
                order_number=order.order_number,
                raw_data={
                    'order_number': order.order_number,
                    'shipment_status': order.shipment_status,
                }
            ))
        
        # Sort all items by date (newest first)
        items.sort(key=lambda x: x.date, reverse=True)
        
        # Apply overall limit
        return items[:limit]
    
    @staticmethod
    def get_spending_summary(
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get spending summary statistics.
        
        Returns:
            Dictionary with summary statistics
        """
        items = SpendingAnalyzer.get_unified_spending(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000  # Get all for summary
        )
        
        total_spending = sum(item.total_amount for item in items)
        receipt_spending = sum(item.total_amount for item in items if item.source == "receipt")
        amazon_spending = sum(item.total_amount for item in items if item.source == "amazon")
        
        receipt_count = sum(1 for item in items if item.source == "receipt")
        amazon_count = sum(1 for item in items if item.source == "amazon")
        
        # Category breakdown
        category_totals: Dict[str, float] = {}
        for item in items:
            cat = item.category or "Uncategorized"
            category_totals[cat] = category_totals.get(cat, 0) + item.total_amount
        
        # Sort categories by spending
        top_categories = sorted(
            category_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # Monthly breakdown
        monthly_totals: Dict[str, float] = {}
        for item in items:
            month_key = item.date.strftime('%Y-%m')
            monthly_totals[month_key] = monthly_totals.get(month_key, 0) + item.total_amount
        
        return {
            'total_spending': total_spending,
            'receipt_spending': receipt_spending,
            'amazon_spending': amazon_spending,
            'receipt_count': receipt_count,
            'amazon_count': amazon_count,
            'total_transactions': len(items),
            'average_transaction': total_spending / len(items) if items else 0,
            'top_categories': top_categories,
            'monthly_totals': dict(sorted(monthly_totals.items())),
        }
    
    @staticmethod
    def get_spending_by_source(
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get spending breakdown by source."""
        items = SpendingAnalyzer.get_unified_spending(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )
        
        sources = {}
        for item in items:
            if item.source not in sources:
                sources[item.source] = {
                    'total': 0,
                    'count': 0,
                    'items': []
                }
            sources[item.source]['total'] += item.total_amount
            sources[item.source]['count'] += 1
            sources[item.source]['items'].append(item)
        
        return sources
