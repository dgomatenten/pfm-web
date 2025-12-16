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
    
    ORDER_ID_PATTERN = re.compile(r'Order\s*#?\s*(\d{3}-\d{7}-\d{7})', re.IGNORECASE)
    DATE_PATTERN = re.compile(r'Order\s+Date:?\s*(\w+\s+\d+,\s+\d{4})', re.IGNORECASE)
    PRICE_PATTERN = re.compile(r'\$?([\d,]+\.\d{2})')
    ASIN_PATTERN = re.compile(r'ASIN:?\s*([A-Z0-9]{10})', re.IGNORECASE)
    
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
        items = self._extract_items(soup, html)
        
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
        text_content = soup.get_text()
        match = self.ORDER_ID_PATTERN.search(text_content)
        if match:
            return match.group(1)
        return None
    
    def _extract_order_date(self, soup: BeautifulSoup) -> datetime:
        """Extract order date."""
        text_content = soup.get_text()
        match = self.DATE_PATTERN.search(text_content)
        if match:
            date_str = match.group(1)
            try:
                return datetime.strptime(date_str, '%B %d, %Y')
            except ValueError:
                try:
                    # Try alternative format
                    return datetime.strptime(date_str, '%b %d, %Y')
                except ValueError:
                    pass
        return datetime.now()  # Fallback
    
    def _extract_items(self, soup: BeautifulSoup, html: str) -> list[ParsedOrderItem]:
        """Extract item details from email."""
        items = []
        
        # Strategy 1: Look for product tables
        for table in soup.find_all('table'):
            table_text = table.get_text()
            if 'product' in table_text.lower() or 'item' in table_text.lower():
                for row in table.find_all('tr'):
                    item = self._parse_item_row(row)
                    if item:
                        items.append(item)
        
        # Strategy 2: Look for div containers with product info
        for div in soup.find_all('div'):
            div_text = div.get_text()
            # Look for price indicators
            if self.PRICE_PATTERN.search(div_text):
                # Check if this looks like a product div
                if len(div_text) > 10 and len(div_text) < 500:
                    item = self._parse_item_from_text(div_text)
                    if item and item not in items:
                        items.append(item)
        
        # Strategy 3: Fallback - scan all text for patterns
        if not items:
            items = self._extract_items_from_full_text(soup.get_text())
        
        return items
    
    def _parse_item_row(self, row) -> Optional[ParsedOrderItem]:
        """Parse individual item from table row."""
        try:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                return None
            
            text = ' '.join([c.get_text(strip=True) for c in cells])
            
            # Skip header rows
            if 'product' in text.lower() and 'price' in text.lower():
                return None
            
            # Extract quantity
            qty_match = re.search(r'(?:Qty|Quantity):?\s*(\d+)', text, re.IGNORECASE)
            quantity = int(qty_match.group(1)) if qty_match else 1
            
            # Extract price
            price_match = self.PRICE_PATTERN.search(text)
            price = float(price_match.group(1).replace(',', '')) if price_match else 0.0
            
            # Extract ASIN
            asin_match = self.ASIN_PATTERN.search(text)
            asin = asin_match.group(1) if asin_match else None
            
            # Name is usually the longest text segment
            name_candidates = [c.get_text(strip=True) for c in cells]
            name = max(name_candidates, key=len) if name_candidates else ""
            
            # Clean name - remove price and qty text
            name = re.sub(r'\$[\d,]+\.\d{2}', '', name)
            name = re.sub(r'Qty:?\s*\d+', '', name, flags=re.IGNORECASE)
            name = name.strip()
            
            if name and len(name) > 5 and price > 0:  # Sanity check
                return ParsedOrderItem(
                    name=name,
                    quantity=quantity,
                    price=price,
                    asin=asin
                )
        except Exception as e:
            print(f"Error parsing item row: {e}")
        
        return None
    
    def _parse_item_from_text(self, text: str) -> Optional[ParsedOrderItem]:
        """Parse item from text block."""
        try:
            # Extract price
            price_match = self.PRICE_PATTERN.search(text)
            if not price_match:
                return None
            
            price = float(price_match.group(1).replace(',', ''))
            
            # Extract quantity
            qty_match = re.search(r'(?:Qty|Quantity):?\s*(\d+)', text, re.IGNORECASE)
            quantity = int(qty_match.group(1)) if qty_match else 1
            
            # Extract ASIN
            asin_match = self.ASIN_PATTERN.search(text)
            asin = asin_match.group(1) if asin_match else None
            
            # Clean text for name
            name = text
            name = re.sub(r'\$[\d,]+\.\d{2}', '', name)
            name = re.sub(r'Qty:?\s*\d+', '', name, flags=re.IGNORECASE)
            name = re.sub(r'ASIN:?\s*[A-Z0-9]{10}', '', name, flags=re.IGNORECASE)
            name = ' '.join(name.split())  # Normalize whitespace
            name = name[:200]  # Limit length
            
            if name and len(name) > 5 and price > 0:
                return ParsedOrderItem(
                    name=name,
                    quantity=quantity,
                    price=price,
                    asin=asin
                )
        except Exception as e:
            print(f"Error parsing item from text: {e}")
        
        return None
    
    def _extract_items_from_full_text(self, text: str) -> list[ParsedOrderItem]:
        """Fallback method: extract items from full email text."""
        items = []
        
        # Split into lines and look for price patterns
        lines = text.split('\n')
        for i, line in enumerate(lines):
            price_match = self.PRICE_PATTERN.search(line)
            if price_match:
                # Look at surrounding lines for product name
                context_start = max(0, i - 2)
                context_end = min(len(lines), i + 3)
                context = ' '.join(lines[context_start:context_end])
                
                item = self._parse_item_from_text(context)
                if item and item not in items:
                    items.append(item)
        
        return items[:20]  # Limit to avoid false positives
    
    def _extract_total(self, soup: BeautifulSoup) -> float:
        """Extract order total."""
        text_content = soup.get_text()
        
        # Look for common total indicators
        patterns = [
            r'Order\s+Total:?\s*\$?([\d,]+\.\d{2})',
            r'Grand\s+Total:?\s*\$?([\d,]+\.\d{2})',
            r'Total:?\s*\$?([\d,]+\.\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                return float(match.group(1).replace(',', ''))
        
        return 0.0
    
    def _extract_shipment_status(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract shipment status if present."""
        text_content = soup.get_text().lower()
        
        if 'delivered' in text_content:
            return 'Delivered'
        elif 'shipped' in text_content or 'dispatched' in text_content:
            return 'Shipped'
        elif 'preparing' in text_content:
            return 'Preparing'
        
        return 'Pending'
    
    def _parse_text(self, text: str) -> Optional[ParsedAmazonOrder]:
        """Fallback text parsing (less reliable)."""
        # Extract order ID
        order_id_match = self.ORDER_ID_PATTERN.search(text)
        if not order_id_match:
            return None
        
        # Extract date
        date_match = self.DATE_PATTERN.search(text)
        order_date = datetime.now()
        if date_match:
            try:
                order_date = datetime.strptime(date_match.group(1), '%B %d, %Y')
            except ValueError:
                pass
        
        # Extract items
        items = self._extract_items_from_full_text(text)
        
        # Extract total
        total_match = re.search(r'(?:Order|Grand)?\s*Total:?\s*\$?([\d,]+\.\d{2})', text, re.IGNORECASE)
        total = float(total_match.group(1).replace(',', '')) if total_match else 0.0
        
        return ParsedAmazonOrder(
            order_id=order_id_match.group(1),
            order_date=order_date,
            items=items,
            total_amount=total
        )
