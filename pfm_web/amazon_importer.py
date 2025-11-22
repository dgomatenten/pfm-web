"""Amazon order CSV importer for loading order history into the database."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .extensions import db
from .models import AmazonOrder, AmazonOrderItem, Category


@dataclass
class AmazonImportResult:
    """Results of Amazon order import operation."""
    orders_created: int = 0
    orders_skipped: int = 0
    items_created: int = 0
    items_categorized: int = 0


def import_amazon_csv(csv_path: Path) -> AmazonImportResult:
    """
    Import Amazon order history CSV file.
    
    The CSV has one row per item, but multiple items can belong to the same order.
    We group by Order ID to create order-level records.
    
    Args:
        csv_path: Path to the Amazon Retail.OrderHistory.csv file
        
    Returns:
        AmazonImportResult with counts of created/skipped orders
    """
    result = AmazonImportResult()
    
    # Group items by Order ID
    orders_dict = _parse_csv_to_orders(csv_path)
    
    # Process each order
    for order_id, order_data in orders_dict.items():
        created = _upsert_amazon_order(order_id, order_data, result)
        if created:
            result.orders_created += 1
        else:
            result.orders_skipped += 1
    
    db.session.commit()
    return result


def _parse_csv_to_orders(csv_path: Path) -> dict[str, dict]:
    """
    Parse CSV and group items by Order ID.
    
    Returns:
        Dict mapping Order ID -> {order_fields, items: [item_dicts]}
    """
    orders: dict[str, dict] = defaultdict(lambda: {"items": []})
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            order_id = row['Order ID']
            
            # Skip cancelled orders with no items
            if row['Order Status'] == 'Cancelled' and row['Quantity'] == '0':
                continue
            
            # First time seeing this order - capture order-level data
            if not orders[order_id].get('order_date'):
                orders[order_id].update({
                    'order_date': row['Order Date'],
                    'currency': row['Currency'],
                    'payment_method': row['Payment Instrument Type'],
                    'order_status': row['Order Status'],
                    'shipment_status': row['Shipment Status'],
                    'ship_date': row.get('Ship Date'),
                    'shipping_address': row['Shipping Address'],
                    'total_owed': row['Total Owed'],
                })
            
            # Add item to this order
            item = _parse_item_from_row(row)
            if item:
                orders[order_id]['items'].append(item)
    
    return dict(orders)


def _parse_item_from_row(row: dict) -> Optional[dict]:
    """Extract item data from a CSV row."""
    try:
        # Skip rows where product name is empty or quantity is 0
        if not row.get('Product Name') or row.get('Quantity') == '0':
            return None
            
        quantity = float(row['Quantity']) if row['Quantity'] not in ('Not Available', '') else 1.0
        unit_price = float(row['Unit Price']) if row['Unit Price'] not in ('Not Available', '') else 0.0
        
        # Some rows have per-item prices, some don't
        if 'Shipment Item Subtotal' in row and row['Shipment Item Subtotal'] not in ('Not Available', ''):
            total_price = float(row['Shipment Item Subtotal'])
        else:
            total_price = unit_price * quantity
        
        return {
            'product_name': row['Product Name'],
            'asin': row.get('ASIN', ''),
            'quantity': quantity,
            'unit_price': unit_price,
            'total_price': total_price,
            'unit_price_tax': float(row['Unit Price Tax']) if row.get('Unit Price Tax') not in ('Not Available', '', '0', None) else 0.0,
            'product_condition': row.get('Product Condition', 'New'),
            'website': row.get('Website', 'Amazon.com'),
        }
    except (ValueError, KeyError, TypeError) as e:
        print(f"Warning: Could not parse item from row: {e} - Product: {row.get('Product Name', 'Unknown')[:50]}")
        return None


def _upsert_amazon_order(order_id: str, order_data: dict, result: AmazonImportResult) -> bool:
    """
    Create or update an Amazon order in the database.
    
    Returns:
        True if created, False if already existed
    """
    # Check if order already exists
    existing = AmazonOrder.query.filter_by(order_number=order_id).first()
    if existing:
        return False
    
    # Parse order date
    order_date = _parse_amazon_datetime(order_data['order_date'])
    
    # Calculate total from items (more accurate than Total Owed which may be aggregate)
    total_amount = sum(item['total_price'] for item in order_data['items'])
    
    # Create order
    order = AmazonOrder(
        order_number=order_id,
        order_date=order_date,
        total_amount=total_amount,
        currency=order_data['currency'],
        payment_method=order_data.get('payment_method'),
        shipment_status=order_data.get('shipment_status'),
        raw_payload=json.dumps(order_data, ensure_ascii=False),
    )
    
    # Add items with auto-categorization
    for item_data in order_data['items']:
        order_item = _create_order_item(item_data)
        order.items.append(order_item)
        result.items_created += 1
        
        if order_item.category_id:
            result.items_categorized += 1
    
    db.session.add(order)
    return True


def _create_order_item(item_data: dict) -> AmazonOrderItem:
    """Create an AmazonOrderItem with auto-categorization."""
    category = _auto_categorize_product(item_data['product_name'], item_data.get('asin'))
    
    return AmazonOrderItem(
        item_name=item_data['product_name'],
        asin=item_data.get('asin'),
        quantity=item_data['quantity'],
        unit_price=item_data['unit_price'],
        total_price=item_data['total_price'],
        category_id=category.id if category else None,
        metadata_json=json.dumps({
            'unit_price_tax': item_data.get('unit_price_tax'),
            'product_condition': item_data.get('product_condition'),
            'website': item_data.get('website'),
        }, ensure_ascii=False),
    )


def _auto_categorize_product(product_name: str, asin: Optional[str] = None) -> Optional[Category]:
    """
    Automatically categorize a product based on name and ASIN.
    
    Uses keyword matching to assign products to categories.
    Returns None if no good match is found.
    """
    product_lower = product_name.lower()
    
    # Category keyword rules (expand as needed)
    category_rules = {
        'Food & Beverages': [
            'coffee', 'tea', 'water', 'drink', 'beverage', 'snack', 'chip', 'cookie',
            'candy', 'chocolate', 'food', 'vitamin', 'supplement', 'protein', 'fiber',
            'honey', 'sauce', 'tuna', 'pasta', 'noodle', 'ramen', 'gum', 'lollipop',
            'sparkling', 'juice', 'latte', 'probiotic', 'prebiotic', 'gummy', 'gummies',
        ],
        'Health & Personal Care': [
            'toothpaste', 'toothbrush', 'dental', 'floss', 'mask', 'face', 'cream',
            'lotion', 'soap', 'shampoo', 'conditioner', 'skincare', 'makeup', 'cosmetic',
            'lip', 'balm', 'foundation', 'sunscreen', 'vitamin d', 'medicine', 'nyquil',
            'cough', 'throat', 'immune', 'health', 'cold & flu', 'scalp', 'hair care',
        ],
        'Home & Kitchen': [
            'kitchen', 'pan', 'cookware', 'cup', 'bottle', 'organizer', 'storage',
            'cart', 'trash bag', 'hanger', 'foam roller', 'power strip', 'grinder',
            'salt and pepper', 'dish soap', 'cleaning', 'cleanser', 'tofu press',
            'hose', 'garden', 'wood repair', 'epoxy',
        ],
        'Electronics': [
            'mouse', 'keyboard', 'laptop', 'usb', 'cable', 'charger', 'flash drive',
            'memory stick', 'fan', 'portable fan', 'led', 'light bulb', 'refrigerator light',
        ],
        'Office Supplies': [
            'pencil', 'pen', 'eraser', 'marker', 'sharpie', 'pouch', 'folder',
            'notebook', 'paper', 'stamp', 'sticker', 'school supplies',
        ],
        'Clothing & Accessories': [
            'underwear', 'bikini', 'hat', 'cap', 'visor', 'backpack', 'luggage',
            'suitcase', 'jewelry box',
        ],
        'Toys & Games': [
            'toy', 'camera', 'kids', 'plush', 'stuffed animal', 'slime', 'sticker',
        ],
        'Books': [
            'book', 'frindle', 'novel', 'reading',
        ],
    }
    
    # Find matching category
    for category_name, keywords in category_rules.items():
        if any(keyword in product_lower for keyword in keywords):
            category = Category.query.filter_by(name=category_name).first()
            if category:
                return category
            # Create category if it doesn't exist
            category = Category(name=category_name, type='expense')
            db.session.add(category)
            db.session.flush()  # Get ID without committing
            return category
    
    return None


def _parse_amazon_datetime(date_str: str) -> datetime:
    """Parse Amazon's ISO 8601 datetime format."""
    try:
        # Amazon uses: 2025-11-19T16:27:13Z
        return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        try:
            # Try with milliseconds: 2025-11-19T16:27:13.123Z
            return datetime.strptime(date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            # Fallback to current time if parsing fails
            print(f"Warning: Could not parse date '{date_str}', using current time")
            return datetime.utcnow()
