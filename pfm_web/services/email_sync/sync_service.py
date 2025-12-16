"""Main email sync orchestration service."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import text

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
                        self._log_email_processing(email, 'failed', error='Parse failed')
                        continue
                    
                    # Create or update order
                    created = self._create_or_update_order(parsed_order, email)
                    
                    if created:
                        stats['orders_created'] += 1
                        logger.info(f"Created order {parsed_order.order_id}")
                    else:
                        stats['orders_updated'] += 1
                        logger.info(f"Updated order {parsed_order.order_id}")
                    
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
        try:
            result = db.session.execute(
                text("SELECT 1 FROM email_processing_log WHERE email_message_id = :msg_id"),
                {"msg_id": message_id}
            ).fetchone()
            return result is not None
        except Exception:
            # Table might not exist yet
            return False
    
    def _create_or_update_order(self, parsed_order, email) -> bool:
        """
        Create new order or update existing.
        
        Returns:
            True if created, False if updated
        """
        # Check if order exists
        existing = AmazonOrder.query.filter_by(
            order_number=parsed_order.order_id
        ).first()
        
        if existing:
            # Update shipment status if changed
            if parsed_order.shipment_status and parsed_order.shipment_status != existing.shipment_status:
                existing.shipment_status = parsed_order.shipment_status
            return False
        
        # Create new order
        order = AmazonOrder(
            user_id=self.user_id,
            order_number=parsed_order.order_id,
            order_date=parsed_order.order_date,
            total_amount=parsed_order.total_amount,
            currency=parsed_order.currency,
            shipment_status=parsed_order.shipment_status or 'Pending'
        )
        
        # Add source tracking if columns exist
        try:
            order.source_type = 'email'
            order.email_message_id = email['message_id']
            order.raw_email_html = email.get('body_html', '')[:5000]  # Limit size
        except AttributeError:
            # Columns don't exist yet
            pass
        
        db.session.add(order)
        db.session.flush()  # Get order.id
        
        # Create order items
        for item in parsed_order.items:
            order_item = AmazonOrderItem(
                amazon_order_id=order.id,
                item_name=item.name,
                quantity=item.quantity,
                unit_price=item.price,
                total_price=item.price * item.quantity,
                asin=item.asin
            )
            db.session.add(order_item)
        
        return True
    
    def _log_email_processing(
        self, 
        email: dict, 
        status: str, 
        order_id: Optional[str] = None, 
        error: Optional[str] = None
    ):
        """Log email processing to database."""
        # Find order ID if order_id string provided
        amazon_order_id = None
        if order_id:
            order = AmazonOrder.query.filter_by(order_number=order_id).first()
            if order:
                amazon_order_id = order.id
        
        try:
            db.session.execute(
                text("""
                        INSERT INTO email_processing_log 
                        (user_id, email_message_id, email_subject, email_date, 
                         processing_status, amazon_order_id, error_message, processed_at)
                        VALUES (:user_id, :email_message_id, :email_subject, :email_date,
                                :processing_status, :amazon_order_id, :error_message, :processed_at)
                    """),
                    {
                        'user_id': self.user_id,
                        'email_message_id': email['message_id'],
                        'email_subject': email.get('subject', '')[:500],
                        'email_date': email.get('date'),
                        'processing_status': status,
                        'amazon_order_id': amazon_order_id,
                        'error_message': error[:1000] if error else None,
                        'processed_at': datetime.now()
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to log email processing: {e}")
