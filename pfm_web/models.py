"""SQLAlchemy models for the PFM web application."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class TimestampMixin:
    """Reusable mixin that adds created/updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        db.DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class CreatedAtMixin:
    """Mixin for tables that only track creation timestamp."""

    created_at: Mapped[datetime] = mapped_column(
        db.DateTime, nullable=False, server_default=func.current_timestamp()
    )


class User(db.Model, CreatedAtMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    role: Mapped[str] = mapped_column(db.String(50), nullable=False, default="owner")

    receipts: Mapped[list["Receipt"]] = relationship(back_populates="user")
    bank_accounts: Mapped[list["BankAccount"]] = relationship(back_populates="user")
    import_jobs: Mapped[list["ImportJob"]] = relationship(back_populates="submitted_by_user")


class Category(db.Model, CreatedAtMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(150), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(db.String(32), nullable=False, default="expense")
    parent_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    color: Mapped[Optional[str]] = mapped_column(db.String(20))
    icon: Mapped[Optional[str]] = mapped_column(db.String(100))

    parent: Mapped[Optional["Category"]] = relationship(remote_side=[id], backref="children")
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="category")
    receipt_items: Mapped[list["ReceiptLineItem"]] = relationship(back_populates="category")
    shops: Mapped[list["Shop"]] = relationship(back_populates="category")
    amazon_items: Mapped[list["AmazonOrderItem"]] = relationship(back_populates="category")
    bank_transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="category")


class Shop(db.Model, CreatedAtMixin):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(db.String(255))
    mcc_code: Mapped[Optional[str]] = mapped_column(db.String(10))
    category_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    visit_count: Mapped[int] = mapped_column(default=0)
    last_visit_date: Mapped[Optional[datetime]] = mapped_column(db.DateTime)

    category: Mapped[Optional[Category]] = relationship(back_populates="shops")
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="shop")
    default_items: Mapped[list["Item"]] = relationship(back_populates="default_shop")


class Item(db.Model, CreatedAtMixin):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(255), unique=True, nullable=False)
    default_category_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    default_shop_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("shops.id"))
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", db.Text)

    default_category: Mapped[Optional[Category]] = relationship(backref="default_items")
    default_shop: Mapped[Optional[Shop]] = relationship(back_populates="default_items")


class Receipt(db.Model, TimestampMixin):
    __tablename__ = "receipts"
    __table_args__ = (
        Index("idx_receipts_user_status", "user_id", "status"),
        Index("idx_receipts_source_external", "source", "external_ref"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(db.String(32), nullable=False)
    external_ref: Mapped[Optional[str]] = mapped_column(db.String(255), unique=True)
    issued_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False)
    total_amount: Mapped[float] = mapped_column(db.Float, nullable=False)
    currency: Mapped[str] = mapped_column(db.String(10), nullable=False, default="USD")
    tax_amount: Mapped[Optional[float]] = mapped_column(db.Float)
    payment_method: Mapped[Optional[str]] = mapped_column(db.String(50))
    receipt_number: Mapped[Optional[str]] = mapped_column(db.String(100))
    vendor_name: Mapped[Optional[str]] = mapped_column(db.String(255))
    vendor_address: Mapped[Optional[str]] = mapped_column(db.String(500))
    shop_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("shops.id"))
    category_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="pending")
    raw_payload: Mapped[Optional[str]] = mapped_column(db.Text)
    processing_engine: Mapped[str] = mapped_column(db.String(100), nullable=False, default="unknown")
    confidence_score: Mapped[Optional[float]] = mapped_column(db.Float)
    language_detected: Mapped[Optional[str]] = mapped_column(db.String(20))
    attachment_path: Mapped[Optional[str]] = mapped_column(db.String(255))

    user: Mapped[Optional[User]] = relationship(back_populates="receipts")
    shop: Mapped[Optional[Shop]] = relationship(back_populates="receipts")
    category: Mapped[Optional[Category]] = relationship(back_populates="receipts")
    items: Mapped[list["ReceiptLineItem"]] = relationship(back_populates="receipt", cascade="all, delete-orphan")
    bank_transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="receipt")
    amazon_orders: Mapped[list["AmazonOrder"]] = relationship(back_populates="receipt")


class ReceiptLineItem(db.Model, CreatedAtMixin):
    __tablename__ = "receipt_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(db.ForeignKey("receipts.id"), nullable=False)
    item_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(db.Float, nullable=False, default=1.0)
    unit_price: Mapped[float] = mapped_column(db.Float, nullable=False)
    total_price: Mapped[float] = mapped_column(db.Float, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    description: Mapped[Optional[str]] = mapped_column(db.Text)

    receipt: Mapped[Receipt] = relationship(back_populates="items")
    category: Mapped[Optional[Category]] = relationship(back_populates="receipt_items")

    __table_args__ = (Index("idx_receipt_line_items_receipt", "receipt_id"),)


class BankAccount(db.Model, CreatedAtMixin):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False)
    bank_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    account_number_masked: Mapped[str] = mapped_column(db.String(64), nullable=False)
    type: Mapped[str] = mapped_column(db.String(32), nullable=False)
    currency: Mapped[str] = mapped_column(db.String(10), nullable=False, default="USD")

    user: Mapped[User] = relationship(back_populates="bank_accounts")
    statements: Mapped[list["BankStatement"]] = relationship(back_populates="bank_account", cascade="all, delete-orphan")
    transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="bank_account", cascade="all, delete-orphan")


