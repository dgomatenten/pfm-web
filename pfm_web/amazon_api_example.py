"""Example API endpoints for Amazon order integration."""

# Add these to pfm_web/api.py or create a new blueprint

from flask import Blueprint, jsonify, request
from sqlalchemy import func, extract
from datetime import datetime

from .models import AmazonOrder, AmazonOrderItem, Category
from .extensions import db

amazon_bp = Blueprint('amazon', __name__, url_prefix='/api/amazon')


@amazon_bp.route('/orders', methods=['GET'])
def list_orders():
    """
    List all Amazon orders with optional filters.
    
    Query params:
        - start_date: Filter orders from this date (YYYY-MM-DD)
        - end_date: Filter orders to this date (YYYY-MM-DD)
        - limit: Max results (default 100)
        - offset: Pagination offset
    """
    query = AmazonOrder.query
    
    # Date filters
    if start_date := request.args.get('start_date'):
        query = query.filter(AmazonOrder.order_date >= datetime.fromisoformat(start_date))
    if end_date := request.args.get('end_date'):
        query = query.filter(AmazonOrder.order_date <= datetime.fromisoformat(end_date))
    
    # Pagination
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    
    orders = query.order_by(AmazonOrder.order_date.desc()).limit(limit).offset(offset).all()
    
    return jsonify({
        'orders': [
            {
                'id': o.id,
                'order_number': o.order_number,
                'order_date': o.order_date.isoformat(),
                'total_amount': o.total_amount,
                'currency': o.currency,
                'item_count': len(o.items),
                'items': [
                    {
                        'name': item.item_name,
                        'quantity': item.quantity,
                        'price': item.total_price,
                        'category': item.category.name if item.category else None,
                    }
                    for item in o.items
                ]
            }
            for o in orders
        ],
        'count': len(orders),
        'limit': limit,
        'offset': offset,
    })


@amazon_bp.route('/orders/<order_number>', methods=['GET'])
def get_order(order_number: str):
    """Get details of a specific order."""
    order = AmazonOrder.query.filter_by(order_number=order_number).first_or_404()
    
    return jsonify({
        'order_number': order.order_number,
        'order_date': order.order_date.isoformat(),
        'total_amount': order.total_amount,
        'currency': order.currency,
        'payment_method': order.payment_method,
        'shipment_status': order.shipment_status,
        'items': [
            {
                'id': item.id,
                'name': item.item_name,
                'asin': item.asin,
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'total_price': item.total_price,
                'category_id': item.category_id,
                'category_name': item.category.name if item.category else None,
            }
            for item in order.items
        ],
    })


@amazon_bp.route('/items/<int:item_id>/categorize', methods=['PUT'])
def categorize_item(item_id: int):
    """
    Manually assign category to an item.
    
    Body:
        {"category_id": 5}
    """
    item = AmazonOrderItem.query.get_or_404(item_id)
    data = request.get_json()
    
    category_id = data.get('category_id')
    if category_id:
        category = Category.query.get_or_404(category_id)
        item.category_id = category.id
    else:
        item.category_id = None
    
    db.session.commit()
    
    return jsonify({
        'item_id': item.id,
        'category_id': item.category_id,
        'category_name': item.category.name if item.category else None,
    })


@amazon_bp.route('/stats/spending', methods=['GET'])
def spending_stats():
    """
    Get spending statistics.
    
    Query params:
        - group_by: 'month', 'category', 'year' (default: month)
        - year: Filter by year
    """
    group_by = request.args.get('group_by', 'month')
    year = request.args.get('year')
    
    query = db.session.query(AmazonOrder)
    if year:
        query = query.filter(extract('year', AmazonOrder.order_date) == int(year))
    
    if group_by == 'month':
        results = db.session.query(
            extract('year', AmazonOrder.order_date).label('year'),
            extract('month', AmazonOrder.order_date).label('month'),
            func.sum(AmazonOrder.total_amount).label('total'),
            func.count(AmazonOrder.id).label('order_count')
        ).group_by('year', 'month').order_by('year', 'month').all()
        
        return jsonify({
            'group_by': 'month',
            'data': [
                {
                    'year': int(r.year),
                    'month': int(r.month),
                    'total': float(r.total),
                    'order_count': r.order_count,
                }
                for r in results
            ]
        })
    
    elif group_by == 'category':
        results = db.session.query(
            Category.name,
            func.sum(AmazonOrderItem.total_price).label('total'),
            func.count(AmazonOrderItem.id).label('item_count')
        ).join(
            AmazonOrderItem, Category.id == AmazonOrderItem.category_id
        ).group_by(
            Category.name
        ).order_by(
            func.sum(AmazonOrderItem.total_price).desc()
        ).all()
        
        return jsonify({
            'group_by': 'category',
            'data': [
                {
                    'category': r.name,
                    'total': float(r.total),
                    'item_count': r.item_count,
                }
                for r in results
            ]
        })
    
    elif group_by == 'year':
        results = db.session.query(
            extract('year', AmazonOrder.order_date).label('year'),
            func.sum(AmazonOrder.total_amount).label('total'),
            func.count(AmazonOrder.id).label('order_count')
        ).group_by('year').order_by('year').all()
        
        return jsonify({
            'group_by': 'year',
            'data': [
                {
                    'year': int(r.year),
                    'total': float(r.total),
                    'order_count': r.order_count,
                }
                for r in results
            ]
        })
    
    return jsonify({'error': 'Invalid group_by parameter'}), 400


@amazon_bp.route('/stats/uncategorized', methods=['GET'])
def uncategorized_items():
    """Get list of items that haven't been categorized."""
    items = AmazonOrderItem.query.filter(
        AmazonOrderItem.category_id.is_(None)
    ).order_by(
        AmazonOrderItem.total_price.desc()
    ).limit(100).all()
    
    return jsonify({
        'count': AmazonOrderItem.query.filter(AmazonOrderItem.category_id.is_(None)).count(),
        'items': [
            {
                'id': item.id,
                'name': item.item_name,
                'asin': item.asin,
                'price': item.total_price,
                'order_number': item.order.order_number,
                'order_date': item.order.order_date.isoformat(),
            }
            for item in items
        ]
    })


@amazon_bp.route('/stats/top-products', methods=['GET'])
def top_products():
    """
    Get top products by spending.
    
    Query params:
        - category_id: Filter by category
        - limit: Max results (default 20)
    """
    query = db.session.query(
        AmazonOrderItem.item_name,
        AmazonOrderItem.asin,
        func.sum(AmazonOrderItem.total_price).label('total_spent'),
        func.sum(AmazonOrderItem.quantity).label('total_quantity'),
        func.count(AmazonOrderItem.id).label('purchase_count')
    ).group_by(
        AmazonOrderItem.item_name,
        AmazonOrderItem.asin
    )
    
    if category_id := request.args.get('category_id'):
        query = query.filter(AmazonOrderItem.category_id == int(category_id))
    
    limit = int(request.args.get('limit', 20))
    results = query.order_by(func.sum(AmazonOrderItem.total_price).desc()).limit(limit).all()
    
    return jsonify({
        'products': [
            {
                'name': r.item_name,
                'asin': r.asin,
                'total_spent': float(r.total_spent),
                'total_quantity': float(r.total_quantity),
                'purchase_count': r.purchase_count,
            }
            for r in results
        ]
    })


# Register blueprint in pfm_web/__init__.py:
# from .amazon_api import amazon_bp
# app.register_blueprint(amazon_bp)
