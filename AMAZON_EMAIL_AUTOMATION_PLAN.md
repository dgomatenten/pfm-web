# Amazon Order Email Automation - Design & Implementation Plan

## Executive Summary

Automate the retrieval and processing of Amazon order confirmation emails from Gmail to automatically populate Amazon order data in pfm_web without manual CSV uploads.

---

## 1. System Architecture Overview

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌──────────────┐
│   Gmail     │─────▶│  Email       │─────▶│   Amazon    │─────▶│   Database   │
│   Inbox     │ IMAP │  Fetcher     │ Parse│   Order     │ Save │   (SQLite)   │
│             │      │  Service     │      │   Parser    │      │              │
└─────────────┘      └──────────────┘      └─────────────┘      └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  Scheduler   │
                     │  (Cron/APSch)│
                     └──────────────┘
```

### Components:

1. **Email Fetcher Service**: Connect to Gmail via IMAP, search for Amazon emails
2. **Email Parser**: Extract order details from HTML/text email body
3. **Order Normalizer**: Convert email data to standardized order format
4. **Database Writer**: Insert/update orders in existing schema
5. **Scheduler**: Run periodic syncs (hourly/daily)
6. **Configuration Manager**: Store Gmail credentials securely

---

## 2. Technology Stack

### Core Libraries:
- **IMAP Client**: `imaplib` (built-in) or `imap-tools` (enhanced)
- **Email Parsing**: `email` module (built-in) + `BeautifulSoup4` for HTML parsing
- **Scheduler**: `APScheduler` (Flask-compatible) or systemd timer
- **Secrets Management**: Flask config + environment variables, or `python-keyring`
- **OAuth2**: `google-auth` + `google-auth-oauthlib` for Gmail API (preferred over App Passwords)

### Security:
- OAuth2 tokens stored encrypted in database or secure file
- No plaintext passwords
- Read-only Gmail access (no send/delete permissions)

---

## 3. Email Identification Strategy

### Amazon Order Email Patterns:

#### Subject Lines:
```
"Your Amazon.com order of [Product Name] has shipped"
"Your Amazon.com order #123-4567890-1234567"
"Order Confirmation #123-4567890-1234567"
"Shipping Confirmation for Order #123-4567890-1234567"
```

#### From Addresses:
```
auto-confirm@amazon.com
ship-confirm@amazon.com
order-update@amazon.com
```

#### Email Body Markers:
- Contains: "Order #" or "Order Number:"
- Contains: "Order Date:" or "Placed on"
- Contains: "Order Total:" or "Grand Total:"
- Contains Amazon logo/branding
- HTML table with item details

---

## 4. Data Extraction Strategy

### Email Types to Process:

1. **Order Confirmation Email**
   - Order ID
   - Order date
   - Items (name, quantity, price)
   - Shipping address
   - Payment method (last 4 digits)
   - Order total

2. **Shipping Confirmation Email**
   - Shipment date
   - Tracking number
   - Estimated delivery
   - Update existing order status

### Parsing Approach:

#### Method A: HTML Parsing (Primary)
```python
from bs4 import BeautifulSoup