class BankStatement(db.Model, CreatedAtMixin):
    __tablename__ = "bank_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(db.ForeignKey("bank_accounts.id"), nullable=False)
    statement_period_start: Mapped[datetime] = mapped_column(db.DateTime, nullable=False)
    statement_period_end: Mapped[datetime] = mapped_column(db.DateTime, nullable=False)
    source_file_path: Mapped[Optional[str]] = mapped_column(db.String(255))
    hash: Mapped[str] = mapped_column(db.String(128), unique=True, nullable=False)

    bank_account: Mapped[BankAccount] = relationship(back_populates="statements")
    transactions: Mapped[list["BankTransaction"]] = relationship(back_populates="statement")


class BankTransaction(db.Model, TimestampMixin):
    __tablename__ = "bank_transactions"
    __table_args__ = (
        Index("idx_bank_transactions_account_date", "bank_account_id", "txn_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_account_id: Mapped[int] = mapped_column(db.ForeignKey("bank_accounts.id"), nullable=False)
    statement_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("bank_statements.id"))
    txn_date: Mapped[datetime] = mapped_column(db.DateTime, nullable=False)
    posted_date: Mapped[Optional[datetime]] = mapped_column(db.DateTime)
    description: Mapped[str] = mapped_column(db.String(255), nullable=False)
    amount: Mapped[float] = mapped_column(db.Float, nullable=False)
    currency: Mapped[str] = mapped_column(db.String(10), nullable=False, default="USD")
    category_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    receipt_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("receipts.id"))
    external_reference: Mapped[Optional[str]] = mapped_column(db.String(255))
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", db.Text)

    bank_account: Mapped[BankAccount] = relationship(back_populates="transactions")
    statement: Mapped[Optional[BankStatement]] = relationship(back_populates="transactions")
    category: Mapped[Optional[Category]] = relationship(back_populates="bank_transactions")
    receipt: Mapped[Optional[Receipt]] = relationship(back_populates="bank_transactions")


class AmazonOrder(db.Model, CreatedAtMixin):
    __tablename__ = "amazon_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)
    order_date: Mapped[datetime] = mapped_column(db.DateTime, nullable=False)
    total_amount: Mapped[float] = mapped_column(db.Float, nullable=False)
    currency: Mapped[str] = mapped_column(db.String(10), nullable=False, default="USD")
    payment_method: Mapped[Optional[str]] = mapped_column(db.String(50))
    shipment_status: Mapped[Optional[str]] = mapped_column(db.String(50))
    raw_payload: Mapped[Optional[str]] = mapped_column(db.Text)
    receipt_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("receipts.id"))

    receipt: Mapped[Optional[Receipt]] = relationship(back_populates="amazon_orders")
    items: Mapped[list["AmazonOrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class AmazonOrderItem(db.Model, CreatedAtMixin):
    __tablename__ = "amazon_order_items"
    __table_args__ = (Index("idx_amazon_order_items_order", "amazon_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    amazon_order_id: Mapped[int] = mapped_column(db.ForeignKey("amazon_orders.id"), nullable=False)
    item_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(db.Float, nullable=False, default=1.0)
    unit_price: Mapped[float] = mapped_column(db.Float, nullable=False)
    total_price: Mapped[float] = mapped_column(db.Float, nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(db.ForeignKey("categories.id"))
    asin: Mapped[Optional[str]] = mapped_column(db.String(50))
    seller: Mapped[Optional[str]] = mapped_column(db.String(255))
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", db.Text)

    order: Mapped[AmazonOrder] = relationship(back_populates="items")
    category: Mapped[Optional[Category]] = relationship(back_populates="amazon_items")


class CleanupIssue(db.Model, CreatedAtMixin):
    __tablename__ = "cleanup_issues"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "issue_type"),
        Index("idx_cleanup_issues_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(db.String(50), nullable=False)
    target_id: Mapped[int] = mapped_column(db.Integer, nullable=False)
    issue_type: Mapped[str] = mapped_column(db.String(50), nullable=False)
    description: Mapped[str] = mapped_column(db.Text, nullable=False)
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="open")
    resolution_notes: Mapped[Optional[str]] = mapped_column(db.Text)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime)


class ImportJob(db.Model, CreatedAtMixin):
    __tablename__ = "import_jobs"
    __table_args__ = (Index("idx_import_jobs_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(db.String(50), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(db.String(255))
    status: Mapped[str] = mapped_column(db.String(32), nullable=False, default="queued")
    submitted_by: Mapped[Optional[int]] = mapped_column(db.ForeignKey("users.id"))
    started_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(db.DateTime)
    log: Mapped[Optional[str]] = mapped_column(db.Text)

    submitted_by_user: Mapped[Optional[User]] = relationship(back_populates="import_jobs")
