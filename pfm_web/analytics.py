"""Unified analytics combining receipts and Amazon orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Literal

from sqlalchemy import func, extract, case, union_all
from sqlalchemy.orm import aliased

from .extensions import db
from .models import (
    Receipt, ReceiptLineItem, AmazonOrder, AmazonOrderItem,
    Category, Shop
)

# Exchange rates to USD (base currency for all calculations)
EXCHANGE_RATES_TO_USD = {
    'USD': 1.0,
    'JPY': 1.0 / 149.50,  # 1 JPY = 0.00669 USD
    'EUR': 1.0 / 0.92,     # 1 EUR = 1.087 USD
    'GBP': 1.0 / 0.79,     # 1 GBP = 1.266 USD
    'CAD': 1.0 / 1.39,     # 1 CAD = 0.719 USD
    'AUD': 1.0 / 1.54,     # 1 AUD = 0.649 USD
    'CNY': 1.0 / 7.24,     # 1 CNY = 0.138 USD
    'INR': 1.0 / 83.12,    # 1 INR = 0.012 USD
}

def get_currency_case_expression(model_class, amount_field):
    """Create a CASE expression to convert amounts to USD."""
    return case(
        *[
            (model_class.currency == curr, amount_field * rate)
            for curr, rate in EXCHANGE_RATES_TO_USD.items()
        ],
        else_=amount_field  # Default to assuming USD if currency unknown
    )


@dataclass
class SpendingSummary:
    """Summary of spending across all sources."""
    total_amount: float
    transaction_count: int
    item_count: int
    avg_transaction: float
    date_range: tuple[datetime, datetime]
    by_source: dict[str, float]
    by_category: dict[str, float]


@dataclass
class CategoryBreakdown:
    """Spending breakdown by category."""
    category_name: str
    category_id: Optional[int]
    total_spent: float
    item_count: int
    transaction_count: int
    percentage: float
    avg_item_price: float


@dataclass
class TimeSeriesPoint:
    """Single point in time series data."""
    period: str  # e.g., "2025-11" or "2025-11-20"
    total_spent: float
    transaction_count: int
    receipt_total: float
    amazon_total: float


class UnifiedAnalytics:
    """Analytics engine combining receipts and Amazon orders."""
    
    @staticmethod
    def get_spending_summary(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[int] = None,
    ) -> SpendingSummary:
        """
        Get comprehensive spending summary across all sources.
        
        Args:
            start_date: Filter transactions from this date
            end_date: Filter transactions to this date
            user_id: Filter by user (for receipts)
            
        Returns:
            SpendingSummary with totals and breakdowns
        """
        # Receipt totals (convert all to USD)
        amount_in_usd = get_currency_case_expression(Receipt, Receipt.total_amount)
        receipt_query = db.session.query(
            func.sum(amount_in_usd).label('total'),
            func.count(Receipt.id).label('count'),
            func.coalesce(func.sum(
                db.session.query(func.count(ReceiptLineItem.id))
                .filter(ReceiptLineItem.receipt_id == Receipt.id)
                .correlate(Receipt)
                .scalar_subquery()
            ), 0).label('items')
        ).filter(Receipt.status != 'cancelled')
        
        if start_date:
            receipt_query = receipt_query.filter(Receipt.issued_at >= start_date)
        if end_date:
            receipt_query = receipt_query.filter(Receipt.issued_at <= end_date)
        if user_id:
            receipt_query = receipt_query.filter(Receipt.user_id == user_id)
        
        receipt_stats = receipt_query.first()
        
        # Amazon order totals (convert all to USD)
        amazon_amount_in_usd = get_currency_case_expression(AmazonOrder, AmazonOrder.total_amount)
        amazon_query = db.session.query(
            func.sum(amazon_amount_in_usd).label('total'),
            func.count(AmazonOrder.id).label('count'),
            func.coalesce(func.sum(
                db.session.query(func.count(AmazonOrderItem.id))
                .filter(AmazonOrderItem.amazon_order_id == AmazonOrder.id)
                .correlate(AmazonOrder)
                .scalar_subquery()
            ), 0).label('items')
        )
        
        if start_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date >= start_date)
        if end_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date <= end_date)
        
        amazon_stats = amazon_query.first()
        
        # Combine totals
        receipt_total = float(receipt_stats.total or 0)
        amazon_total = float(amazon_stats.total or 0)
        total_amount = receipt_total + amazon_total
        
        receipt_count = receipt_stats.count or 0
        amazon_count = amazon_stats.count or 0
        transaction_count = receipt_count + amazon_count
        
        item_count = (receipt_stats.items or 0) + (amazon_stats.items or 0)
        
        avg_transaction = total_amount / transaction_count if transaction_count > 0 else 0
        
        # Get date range
        receipt_dates = db.session.query(
            func.min(Receipt.issued_at),
            func.max(Receipt.issued_at)
        ).first()
        
        amazon_dates = db.session.query(
            func.min(AmazonOrder.order_date),
            func.max(AmazonOrder.order_date)
        ).first()
        
        min_date = min(d for d in [receipt_dates[0], amazon_dates[0]] if d)
        max_date = max(d for d in [receipt_dates[1], amazon_dates[1]] if d)
        
        # Category breakdown
        by_category = UnifiedAnalytics._get_category_totals(start_date, end_date, user_id)
        
        return SpendingSummary(
            total_amount=total_amount,
            transaction_count=transaction_count,
            item_count=item_count,
            avg_transaction=avg_transaction,
            date_range=(min_date, max_date),
            by_source={
                'receipts': receipt_total,
                'amazon': amazon_total,
            },
            by_category=by_category,
        )
    
    @staticmethod
    def _get_category_totals(
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        user_id: Optional[int],
    ) -> dict[str, float]:
        """Get spending totals by category."""
        # Receipt items by category
        receipt_items_query = db.session.query(
            Category.name,
            func.sum(ReceiptLineItem.total_price).label('total')
        ).join(
            ReceiptLineItem, Category.id == ReceiptLineItem.category_id
        ).join(
            Receipt, ReceiptLineItem.receipt_id == Receipt.id
        ).filter(
            Receipt.status != 'cancelled'
        )
        
        if start_date:
            receipt_items_query = receipt_items_query.filter(Receipt.issued_at >= start_date)
        if end_date:
            receipt_items_query = receipt_items_query.filter(Receipt.issued_at <= end_date)
        if user_id:
            receipt_items_query = receipt_items_query.filter(Receipt.user_id == user_id)
        
        receipt_items_query = receipt_items_query.group_by(Category.name)
        
        # Amazon items by category
        amazon_items_query = db.session.query(
            Category.name,
            func.sum(AmazonOrderItem.total_price).label('total')
        ).join(
            AmazonOrderItem, Category.id == AmazonOrderItem.category_id
        ).join(
            AmazonOrder, AmazonOrderItem.amazon_order_id == AmazonOrder.id
        )
        
        if start_date:
            amazon_items_query = amazon_items_query.filter(AmazonOrder.order_date >= start_date)
        if end_date:
            amazon_items_query = amazon_items_query.filter(AmazonOrder.order_date <= end_date)
        
        amazon_items_query = amazon_items_query.group_by(Category.name)
        
        # Combine results
        by_category = {}
        for name, total in receipt_items_query.all():
            by_category[name] = float(total or 0)
        
        for name, total in amazon_items_query.all():
            by_category[name] = by_category.get(name, 0) + float(total or 0)
        
        return by_category
    
    @staticmethod
    def get_category_breakdown(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[int] = None,
        limit: int = 20,
    ) -> list[CategoryBreakdown]:
        """
        Get detailed spending breakdown by category.
        
        Returns list sorted by total spent descending.
        """
        # Receipt items
        receipt_subquery = db.session.query(
            Category.id.label('category_id'),
            Category.name.label('category_name'),
            func.sum(ReceiptLineItem.total_price).label('total'),
            func.count(ReceiptLineItem.id).label('item_count'),
            func.count(func.distinct(Receipt.id)).label('transaction_count')
        ).join(
            ReceiptLineItem, Category.id == ReceiptLineItem.category_id
        ).join(
            Receipt, ReceiptLineItem.receipt_id == Receipt.id
        ).filter(
            Receipt.status != 'cancelled'
        )
        
        if start_date:
            receipt_subquery = receipt_subquery.filter(Receipt.issued_at >= start_date)
        if end_date:
            receipt_subquery = receipt_subquery.filter(Receipt.issued_at <= end_date)
        if user_id:
            receipt_subquery = receipt_subquery.filter(Receipt.user_id == user_id)
        
        receipt_subquery = receipt_subquery.group_by(Category.id, Category.name)
        
        # Amazon items
        amazon_subquery = db.session.query(
            Category.id.label('category_id'),
            Category.name.label('category_name'),
            func.sum(AmazonOrderItem.total_price).label('total'),
            func.count(AmazonOrderItem.id).label('item_count'),
            func.count(func.distinct(AmazonOrder.id)).label('transaction_count')
        ).join(
            AmazonOrderItem, Category.id == AmazonOrderItem.category_id
        ).join(
            AmazonOrder, AmazonOrderItem.amazon_order_id == AmazonOrder.id
        )
        
        if start_date:
            amazon_subquery = amazon_subquery.filter(AmazonOrder.order_date >= start_date)
        if end_date:
            amazon_subquery = amazon_subquery.filter(AmazonOrder.order_date <= end_date)
        
        amazon_subquery = amazon_subquery.group_by(Category.id, Category.name)
        
        # Combine results manually (SQLite doesn't support FULL OUTER JOIN)
        receipt_data = {row.category_id: row for row in receipt_subquery.all()}
        amazon_data = {row.category_id: row for row in amazon_subquery.all()}
        
        # Merge data
        all_category_ids = set(receipt_data.keys()) | set(amazon_data.keys())
        combined = []
        
        for cat_id in all_category_ids:
            receipt_row = receipt_data.get(cat_id)
            amazon_row = amazon_data.get(cat_id)
            
            category_name = receipt_row.category_name if receipt_row else amazon_row.category_name
            total_spent = (receipt_row.total if receipt_row else 0) + (amazon_row.total if amazon_row else 0)
            item_count = (receipt_row.item_count if receipt_row else 0) + (amazon_row.item_count if amazon_row else 0)
            transaction_count = (receipt_row.transaction_count if receipt_row else 0) + (amazon_row.transaction_count if amazon_row else 0)
            
            combined.append(type('obj', (object,), {
                'category_id': cat_id,
                'category_name': category_name,
                'total_spent': total_spent,
                'item_count': item_count,
                'transaction_count': transaction_count,
            })())
        
        # Sort by total spent descending
        combined.sort(key=lambda x: x.total_spent, reverse=True)
        combined = combined[:limit]
        
        # Calculate total for percentages
        total_spent = sum(row.total_spent for row in combined)
        
        return [
            CategoryBreakdown(
                category_name=row.category_name,
                category_id=row.category_id,
                total_spent=float(row.total_spent),
                item_count=row.item_count,
                transaction_count=row.transaction_count,
                percentage=(float(row.total_spent) / total_spent * 100) if total_spent > 0 else 0,
                avg_item_price=float(row.total_spent) / row.item_count if row.item_count > 0 else 0,
            )
            for row in combined
        ]
    
    @staticmethod
    def get_time_series(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        granularity: Literal['day', 'week', 'month', 'year'] = 'month',
        user_id: Optional[int] = None,
    ) -> list[TimeSeriesPoint]:
        """
        Get spending over time from both sources.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            granularity: Time bucket size (day, week, month, year)
            user_id: Filter by user (for receipts)
            
        Returns:
            List of TimeSeriesPoint objects sorted by period
        """
        # Default to last 12 months if no dates provided
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=365)
        
        # Build date format based on granularity
        if granularity == 'day':
            date_format = '%Y-%m-%d'
            receipt_period = func.date(Receipt.issued_at)
            amazon_period = func.date(AmazonOrder.order_date)
        elif granularity == 'week':
            date_format = '%Y-W%W'
            receipt_period = func.strftime('%Y-W%W', Receipt.issued_at)
            amazon_period = func.strftime('%Y-W%W', AmazonOrder.order_date)
        elif granularity == 'month':
            date_format = '%Y-%m'
            receipt_period = func.strftime('%Y-%m', Receipt.issued_at)
            amazon_period = func.strftime('%Y-%m', AmazonOrder.order_date)
        else:  # year
            date_format = '%Y'
            receipt_period = func.strftime('%Y', Receipt.issued_at)
            amazon_period = func.strftime('%Y', AmazonOrder.order_date)
        
        # Receipt time series
        receipt_series = db.session.query(
            receipt_period.label('period'),
            func.sum(Receipt.total_amount).label('total'),
            func.count(Receipt.id).label('count')
        ).filter(
            Receipt.status != 'cancelled',
            Receipt.issued_at >= start_date,
            Receipt.issued_at <= end_date
        )
        
        if user_id:
            receipt_series = receipt_series.filter(Receipt.user_id == user_id)
        
        receipt_series = receipt_series.group_by('period').all()
        
        # Amazon time series
        amazon_series = db.session.query(
            amazon_period.label('period'),
            func.sum(AmazonOrder.total_amount).label('total'),
            func.count(AmazonOrder.id).label('count')
        ).filter(
            AmazonOrder.order_date >= start_date,
            AmazonOrder.order_date <= end_date
        ).group_by('period').all()
        
        # Combine into dict
        periods = {}
        for row in receipt_series:
            periods[row.period] = {
                'receipt_total': float(row.total or 0),
                'receipt_count': row.count,
                'amazon_total': 0,
                'amazon_count': 0,
            }
        
        for row in amazon_series:
            if row.period not in periods:
                periods[row.period] = {
                    'receipt_total': 0,
                    'receipt_count': 0,
                    'amazon_total': float(row.total or 0),
                    'amazon_count': row.count,
                }
            else:
                periods[row.period]['amazon_total'] = float(row.total or 0)
                periods[row.period]['amazon_count'] = row.count
        
        # Convert to TimeSeriesPoint objects
        result = [
            TimeSeriesPoint(
                period=period,
                total_spent=data['receipt_total'] + data['amazon_total'],
                transaction_count=data['receipt_count'] + data['amazon_count'],
                receipt_total=data['receipt_total'],
                amazon_total=data['amazon_total'],
            )
            for period, data in sorted(periods.items())
        ]
        
        return result
    
    @staticmethod
    def get_top_merchants(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[int] = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get top merchants/shops by spending.
        
        Combines shops from receipts with Amazon as a virtual shop.
        """
        # Shop spending from receipts
        shop_query = db.session.query(
            Shop.name.label('merchant'),
            func.sum(Receipt.total_amount).label('total'),
            func.count(Receipt.id).label('transaction_count')
        ).join(
            Receipt, Shop.id == Receipt.shop_id
        ).filter(
            Receipt.status != 'cancelled'
        )
        
        if start_date:
            shop_query = shop_query.filter(Receipt.issued_at >= start_date)
        if end_date:
            shop_query = shop_query.filter(Receipt.issued_at <= end_date)
        if user_id:
            shop_query = shop_query.filter(Receipt.user_id == user_id)
        
        shop_query = shop_query.group_by(Shop.name)
        
        # Amazon total
        amazon_query = db.session.query(
            func.sum(AmazonOrder.total_amount).label('total'),
            func.count(AmazonOrder.id).label('transaction_count')
        )
        
        if start_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date >= start_date)
        if end_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date <= end_date)
        
        amazon_stats = amazon_query.first()
        
        # Combine results
        merchants = [
            {
                'merchant': row.merchant,
                'total_spent': float(row.total),
                'transaction_count': row.transaction_count,
                'avg_transaction': float(row.total) / row.transaction_count,
                'source': 'receipt',
            }
            for row in shop_query.all()
        ]
        
        if amazon_stats.total:
            merchants.append({
                'merchant': 'Amazon.com',
                'total_spent': float(amazon_stats.total),
                'transaction_count': amazon_stats.transaction_count,
                'avg_transaction': float(amazon_stats.total) / amazon_stats.transaction_count,
                'source': 'amazon',
            })
        
        # Sort by total spent
        merchants.sort(key=lambda x: x['total_spent'], reverse=True)
        
        return merchants[:limit]
    
    @staticmethod
    def compare_sources(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[int] = None,
    ) -> dict:
        """
        Compare receipts vs Amazon orders.
        
        Returns metrics for each source side-by-side.
        """
        # Receipt metrics (convert to USD)
        amount_in_usd = get_currency_case_expression(Receipt, Receipt.total_amount)
        receipt_query = db.session.query(
            func.sum(amount_in_usd).label('total'),
            func.count(Receipt.id).label('count'),
            func.avg(amount_in_usd).label('avg')
        ).filter(Receipt.status != 'cancelled')
        
        if start_date:
            receipt_query = receipt_query.filter(Receipt.issued_at >= start_date)
        if end_date:
            receipt_query = receipt_query.filter(Receipt.issued_at <= end_date)
        if user_id:
            receipt_query = receipt_query.filter(Receipt.user_id == user_id)
        
        receipt_stats = receipt_query.first()
        
        # Amazon metrics (convert to USD)
        amazon_amount_in_usd = get_currency_case_expression(AmazonOrder, AmazonOrder.total_amount)
        amazon_query = db.session.query(
            func.sum(amazon_amount_in_usd).label('total'),
            func.count(AmazonOrder.id).label('count'),
            func.avg(amazon_amount_in_usd).label('avg')
        )
        
        if start_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date >= start_date)
        if end_date:
            amazon_query = amazon_query.filter(AmazonOrder.order_date <= end_date)
        
        amazon_stats = amazon_query.first()
        
        receipt_total = float(receipt_stats.total or 0)
        amazon_total = float(amazon_stats.total or 0)
        combined_total = receipt_total + amazon_total
        
        return {
            'receipts': {
                'total': receipt_total,
                'count': receipt_stats.count or 0,
                'avg_transaction': float(receipt_stats.avg or 0),
                'percentage': (receipt_total / combined_total * 100) if combined_total > 0 else 0,
            },
            'amazon': {
                'total': amazon_total,
                'count': amazon_stats.count or 0,
                'avg_transaction': float(amazon_stats.avg or 0),
                'percentage': (amazon_total / combined_total * 100) if combined_total > 0 else 0,
            },
            'combined': {
                'total': combined_total,
                'count': (receipt_stats.count or 0) + (amazon_stats.count or 0),
            },
        }
