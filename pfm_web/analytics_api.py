"""API endpoints for unified analytics."""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

from .analytics import UnifiedAnalytics
from .extensions import db

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

# Exchange rates (USD base)
EXCHANGE_RATES = {
    'USD': 1.0,
    'EUR': 0.92,
    'GBP': 0.79,
    'JPY': 149.50,
    'CAD': 1.39,
    'AUD': 1.54,
    'CNY': 7.24,
    'INR': 83.12
}

def convert_currency(amount, to_currency='USD'):
    """Convert USD amount to target currency."""
    if to_currency == 'USD' or to_currency not in EXCHANGE_RATES:
        return amount
    return amount * EXCHANGE_RATES[to_currency]

def convert_dict_amounts(data, currency='USD'):
    """Recursively convert monetary amounts in a dictionary."""
    if currency == 'USD':
        return data
    
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in ('total_amount', 'total_spent', 'avg_transaction', 'avg_item_price', 
                      'total', 'receipt_total', 'amazon_total'):
                result[key] = convert_currency(value, currency) if value else value
            elif isinstance(value, (dict, list)):
                result[key] = convert_dict_amounts(value, currency)
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        return [convert_dict_amounts(item, currency) for item in data]
    else:
        return data


@analytics_bp.route('/summary', methods=['GET'])
def get_summary():
    """
    Get spending summary across all sources.
    
    Query params:
        - days: Number of days to look back (default: 30)
        - start_date: YYYY-MM-DD (overrides days param)
        - end_date: YYYY-MM-DD (default: today)
        - currency: Target currency (default: USD)
        - user_id: User ID filter (optional)
    """
    # Parse dates
    end_date = datetime.now()
    days = request.args.get('days', type=int, default=30)
    start_date = end_date - timedelta(days=days)
    
    if start_str := request.args.get('start_date'):
        start_date = datetime.fromisoformat(start_str)
    if end_str := request.args.get('end_date'):
        end_date = datetime.fromisoformat(end_str)
    
    user_id = request.args.get('user_id', type=int)
    currency = request.args.get('currency', 'USD').upper()
    
    summary = UnifiedAnalytics.get_spending_summary(start_date, end_date, user_id)
    
    response = {
        'total_amount': summary.total_amount,
        'transaction_count': summary.transaction_count,
        'item_count': summary.item_count,
        'avg_transaction': summary.avg_transaction,
        'date_range': {
            'start': summary.date_range[0].isoformat() if summary.date_range[0] else None,
            'end': summary.date_range[1].isoformat() if summary.date_range[1] else None,
        },
        'by_source': summary.by_source,
        'by_category': summary.by_category,
        'currency': currency
    }
    
    return jsonify(convert_dict_amounts(response, currency))


@analytics_bp.route('/categories', methods=['GET'])
def get_category_breakdown():
    """
    Get detailed category breakdown.
    
    Query params:
        - days: Number of days to look back (default: 30)
        - start_date: YYYY-MM-DD (overrides days param)
        - end_date: YYYY-MM-DD (default: today)
        - currency: Target currency (default: USD)
        - user_id: User ID filter (optional)
        - limit: Max categories (default: 20)
    """
    end_date = datetime.now()
    days = request.args.get('days', type=int, default=30)
    start_date = end_date - timedelta(days=days)
    
    if start_str := request.args.get('start_date'):
        start_date = datetime.fromisoformat(start_str)
    if end_str := request.args.get('end_date'):
        end_date = datetime.fromisoformat(end_str)
    
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', type=int, default=20)
    currency = request.args.get('currency', 'USD').upper()
    
    breakdown = UnifiedAnalytics.get_category_breakdown(
        start_date, end_date, user_id, limit
    )
    
    response = {
        'categories': [
            {
                'category_name': cat.category_name,
                'category_id': cat.category_id,
                'total_spent': cat.total_spent,
                'item_count': cat.item_count,
                'transaction_count': cat.transaction_count,
                'percentage': cat.percentage,
                'avg_item_price': cat.avg_item_price,
            }
            for cat in breakdown
        ],
        'currency': currency
    }
    
    return jsonify(convert_dict_amounts(response, currency))


