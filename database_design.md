# PFM Web Database Design

## 1. Architecture Overview
- Primary persistence layer uses SQLAlchemy ORM targeting SQLite in phase 1; switching to PostgreSQL requires only an environment-driven DSN change and running the same Alembic migrations.
- Single schema (default namespace) with referential integrity enforced via foreign keys and cascading rules; future PostgreSQL deployment may leverage schemas (e.g., `public`).
- All timestamps stored in UTC ISO-8601 strings in SQLite and mapped to `TIMESTAMP WITH TIME ZONE` when on PostgreSQL via SQLAlchemy column types.

## 2. Naming and Conventions
- Table names: snake_case plural (e.g., `receipts`, `bank_transactions`).
- Primary keys: `id` INTEGER primary key autoincrement.
- Foreign keys follow `<referenced_table>_id` naming with cascading deletes where business logic allows.
- Soft deletes avoided; records remain with status flags to prevent orphaned analytics.
- Monetary values stored as `REAL` in SQLite and `NUMERIC(18,2)` in PostgreSQL; application layer provides rounding utilities.

## 3. Entity Relationship Summary
- `users` (optional in phase 1) owns many `receipts`, `bank_accounts`, `bank_transactions`, `import_jobs`.
- `receipts` sync from Android app, link to many `receipt_line_items`, optionally reference `shops` and `categories`.
- `bank_transactions` reconcile with `receipts` and `amazon_orders` through associative tables.
- `amazon_orders` contain many `amazon_order_items`; both optionally relate to master data (`categories`, `items`, `shops`).
- `cleanup_issues` polymorphically reference other tables by storing target type and id.

## 4. Table Specifications
### 4.1 users
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT | Reserved for future multi-user support |
| email | TEXT | UNIQUE NOT NULL | Lowercased, indexed |
| password_hash | TEXT | NOT NULL | Argon2 or bcrypt |
| role | TEXT | NOT NULL DEFAULT 'owner' | Enum enforced in app |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP | UTC |

### 4.2 receipts
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| user_id | INTEGER | FK users(id) ON DELETE SET NULL | Nullable until multi-user enabled |
| source | TEXT | NOT NULL | Enum: android, bank, amazon, manual |
| external_ref | TEXT | UNIQUE NULL | Maps to Android receipt id or bank ref |
| issued_at | TEXT | NOT NULL | Date of purchase |
| total_amount | REAL | NOT NULL |
| currency | TEXT | NOT NULL DEFAULT 'USD' | ISO 4217 |
| tax_amount | REAL | NULL |
| payment_method | TEXT | NULL |
| receipt_number | TEXT | NULL |
| vendor_name | TEXT | NULL |
| shop_id | INTEGER | FK shops(id) ON DELETE SET NULL |
| category_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| status | TEXT | NOT NULL DEFAULT 'pending' | pending, verified, archived |
| raw_payload | TEXT | NULL | JSON string of Android source data |
| processing_engine | TEXT | NOT NULL DEFAULT 'unknown' |
| confidence_score | REAL | NULL |
| language_detected | TEXT | NULL |
| attachment_path | TEXT | NULL | Relative path to receipt image |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |
| updated_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Indexes:
- `idx_receipts_user_status` on `(user_id, status)`
- `idx_receipts_source_external` on `(source, external_ref)`

### 4.3 receipt_line_items
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| receipt_id | INTEGER | FK receipts(id) ON DELETE CASCADE |
| item_name | TEXT | NOT NULL |
| quantity | REAL | NOT NULL DEFAULT 1.0 |
| unit_price | REAL | NOT NULL |
| total_price | REAL | NOT NULL |
| category_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| description | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Index: `idx_receipt_line_items_receipt` on `(receipt_id)`

### 4.4 shops
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| name | TEXT | NOT NULL UNIQUE |
| address | TEXT | NULL |
| mcc_code | TEXT | NULL |
| category_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| visit_count | INTEGER | NOT NULL DEFAULT 0 |
| last_visit_date | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

### 4.5 categories
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| name | TEXT | NOT NULL UNIQUE |
| type | TEXT | NOT NULL DEFAULT 'expense' | Enum: expense, income, transfer |
| parent_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| color | TEXT | NULL |
| icon | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Index: `idx_categories_parent` on `(parent_id)`

### 4.6 items
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| name | TEXT | NOT NULL UNIQUE |
| default_category_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| default_shop_id | INTEGER | FK shops(id) ON DELETE SET NULL |
| metadata | TEXT | NULL | JSON blob |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

### 4.7 bank_accounts
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| user_id | INTEGER | FK users(id) ON DELETE CASCADE |
| bank_name | TEXT | NOT NULL |
| account_number_masked | TEXT | NOT NULL |
| type | TEXT | NOT NULL | Enum: credit_card, checking, savings |
| currency | TEXT | NOT NULL DEFAULT 'USD' |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

### 4.8 bank_statements
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| bank_account_id | INTEGER | FK bank_accounts(id) ON DELETE CASCADE |
| statement_period_start | TEXT | NOT NULL |
| statement_period_end | TEXT | NOT NULL |
| source_file_path | TEXT | NULL |
| hash | TEXT | UNIQUE NOT NULL | Detect duplicates |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

