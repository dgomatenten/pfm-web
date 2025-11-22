# Amazon Order History Import - Documentation

## Overview

Added functionality to import Amazon order history CSV files into the PFM web application. The system automatically parses orders, extracts line items, and categorizes products using keyword-based rules.

## Database Schema

### Tables Created

**amazon_orders**
- `id`: Primary key
- `order_number`: Unique Amazon order ID (e.g., "111-9049276-7679434")
- `order_date`: Date order was placed
- `total_amount`: Total order amount (calculated from items)
- `currency`: Currency code (USD, etc.)
- `payment_method`: Payment method used
- `shipment_status`: Shipping status
- `raw_payload`: Full JSON of parsed CSV data
- `receipt_id`: Foreign key to receipts table (future integration)

**amazon_order_items**
- `id`: Primary key
- `amazon_order_id`: Foreign key to amazon_orders
- `item_name`: Product name
- `quantity`: Quantity purchased
- `unit_price`: Price per unit
- `total_price`: Total line item price
- `category_id`: Foreign key to categories (auto-categorized)
- `asin`: Amazon Standard Identification Number
- `seller`: Seller name (if applicable)
- `metadata_json`: Additional JSON data (tax, condition, etc.)

## Import Statistics

From the provided CSV file (Retail.OrderHistory.1.csv):
- **1,592 orders** imported
- **2,107 items** parsed
- **1,337 items** (63.5%) auto-categorized
- **$53,120.56** total spend

## Auto-Categorization System

Products are automatically categorized using keyword matching on product names:

### Categories and Keywords

1. **Food & Beverages** (543 items)
   - Keywords: coffee, tea, water, drink, snack, vitamin, supplement, honey, sauce, tuna, pasta, noodle, etc.

2. **Health & Personal Care** (235 items)
   - Keywords: toothpaste, dental, mask, face, cream, lotion, soap, makeup, vitamin, medicine, etc.

3. **Home & Kitchen** (180 items)
   - Keywords: kitchen, pan, cookware, bottle, organizer, trash bag, hanger, cleaning, etc.

4. **Electronics** (137 items)
   - Keywords: mouse, keyboard, usb, cable, charger, flash drive, fan, led, light bulb, etc.

5. **Office Supplies** (80 items)
   - Keywords: pencil, pen, eraser, marker, folder, notebook, stamp, sticker, etc.

6. **Toys & Games** (82 items)
   - Keywords: toy, camera, kids, plush, stuffed animal, slime, etc.

7. **Books** (43 items)
   - Keywords: book, novel, reading, etc.

8. **Clothing & Accessories** (37 items)
   - Keywords: underwear, hat, cap, backpack, luggage, jewelry box, etc.

## Usage

### Import Command

```bash
cd /home/dgoma/app_dev/pfm-web
./pfm/bin/python3 -m flask import-amazon data/Retail.OrderHistory.1.csv
```

Output:
```
Imported 1592 orders (2107 items, 1337 auto-categorized). Skipped 0 duplicates.
```

### Re-importing

The system uses `order_number` as a unique key. If you re-import the same CSV:
- Existing orders are skipped
- Duplicate prevention by Order ID

### CSV Format

Expected columns:
- `Order ID`: Unique identifier
- `Order Date`: ISO 8601 format (2025-11-19T16:27:13Z)
- `Product Name`: Full product name
- `ASIN`: Amazon product identifier
- `Quantity`: Number of items
- `Unit Price`: Price per item
- `Total Owed`: Order total
- `Currency`: USD, etc.
- `Payment Instrument Type`: Payment method
- `Order Status`: Closed, Authorized, Cancelled
- `Shipment Status`: Shipped, Not Available

## File Structure

```
pfm_web/
├── amazon_importer.py      # Main import logic
├── models.py               # AmazonOrder & AmazonOrderItem models
└── __init__.py             # Flask CLI command registration
```

## Implementation Details

### Order Grouping

Amazon CSV has **one row per item**, but multiple items can belong to one order:

```csv
Order ID,Product Name,Quantity,Unit Price
111-1234567-8901234,"Product A",1,10.00
111-1234567-8901234,"Product B",2,5.00
```

The importer groups by Order ID to create:
- 1 order record ($20.00 total)
- 2 item records

### Cancelled Orders

Orders with status "Cancelled" and quantity 0 are skipped.

### Missing Data Handling

- `Not Available` or empty fields default to 0 or null
- Unit prices calculated from `Shipment Item Subtotal` when available
- Fallback to `Unit Price * Quantity`

### Category Expansion

To add new categories or keywords, edit `amazon_importer.py`:

```python
category_rules = {
    'Food & Beverages': ['coffee', 'tea', 'water', ...],
    'Your New Category': ['keyword1', 'keyword2', ...],
    ...
}
```

## Query Examples

### Recent Orders

```python
from pfm_web.models import AmazonOrder

recent = AmazonOrder.query.order_by(
    AmazonOrder.order_date.desc()
).limit(10).all()
```

### Items by Category

```python
from pfm_web.models import AmazonOrderItem, Category

food_cat = Category.query.filter_by(name='Food & Beverages').first()
food_items = AmazonOrderItem.query.filter_by(category_id=food_cat.id).all()
```

### Monthly Spending

```python
from sqlalchemy import func, extract

monthly_spend = db.session.query(
    extract('year', AmazonOrder.order_date).label('year'),
    extract('month', AmazonOrder.order_date).label('month'),
    func.sum(AmazonOrder.total_amount).label('total')
).group_by('year', 'month').all()
```

### Uncategorized Items

```python
uncategorized = AmazonOrderItem.query.filter(
    AmazonOrderItem.category_id.is_(None)
).all()
```

## Future Enhancements

1. **Web UI for reviewing** categorizations
2. **Manual category assignment** for uncategorized items
3. **Category rules learning** from user corrections
4. **Receipt reconciliation** - link Amazon orders to scanned receipts
5. **Spending analytics** - charts by category, time period
6. **ASIN-based categorization** - use Amazon product database
7. **Seller tracking** - analyze purchases by seller/brand
8. **Return/refund tracking** - parse return orders

## Troubleshooting

### Tables Not Found

Run migrations:
```bash
./pfm/bin/python3 -m flask db upgrade
```

Or create tables manually:
```python
from pfm_web import create_app
from pfm_web.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
```

### Parse Warnings

If you see "Could not parse item" warnings, check CSV format:
- Ensure all required columns exist
- Check for encoding issues (should be UTF-8)
- Verify numeric fields don't have unexpected characters

### Duplicate Orders

If orders appear duplicated after re-import:
- Check database for existing data: `SELECT COUNT(*) FROM amazon_orders;`
- Clear data if needed (see "Re-importing" section above)

## Testing

Verify import success:

```bash
./pfm/bin/python3 << 'EOF'
from pfm_web import create_app
from pfm_web.models import AmazonOrder, AmazonOrderItem

app = create_app()
with app.app_context():
    print(f"Orders: {AmazonOrder.query.count()}")
    print(f"Items: {AmazonOrderItem.query.count()}")
    print(f"Categorized: {AmazonOrderItem.query.filter(AmazonOrderItem.category_id.isnot(None)).count()}")
EOF
```