@analytics_bp.route('/time-series', methods=['GET'])
def get_time_series():
    """
    Get spending over time.
    
    Query params:
        - days: Number of days to look back (default: 365)
        - start_date: YYYY-MM-DD (overrides days param)
        - end_date: YYYY-MM-DD (default: today)
        - group_by: day|week|month|year (default: month)
        - granularity: day|week|month|year (alias for group_by)
        - currency: Target currency (default: USD)
        - user_id: User ID filter (optional)
    """
    end_date = datetime.now()
    days = request.args.get('days', type=int, default=365)
    start_date = end_date - timedelta(days=days)
    
    if start_str := request.args.get('start_date'):
        start_date = datetime.fromisoformat(start_str)
    if end_str := request.args.get('end_date'):
        end_date = datetime.fromisoformat(end_str)
    
    granularity = request.args.get('group_by') or request.args.get('granularity', 'month')
    user_id = request.args.get('user_id', type=int)
    currency = request.args.get('currency', 'USD').upper()
    
    series = UnifiedAnalytics.get_time_series(
        start_date, end_date, granularity, user_id
    )
    
    response = {
        'granularity': granularity,
        'currency': currency,
        'data': [
            {
                'period': point.period,
                'total_spent': point.total_spent,
                'transaction_count': point.transaction_count,
                'receipt_total': point.receipt_total,
                'amazon_total': point.amazon_total,
            }
            for point in series
        ]
    }
    
    return jsonify(convert_dict_amounts(response, currency))


@analytics_bp.route('/merchants', methods=['GET'])
def get_top_merchants():
    """
    Get top merchants by spending.
    
    Query params:
        - start_date: YYYY-MM-DD (default: 30 days ago)
        - end_date: YYYY-MM-DD (default: today)
        - user_id: User ID filter (optional)
        - limit: Max merchants (default: 20)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    if start_str := request.args.get('start_date'):
        start_date = datetime.fromisoformat(start_str)
    if end_str := request.args.get('end_date'):
        end_date = datetime.fromisoformat(end_str)
    
    user_id = request.args.get('user_id', type=int)
    limit = request.args.get('limit', type=int, default=20)
    
    merchants = UnifiedAnalytics.get_top_merchants(
        start_date, end_date, user_id, limit
    )
    
    return jsonify({'merchants': merchants})


@analytics_bp.route('/compare-sources', methods=['GET'])
def compare_sources():
    """
    Compare receipts vs Amazon orders.
    
    Query params:
        - days: Number of days to look back (default: 30)
        - start_date: YYYY-MM-DD (overrides days param)
        - end_date: YYYY-MM-DD (default: today)
        - currency: Target currency (default: USD)
        - user_id: User ID filter (optional)
    """
    end_date = datetime.now()
    days = request.args.get('days', type=int, default=30)
    start_date = end_date - timedelta(days=days)
    
    if start_str := request.args.get('start_date'):
        start_date = datetime.fromisoformat(start_str)
    if end_str := request.args.get('end_date'):
        end_date = datetime.fromisoformat(end_str)
    
    user_id = request.args.get('user_id', type=int)
    currency = request.args.get('currency', 'USD').upper()
    
    comparison = UnifiedAnalytics.compare_sources(start_date, end_date, user_id)
    comparison['currency'] = currency
    
    return jsonify(convert_dict_amounts(comparison, currency))


@analytics_bp.route('/monthly-trends', methods=['GET'])
def get_monthly_trends():
    """
    Get monthly spending trends for the last 12 months.
    
    Query params:
        - user_id: User ID filter (optional)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    user_id = request.args.get('user_id', type=int)
    
    series = UnifiedAnalytics.get_time_series(
        start_date, end_date, 'month', user_id
    )
    
    # Calculate trends
    if len(series) >= 2:
        recent_avg = sum(p.total_spent for p in series[-3:]) / 3
        previous_avg = sum(p.total_spent for p in series[-6:-3]) / 3 if len(series) >= 6 else recent_avg
        trend_direction = 'up' if recent_avg > previous_avg else 'down' if recent_avg < previous_avg else 'stable'
        trend_percentage = ((recent_avg - previous_avg) / previous_avg * 100) if previous_avg > 0 else 0
    else:
        trend_direction = 'unknown'
        trend_percentage = 0
    
    return jsonify({
        'months': [
            {
                'period': point.period,
                'total_spent': point.total_spent,
                'transaction_count': point.transaction_count,
                'receipt_total': point.receipt_total,
                'amazon_total': point.amazon_total,
            }
            for point in series
        ],
        'trend': {
            'direction': trend_direction,
            'percentage': trend_percentage,
        }
    })