### 4.9 bank_transactions
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| bank_account_id | INTEGER | FK bank_accounts(id) ON DELETE CASCADE |
| statement_id | INTEGER | FK bank_statements(id) ON DELETE SET NULL |
| txn_date | TEXT | NOT NULL |
| posted_date | TEXT | NULL |
| description | TEXT | NOT NULL |
| amount | REAL | NOT NULL |
| currency | TEXT | NOT NULL DEFAULT 'USD' |
| category_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| receipt_id | INTEGER | FK receipts(id) ON DELETE SET NULL |
| external_reference | TEXT | NULL |
| metadata | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |
| updated_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Index: `idx_bank_transactions_account_date` on `(bank_account_id, txn_date)`

### 4.10 amazon_orders
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| order_number | TEXT | NOT NULL UNIQUE |
| order_date | TEXT | NOT NULL |
| total_amount | REAL | NOT NULL |
| currency | TEXT | NOT NULL DEFAULT 'USD' |
| payment_method | TEXT | NULL |
| shipment_status | TEXT | NULL |
| raw_payload | TEXT | NULL |
| receipt_id | INTEGER | FK receipts(id) ON DELETE SET NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

### 4.11 amazon_order_items
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| amazon_order_id | INTEGER | FK amazon_orders(id) ON DELETE CASCADE |
| item_name | TEXT | NOT NULL |
| quantity | REAL | NOT NULL DEFAULT 1.0 |
| unit_price | REAL | NOT NULL |
| total_price | REAL | NOT NULL |
| category_id | INTEGER | FK categories(id) ON DELETE SET NULL |
| asin | TEXT | NULL |
| seller | TEXT | NULL |
| metadata | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Index: `idx_amazon_order_items_order` on `(amazon_order_id)`

### 4.12 cleanup_issues
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| target_type | TEXT | NOT NULL | Enum enforced in app |
| target_id | INTEGER | NOT NULL |
| issue_type | TEXT | NOT NULL | e.g., duplicate, missing_field |
| description | TEXT | NOT NULL |
| status | TEXT | NOT NULL DEFAULT 'open' |
| resolution_notes | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |
| resolved_at | TEXT | NULL |

Index: `idx_cleanup_issues_target` on `(target_type, target_id)`

### 4.13 import_jobs
| Column | SQLite Type | Constraints | Notes |
|---|---|---|---|
| id | INTEGER | PK AUTOINCREMENT |
| job_type | TEXT | NOT NULL | Enum: android_sync, bank_statement, amazon_csv |
| source | TEXT | NULL | File path, API identifier |
| status | TEXT | NOT NULL DEFAULT 'queued' | queued, running, failed, completed |
| submitted_by | INTEGER | FK users(id) ON DELETE SET NULL |
| started_at | TEXT | NULL |
| completed_at | TEXT | NULL |
| log | TEXT | NULL |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Index: `idx_import_jobs_status` on `(status)`

## 5. Android Schema Alignment
- Android app persists receipts, receipt items, shops, and categories with nearly identical fields; server schema includes superset columns to store additional metadata (e.g., status, mapping ids).
- Sync strategy: Android payload ingested into `receipts` and `receipt_line_items`; missing foreign keys resolved by lookup/creation in `shops` and `categories`. Unmapped values logged as `cleanup_issues`.
- Keep Android primary keys in `external_ref` to support idempotent imports.

## 6. Data Integrity and Constraints
- Use SQLAlchemy events to maintain `updated_at` timestamps.
- Enforce unique constraints for deduplication (`receipts.external_ref`, `amazon_orders.order_number`, `bank_statements.hash`).
- Background checks for orphaned records run as scheduled tasks, escalating to `cleanup_issues` when anomalies detected.

## 7. Migration and Tooling
- Alembic manages schema evolution; first migration creates all tables with SQLite-compatible types.
- Database URL configured via `DATABASE_URL` environment variable; default `sqlite:///pfm.db`. Production uses `postgresql+psycopg://...`.
- Seed scripts populate baseline categories and shops for testing.
- Data fixtures written as JSON to allow deterministic integration tests.

## 8. Performance Considerations
- Add covering indexes on frequent filters (e.g., `receipts (issued_at DESC)`, `bank_transactions (category_id)`); monitor query plans with `EXPLAIN` when using PostgreSQL.
- For SQLite, wrap bulk imports in transactions and disable synchronous mode temporarily for large sync batches if acceptable.
- Archive attachments to object storage when file count grows beyond local filesystem limits.

## 9. Backup and Recovery
- SQLite: daily copy of database file plus WAL; before upgrade, export via `.backup` command.
- PostgreSQL (future): point-in-time recovery through managed service (e.g., RDS automated backups); schema migrations tested in staging before production rollout.

## 10. Open Items
- Confirm need for `users` table prior to phase 2 multi-user rollout.
- Decide whether `cleanup_issues.target_id` should enforce FK constraints in PostgreSQL using association tables.
- Validate numeric precision requirements for multi-currency support.