def parse_order_email(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find order number
    order_num = soup.find(text=re.compile(r'Order #')).parent.text
    
    # Find order date
    order_date = soup.find(text=re.compile(r'Order Date:')).parent.text
    
    # Find items table
    items_table = soup.find('table', class_='items')
    items = []
    for row in items_table.find_all('tr')[1:]:
        cols = row.find_all('td')
        items.append({
            'name': cols[0].text.strip(),
            'quantity': int(cols[1].text.strip()),
            'price': parse_price(cols[2].text.strip())
        })
    
    return {
        'order_id': clean_order_id(order_num),
        'order_date': parse_date(order_date),
        'items': items,
        'total': find_total(soup)
    }
```

#### Method B: Text Pattern Matching (Fallback)
```python
import re

def parse_text_email(text_content):
    order_id_match = re.search(r'Order #?(\d{3}-\d{7}-\d{7})', text_content)
    date_match = re.search(r'Order Date:?\s*(\w+ \d+, \d{4})', text_content)
    total_match = re.search(r'Order Total:?\s*\$?([\d,]+\.\d{2})', text_content)
    
    return {
        'order_id': order_id_match.group(1) if order_id_match else None,
        'order_date': date_match.group(1) if date_match else None,
        'total': float(total_match.group(1).replace(',', '')) if total_match else None
    }
```

---

## 5. Database Schema Updates

### New Table: `email_sync_config`
```sql
CREATE TABLE email_sync_config (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    email_provider VARCHAR(50) NOT NULL DEFAULT 'gmail',
    email_address VARCHAR(255) NOT NULL,
    oauth_token_encrypted TEXT,  -- Encrypted OAuth2 refresh token
    last_sync_date DATETIME,
    sync_enabled BOOLEAN DEFAULT TRUE,
    sync_frequency_hours INTEGER DEFAULT 24,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### New Table: `email_processing_log`
```sql
CREATE TABLE email_processing_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    email_message_id VARCHAR(255) NOT NULL,  -- Gmail Message-ID
    email_subject TEXT,
    email_date DATETIME,
    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processing_status VARCHAR(50),  -- 'success', 'failed', 'skipped'
    amazon_order_id INTEGER,  -- FK to amazon_orders if created
    error_message TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (amazon_order_id) REFERENCES amazon_orders(id),
    UNIQUE(email_message_id)  -- Prevent reprocessing same email
);
```

### Update Existing Table: `amazon_orders`
```sql
-- Add new columns to track email source
ALTER TABLE amazon_orders ADD COLUMN source_type VARCHAR(50) DEFAULT 'csv';  -- 'csv', 'email', 'api'
ALTER TABLE amazon_orders ADD COLUMN email_message_id VARCHAR(255);  -- Link to source email
ALTER TABLE amazon_orders ADD COLUMN raw_email_html TEXT;  -- Store original email for debugging
```

---

## 6. Gmail API Setup (OAuth2 Method - RECOMMENDED)

### Step 1: Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project: "PFM-Amazon-Sync"
3. Enable Gmail API:
   - Navigate to "APIs & Services" > "Library"
   - Search "Gmail API"
   - Click "Enable"

4. Create OAuth2 Credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client ID"
   - Application type: "Desktop app" or "Web application"
   - Note down:
     - Client ID: `xxxxx.apps.googleusercontent.com`
     - Client Secret: `xxxxxxxxxxxxxx`

5. Configure OAuth Consent Screen:
   - User Type: External (for personal use)
   - Add scopes: `https://www.googleapis.com/auth/gmail.readonly`
   - Add test users: your email address

### Step 2: Initial Token Generation

```python
# scripts/generate_gmail_token.py
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def generate_token():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json',  # Downloaded from Google Cloud Console
        SCOPES
    )
    creds = flow.run_local_server(port=0)
    
    # Save token for later use
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)
    
    print("✅ Token generated successfully!")
    print(f"Refresh token: {creds.refresh_token}")

if __name__ == '__main__':
    generate_token()
```

### Step 3: Flask Configuration

```python
# pfm_web/config.py
class Config:
    # Gmail OAuth2
    GMAIL_CLIENT_ID = os.getenv('GMAIL_CLIENT_ID')
    GMAIL_CLIENT_SECRET = os.getenv('GMAIL_CLIENT_SECRET')
    GMAIL_TOKEN_FILE = os.getenv('GMAIL_TOKEN_FILE', 'data/gmail_token.pickle')
    
    # Email sync settings
    EMAIL_SYNC_ENABLED = os.getenv('EMAIL_SYNC_ENABLED', 'False') == 'True'
    EMAIL_SYNC_INTERVAL_HOURS = int(os.getenv('EMAIL_SYNC_INTERVAL_HOURS', '24'))
```

### Step 4: Environment Variables

```bash
# .env
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_TOKEN_FILE=data/gmail_token.pickle
EMAIL_SYNC_ENABLED=True
EMAIL_SYNC_INTERVAL_HOURS=24
```

---

## 7. IMAP Method (Alternative - Simpler but Less Secure)

### Enable Gmail App Password:

1. Go to Google Account Settings
2. Security > 2-Step Verification (must be enabled)
3. App Passwords > Generate
4. Select "Mail" and "Other (Custom name)"
5. Copy 16-character password

### Configuration:

```python
# .env
GMAIL_EMAIL=your-email@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop  # 16-char app password
EMAIL_SYNC_METHOD=imap  # or 'oauth2'
```

---

## 8. Implementation Files Structure

```
pfm-web/
├── pfm_web/
│   ├── services/
│   │   ├── email_sync/
│   │   │   ├── __init__.py
│   │   │   ├── gmail_client.py         # Gmail API/IMAP wrapper
│   │   │   ├── email_parser.py         # Parse Amazon emails
│   │   │   ├── order_extractor.py      # Extract order data
│   │   │   ├── sync_service.py         # Orchestration
│   │   │   └── scheduler.py            # Background job setup
│   │   └── encryption.py               # Token encryption utilities
│   ├── migrations/
│   │   └── versions/
│   │       └── xxxx_add_email_sync_tables.py
│   └── cli/
│       └── email_sync_commands.py      # Flask CLI commands
├── scripts/
│   ├── generate_gmail_token.py         # One-time OAuth setup
│   └── test_email_parser.py            # Parse sample emails
├── tests/
│   ├── test_email_parser.py
│   └── fixtures/
│       └── sample_amazon_email.html
└── data/
    ├── gmail_token.pickle              # OAuth tokens (gitignored)
    └── sample_emails/                  # Test emails (gitignored)
```

---

## 9. Core Implementation: Email Sync Service

### File: `pfm_web/services/email_sync/gmail_client.py`

```python
"""Gmail client using OAuth2 or IMAP."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GmailClient:
    """Gmail API client with OAuth2 authentication."""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, token_file: Path):
        self.token_file = token_file
        self.creds = self._load_credentials()
        self.service = build('gmail', 'v1', credentials=self.creds)
    
    def _load_credentials(self) -> Credentials:
        """Load and refresh OAuth2 credentials."""
        if not self.token_file.exists():
            raise FileNotFoundError(f"Token file not found: {self.token_file}")
        
        with open(self.token_file, 'rb') as token:
            creds = pickle.load(token)
        
        # Refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return creds
    
    def search_amazon_emails(
        self, 
        after_date: str = None,
        max_results: int = 100
    ) -> Iterator[dict]:
        """
        Search for Amazon order emails.
        
        Args:
            after_date: ISO date string (e.g., '2025/12/01')
            max_results: Maximum emails to return
            
        Yields:
            Email message dicts with id, subject, date, body
        """
        query_parts = [
            'from:(auto-confirm@amazon.com OR ship-confirm@amazon.com)',
            'subject:(order OR shipped)',
        ]
        
        if after_date:
            query_parts.append(f'after:{after_date}')
        
        query = ' '.join(query_parts)
        
        # Search messages
        results = self.service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        for message_ref in messages:
            # Fetch full message
            msg = self.service.users().messages().get(
                userId='me',
                id=message_ref['id'],
                format='full'
            ).execute()
            
            yield self._parse_message(msg)
    
    def _parse_message(self, msg: dict) -> dict:
        """Parse Gmail API message into simplified dict."""
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        
        # Extract body
        body_html = None
        body_text = None
        
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/html':
                    body_html = self._decode_body(part['body']['data'])
                elif part['mimeType'] == 'text/plain':
                    body_text = self._decode_body(part['body']['data'])
        else:
            # Single part message
            body_data = msg['payload']['body'].get('data')
            if body_data:
                body_html = self._decode_body(body_data)
        
        return {
            'id': msg['id'],
            'message_id': headers.get('Message-ID'),
            'subject': headers.get('Subject'),
            'from': headers.get('From'),
            'date': headers.get('Date'),
            'body_html': body_html,
            'body_text': body_text,
        }
    
    @staticmethod
    def _decode_body(data: str) -> str:
        """Decode base64url encoded message body."""
        import base64
        return base64.urlsafe_b64decode(data).decode('utf-8')
```

---

### File: `pfm_web/services/email_sync/email_parser.py`

```python
"""Parse Amazon order data from email HTML/text."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup


@dataclass
class ParsedOrderItem:
    """Parsed item from email."""
    name: str
    quantity: int
    price: float
    asin: Optional[str] = None


@dataclass
class ParsedAmazonOrder:
    """Parsed order from email."""
    order_id: str
    order_date: datetime
    items: list[ParsedOrderItem]
    total_amount: float
    currency: str = 'USD'
    shipment_status: Optional[str] = None
    tracking_number: Optional[str] = None


class AmazonEmailParser:
    """Parse Amazon confirmation emails."""
    
    ORDER_ID_PATTERN = re.compile(r'Order\s*#?\s*(\d{3}-\d{7}-\d{7})')
    DATE_PATTERN = re.compile(r'Order\s+Date:?\s*(\w+\s+\d+,\s+\d{4})')
    PRICE_PATTERN = re.compile(r'\$?([\d,]+\.\d{2})')
    
    def parse_email(self, email_html: str, email_text: str = None) -> Optional[ParsedAmazonOrder]:
        """
        Parse Amazon order email.
        
        Args:
            email_html: HTML body of email
            email_text: Plain text body (fallback)
            
        Returns:
            ParsedAmazonOrder or None if parsing fails
        """
        if email_html:
            return self._parse_html(email_html)
        elif email_text:
            return self._parse_text(email_text)
        return None
    
    def _parse_html(self, html: str) -> Optional[ParsedAmazonOrder]:
        """Parse HTML email body."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract order ID
        order_id = self._extract_order_id(soup)
        if not order_id:
            return None
        
        # Extract order date
        order_date = self._extract_order_date(soup)
        
        # Extract items
        items = self._extract_items(soup)
        
        # Extract total
        total = self._extract_total(soup)
        
        # Extract shipment status
        status = self._extract_shipment_status(soup)
        
        return ParsedAmazonOrder(
            order_id=order_id,
            order_date=order_date,
            items=items,
            total_amount=total,
            shipment_status=status
        )
    
    def _extract_order_id(self, soup: BeautifulSoup) -> Optional[str]:
        """Find order number in HTML."""
        # Try common patterns
        for text in soup.stripped_strings:
            match = self.ORDER_ID_PATTERN.search(text)
            if match:
                return match.group(1)
        return None
    
    def _extract_order_date(self, soup: BeautifulSoup) -> datetime:
        """Extract order date."""
        for text in soup.stripped_strings:
            match = self.DATE_PATTERN.search(text)
            if match:
                date_str = match.group(1)
                return datetime.strptime(date_str, '%B %d, %Y')
        return datetime.now()  # Fallback
    
    def _extract_items(self, soup: BeautifulSoup) -> list[ParsedOrderItem]:
        """Extract item details from email."""
        items = []
        
        # Look for product tables (Amazon uses specific classes)
        # This is a simplified version - real implementation needs more patterns
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 2:
                    # Try to identify item name and price
                    text = ' '.join([c.get_text(strip=True) for c in cells])
                    if 'Qty:' in text or 'Quantity:' in text:
                        item = self._parse_item_row(cells)
                        if item:
                            items.append(item)
        
        return items
    
    def _parse_item_row(self, cells) -> Optional[ParsedOrderItem]:
        """Parse individual item from table row."""
        # Simplified - real implementation needs robust pattern matching
        text = ' '.join([c.get_text(strip=True) for c in cells])
        
        # Extract quantity
        qty_match = re.search(r'Qty:?\s*(\d+)', text)
        quantity = int(qty_match.group(1)) if qty_match else 1
        
        # Extract price
        price_match = self.PRICE_PATTERN.search(text)
        price = float(price_match.group(1).replace(',', '')) if price_match else 0.0
        
        # Name is usually the longest text segment
        name = max((c.get_text(strip=True) for c in cells), key=len)
        
        if name and len(name) > 5:  # Sanity check
            return ParsedOrderItem(
                name=name,
                quantity=quantity,
                price=price
            )
        return None
    
    def _extract_total(self, soup: BeautifulSoup) -> float:
        """Extract order total."""
        for text in soup.stripped_strings:
            if 'Order Total' in text or 'Grand Total' in text:
                match = self.PRICE_PATTERN.search(text)
                if match:
                    return float(match.group(1).replace(',', ''))
        return 0.0
    
    def _extract_shipment_status(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract shipment status if present."""
        for text in soup.stripped_strings:
            if 'shipped' in text.lower():
                return 'Shipped'
            elif 'delivered' in text.lower():
                return 'Delivered'
        return 'Pending'
    
    def _parse_text(self, text: str) -> Optional[ParsedAmazonOrder]:
        """Fallback text parsing (less reliable)."""
        # Simplified text parsing
        order_id_match = self.ORDER_ID_PATTERN.search(text)
        if not order_id_match:
            return None
        
        return ParsedAmazonOrder(
            order_id=order_id_match.group(1),
            order_date=datetime.now(),
            items=[],
            total_amount=0.0
        )
```

---

### File: `pfm_web/services/email_sync/sync_service.py`

```python
"""Main email sync orchestration service."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from ...extensions import db
from ...models import AmazonOrder, AmazonOrderItem, User
from .gmail_client import GmailClient
from .email_parser import AmazonEmailParser

logger = logging.getLogger(__name__)


class EmailSyncService:
    """Orchestrate email fetching and order creation."""
    
    def __init__(self, user_id: int, token_file: Path):
        self.user_id = user_id
        self.gmail_client = GmailClient(token_file)
        self.parser = AmazonEmailParser()
    
    def sync_orders(self, days_back: int = 30) -> dict:
        """
        Sync Amazon orders from Gmail.
        
        Args:
            days_back: How many days back to search
            
        Returns:
            Dict with sync statistics
        """
        stats = {
            'emails_processed': 0,
            'orders_created': 0,
            'orders_updated': 0,
            'orders_skipped': 0,
            'errors': []
        }
        
        # Calculate date range
        after_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')
        
        logger.info(f"Starting email sync for user {self.user_id} (after {after_date})")
        
        # Fetch emails
        try:
            emails = self.gmail_client.search_amazon_emails(
                after_date=after_date,
                max_results=100
            )
            
            for email in emails:
                stats['emails_processed'] += 1
                
                # Check if already processed
                if self._is_email_processed(email['message_id']):
                    logger.debug(f"Skipping already processed email: {email['message_id']}")
                    stats['orders_skipped'] += 1
                    continue
                
                # Parse email
                try:
                    parsed_order = self.parser.parse_email(
                        email.get('body_html'),
                        email.get('body_text')
                    )
                    
                    if not parsed_order:
                        logger.warning(f"Failed to parse email: {email['subject']}")
                        stats['errors'].append(f"Parse failed: {email['subject']}")
                        continue
                    
                    # Create or update order
                    created = self._create_or_update_order(parsed_order, email)
                    
                    if created:
                        stats['orders_created'] += 1
                    else:
                        stats['orders_updated'] += 1
                    
                    # Log processing
                    self._log_email_processing(email, 'success', parsed_order.order_id)
                
                except Exception as e:
                    logger.error(f"Error processing email {email['message_id']}: {e}")
                    stats['errors'].append(str(e))
                    self._log_email_processing(email, 'failed', error=str(e))
            
            db.session.commit()
            logger.info(f"Email sync completed: {stats}")
            
        except Exception as e:
            logger.error(f"Email sync failed: {e}")
            stats['errors'].append(f"Sync failed: {e}")
            db.session.rollback()
        
        return stats
    
    def _is_email_processed(self, message_id: str) -> bool:
        """Check if email was already processed."""
        # Query email_processing_log table
        result = db.session.execute(
            "SELECT 1 FROM email_processing_log WHERE email_message_id = ?",
            (message_id,)
        ).fetchone()
        return result is not None
    
    def _create_or_update_order(self, parsed_order, email) -> bool:
        """
        Create new order or update existing.
        
        Returns:
            True if created, False if updated
        """
        # Check if order exists
        existing = AmazonOrder.query.filter_by(
            order_id=parsed_order.order_id
        ).first()
        
        if existing:
            # Update shipment status if changed
            if parsed_order.shipment_status and parsed_order.shipment_status != existing.status:
                existing.status = parsed_order.shipment_status
                existing.updated_at = datetime.now()
            return False
        
        # Create new order
        order = AmazonOrder(
            user_id=self.user_id,
            order_id=parsed_order.order_id,
            order_date=parsed_order.order_date,
            total_amount=parsed_order.total_amount,
            currency=parsed_order.currency,
            status=parsed_order.shipment_status or 'Pending',
            source_type='email',
            email_message_id=email['message_id'],
            raw_email_html=email.get('body_html')
        )
        db.session.add(order)
        db.session.flush()  # Get order.id
        
        # Create order items
        for item in parsed_order.items:
            order_item = AmazonOrderItem(
                amazon_order_id=order.id,
                title=item.name,
                quantity=item.quantity,
                price=item.price,
                asin=item.asin
            )
            db.session.add(order_item)
        
        return True
    
    def _log_email_processing(self, email, status, order_id=None, error=None):
        """Log email processing to database."""
        log_entry = {
            'user_id': self.user_id,
            'email_message_id': email['message_id'],
            'email_subject': email.get('subject'),
            'email_date': email.get('date'),
            'processing_status': status,
            'amazon_order_id': order_id,
            'error_message': error,
            'processed_at': datetime.now()
        }
        
        db.session.execute(
            """
            INSERT INTO email_processing_log 
            (user_id, email_message_id, email_subject, email_date, 
             processing_status, amazon_order_id, error_message, processed_at)
            VALUES (:user_id, :email_message_id, :email_subject, :email_date,
                    :processing_status, :amazon_order_id, :error_message, :processed_at)
            """,
            log_entry
        )
```

---

## 10. Flask CLI Commands

### File: `pfm_web/cli/email_sync_commands.py`

```python
"""Flask CLI commands for email sync."""
import click
from flask import current_app
from flask.cli import with_appcontext

from ..services.email_sync.sync_service import EmailSyncService


@click.group()
def email_sync():
    """Email sync management commands."""
    pass


@email_sync.command()
@click.option('--user-id', required=True, type=int, help='User ID to sync for')
@click.option('--days', default=30, help='Days back to sync')
@with_appcontext
def sync_now(user_id, days):
    """Manually trigger email sync for a user."""
    token_file = current_app.config['GMAIL_TOKEN_FILE']
    
    click.echo(f"Starting email sync for user {user_id}...")
    
    service = EmailSyncService(user_id, token_file)
    stats = service.sync_orders(days_back=days)
    
    click.echo(f"✅ Sync completed!")
    click.echo(f"   Emails processed: {stats['emails_processed']}")
    click.echo(f"   Orders created: {stats['orders_created']}")
    click.echo(f"   Orders updated: {stats['orders_updated']}")
    click.echo(f"   Orders skipped: {stats['orders_skipped']}")
    
    if stats['errors']:
        click.echo(f"⚠️  Errors: {len(stats['errors'])}")
        for error in stats['errors'][:5]:  # Show first 5
            click.echo(f"     - {error}")


@email_sync.command()
@with_appcontext
def setup_oauth():
    """Interactive OAuth2 setup for Gmail."""
    from ..services.email_sync.gmail_client import setup_oauth_interactive
    
    click.echo("Starting Gmail OAuth2 setup...")
    click.echo("This will open a browser window for authentication.")
    
    token_file = setup_oauth_interactive(
        current_app.config['GMAIL_CLIENT_ID'],
        current_app.config['GMAIL_CLIENT_SECRET']
    )
    
    click.echo(f"✅ OAuth2 token saved to: {token_file}")


def init_app(app):
    """Register CLI commands with Flask app."""
    app.cli.add_command(email_sync)
```

---

## 11. Scheduler Setup (Background Jobs)

### File: `pfm_web/services/email_sync/scheduler.py`

```python
"""Background scheduler for periodic email sync."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import current_app

from .sync_service import EmailSyncService


def create_scheduler(app):
    """Create and configure APScheduler."""
    scheduler = BackgroundScheduler()
    
    def sync_all_users():
        """Sync emails for all enabled users."""
        with app.app_context():
            from ...models import User
            from ...extensions import db
            
            # Get users with email sync enabled
            users = db.session.execute(
                "SELECT user_id FROM email_sync_config WHERE sync_enabled = 1"
            ).fetchall()
            
            for (user_id,) in users:
                try:
                    service = EmailSyncService(
                        user_id,
                        current_app.config['GMAIL_TOKEN_FILE']
                    )
                    stats = service.sync_orders(days_back=7)  # Only recent emails
                    current_app.logger.info(
                        f"Scheduled sync for user {user_id}: {stats}"
                    )
                except Exception as e:
                    current_app.logger.error(
                        f"Scheduled sync failed for user {user_id}: {e}"
                    )
    
    # Schedule job
    interval_hours = app.config.get('EMAIL_SYNC_INTERVAL_HOURS', 24)
    scheduler.add_job(
        func=sync_all_users,
        trigger=IntervalTrigger(hours=interval_hours),
        id='email_sync_job',
        name='Sync Amazon emails from Gmail',
        replace_existing=True
    )
    
    return scheduler
```

---

## 12. Database Migration

### File: `pfm_web/migrations/versions/xxxx_add_email_sync_tables.py`

```python
"""Add email sync tables

Revision ID: xxxx
Revises: yyyy
Create Date: 2025-12-13
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    # Create email_sync_config table
    op.create_table(
        'email_sync_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_provider', sa.String(50), server_default='gmail', nullable=False),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column('oauth_token_encrypted', sa.Text(), nullable=True),
        sa.Column('last_sync_date', sa.DateTime(), nullable=True),
        sa.Column('sync_enabled', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('sync_frequency_hours', sa.Integer(), server_default='24', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create email_processing_log table
    op.create_table(
        'email_processing_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_message_id', sa.String(255), nullable=False),
        sa.Column('email_subject', sa.Text(), nullable=True),
        sa.Column('email_date', sa.DateTime(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('processing_status', sa.String(50), nullable=True),
        sa.Column('amazon_order_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['amazon_order_id'], ['amazon_orders.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email_message_id')
    )
    
    # Add new columns to amazon_orders
    op.add_column('amazon_orders', sa.Column('source_type', sa.String(50), server_default='csv', nullable=True))
    op.add_column('amazon_orders', sa.Column('email_message_id', sa.String(255), nullable=True))
    op.add_column('amazon_orders', sa.Column('raw_email_html', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('amazon_orders', 'raw_email_html')
    op.drop_column('amazon_orders', 'email_message_id')
    op.drop_column('amazon_orders', 'source_type')
    op.drop_table('email_processing_log')
    op.drop_table('email_sync_config')
```

---

## 13. Configuration & Setup Steps

### Step-by-Step Setup Guide:

#### 1. Install Dependencies
```bash
cd /home/dgoma/app_dev/pfm-web
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
pip install beautifulsoup4 lxml
pip install apscheduler
pip install flask-migrate  # If not already installed
```

#### 2. Update requirements.txt
```bash
echo "google-auth>=2.23.0" >> requirements.txt
echo "google-auth-oauthlib>=1.1.0" >> requirements.txt
echo "google-auth-httplib2>=0.1.1" >> requirements.txt
echo "google-api-python-client>=2.100.0" >> requirements.txt
echo "beautifulsoup4>=4.12.0" >> requirements.txt
echo "lxml>=4.9.0" >> requirements.txt
echo "APScheduler>=3.10.0" >> requirements.txt
```

#### 3. Google Cloud Setup
1. Visit https://console.cloud.google.com/
2. Create project "PFM-Amazon-Sync"
3. Enable Gmail API
4. Create OAuth2 credentials (Desktop app)
5. Download `credentials.json` to `pfm-web/data/`

#### 4. Generate OAuth Token
```bash
cd /home/dgoma/app_dev/pfm-web
python scripts/generate_gmail_token.py
# This will open browser for authentication
# Token saved to data/gmail_token.pickle
```

#### 5. Configure Environment
```bash
# .env
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_TOKEN_FILE=data/gmail_token.pickle
EMAIL_SYNC_ENABLED=True
EMAIL_SYNC_INTERVAL_HOURS=24
```

#### 6. Run Database Migration
```bash
flask db upgrade
```

#### 7. Test Email Parsing
```bash
# Save a sample Amazon email as HTML
# Test parser
python scripts/test_email_parser.py data/sample_emails/amazon_order.html
```

#### 8. Manual Sync Test
```bash
flask email-sync sync-now --user-id 1 --days 30
```

#### 9. Enable Background Scheduler
```python
# In pfm_web/__init__.py
from .services.email_sync.scheduler import create_scheduler

def create_app():
    app = Flask(__name__)
    # ... existing setup ...
    
    if app.config['EMAIL_SYNC_ENABLED']:
        scheduler = create_scheduler(app)
        scheduler.start()
    
    return app
```

---

## 14. Security Considerations

### Token Storage:
- ✅ Store OAuth tokens encrypted
- ✅ Use environment variables for client secrets
- ✅ Never commit credentials to git
- ✅ Use read-only Gmail scope

### Email Privacy:
- ✅ Only fetch Amazon emails (filtered queries)
- ✅ Store minimal email data (only order info)
- ✅ Allow users to disable sync
- ✅ Provide email deletion tools

### Error Handling:
- ✅ Log failed parses for debugging
- ✅ Don't crash on malformed emails
- ✅ Retry failed syncs with backoff
- ✅ Alert on repeated failures

---

## 15. Testing Strategy

### Unit Tests:
```python
# tests/test_email_parser.py
def test_parse_order_confirmation():
    with open('tests/fixtures/amazon_order.html') as f:
        html = f.read()
    
    parser = AmazonEmailParser()
    order = parser.parse_email(html)
    
    assert order.order_id == '123-4567890-1234567'
    assert order.total_amount == 45.99
    assert len(order.items) == 2
```

### Integration Tests:
```python
def test_full_sync_flow():
    service = EmailSyncService(user_id=1, token_file='test_token.pickle')
    stats = service.sync_orders(days_back=1)
    
    assert stats['orders_created'] > 0
    assert len(stats['errors']) == 0
```

### Manual Testing:
1. Forward test Amazon emails to test account
2. Run sync and verify database
3. Check duplicate handling
4. Verify category auto-assignment

---

## 16. Monitoring & Logging

### Logging Setup:
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/email_sync.log'),
        logging.StreamHandler()
    ]
)
```

### Metrics to Track:
- Emails processed per sync
- Parse success rate
- Orders created vs updated
- Sync duration
- Error frequency

### Dashboard Additions:
```sql
-- Sync health query
SELECT 
    COUNT(*) as total_syncs,
    SUM(CASE WHEN processing_status = 'success' THEN 1 ELSE 0 END) as successful,
    MAX(processed_at) as last_sync
FROM email_processing_log
WHERE user_id = ?
    AND processed_at > datetime('now', '-7 days');
```

---

## 17. Future Enhancements

### Phase 2 Features:
1. **Multi-Provider Support**
   - Outlook/Hotmail
   - Yahoo Mail
   - Custom IMAP servers

2. **Advanced Parsing**
   - Machine learning for better extraction
   - Handle international Amazon sites
   - Parse return/refund emails

3. **Smart Categorization**
   - ML-based category prediction
   - User feedback loop
   - Product image analysis

4. **Real-time Sync**
   - Gmail push notifications (Pub/Sub)
   - Instant order updates
   - Mobile push notifications

5. **Analytics**
   - Spending trends from emails
   - Price tracking
   - Deal alerts

---

## 18. Rollout Plan

### Week 1: Foundation
- [ ] Create database migrations
- [ ] Implement Gmail client
- [ ] Build email parser (basic)
- [ ] Unit tests

### Week 2: Integration
- [ ] Sync service implementation
- [ ] CLI commands
- [ ] Test with real emails
- [ ] Fix parsing issues

### Week 3: Automation
- [ ] Background scheduler
- [ ] Error handling
- [ ] Logging & monitoring
- [ ] Documentation

### Week 4: Polish
- [ ] UI for sync config
- [ ] Sync status dashboard
- [ ] Beta testing
- [ ] Production deployment

---

## 19. Success Metrics

### Key Performance Indicators:
- **Parse accuracy**: >90% of emails correctly parsed
- **Sync reliability**: >95% successful syncs
- **Performance**: <30 seconds for 100 emails
- **User adoption**: >50% enable email sync

### User Feedback:
- Survey users on feature usefulness
- Track manual CSV uploads (should decrease)
- Monitor support tickets

---

## 20. Documentation Checklist

- [x] Architecture diagram
- [x] Database schema design
- [x] API/service interfaces
- [x] Configuration guide
- [x] Security best practices
- [x] Testing strategy
- [ ] User guide
- [ ] Troubleshooting guide
- [ ] API documentation

---

## Conclusion

This plan provides a complete roadmap for implementing automated Amazon order fetching from Gmail emails. The modular architecture allows incremental development and testing, while the OAuth2 approach ensures security and long-term reliability.

**Next Steps:**
1. Review and approve this design
2. Set up Google Cloud project
3. Begin implementation with Phase 1 (Gmail client + parser)
4. Test with sample emails
5. Deploy to production with manual testing
6. Enable background automation

**Estimated Timeline:** 3-4 weeks for full implementation
**Effort:** ~40-60 hours development + testing
