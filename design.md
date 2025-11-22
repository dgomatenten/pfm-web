# PFM Web System Design

## 1. Overview
- Build a Personal Finance Management (PFM) web application that synchronizes data from the existing Android app, ingests bank credit card statements, and manages Amazon order history.
- Provide tools for data cleaning, categorization, and master data management to support accurate reporting and budgeting.

## 2. Goals and Non-Goals
- Goals:
  - Consolidate financial records (receipts, bank statements, Amazon orders) into a unified datastore.
  - Offer web-based interfaces for reviewing, editing, and categorizing transactions.
  - Enable robust data hygiene tooling (duplicate detection, category normalization, missing field resolution).
  - Support extensible architecture for future cloud deployment and additional integrations.
- Non-Goals (phase 1):
  - Real-time analytics dashboards (basic reporting only).
  - Native mobile web experience beyond responsive layout.
  - Automated payment scheduling or budgeting recommendations.

## 3. Key Requirements
- Synchronize with PFM Android App via secure API to retrieve receipt data.
- Import and reconcile credit card bank statements.
- Import Amazon order data (order history, items, payment, delivery info).
- Data cleanup workflows for receipts (deduplication, normalization, fixing OCR errors).
- Master data management for categories, shops, and items (CRUD operations, history tracking).
- Operate locally during initial development; design for optional Docker-based deployment and future cloud hosting.

## 4. Assumptions
- Android app can expose or adapt to a RESTful API endpoint to push/pull receipts.
- Bank statements are exported as CSV/Excel; format mapping handled via configurable parsers.
- Amazon order data retrieved via user-provided CSV download or Amazon API (if available) with user authorization.
- Single-user system initially; multi-user support to be designed but not implemented in phase 1.
- SQLite serves as the phase-1 datastore; migration path to PostgreSQL kept low-effort via SQLAlchemy abstractions.

## 5. System Architecture
- Three-layer architecture: Presentation (Flask web UI + REST API), Application Services (business logic), Persistence (SQLAlchemy ORM backed by SQLite initially and PostgreSQL-ready).
- Background job runner (Celery or RQ) for long-running imports and data cleanup tasks.
- Storage stack:
  - Primary relational database (SQLite file locally, swappable to PostgreSQL with environment change).
  - Optional object storage (local or S3-compatible) for storing original receipt images.
- Deployment options:
  - Local: Python virtual environment + SQLite database file (default) with optional Postgres DSN when needed.
  - Container: Docker Compose orchestrating web app, worker, cache, and optional Postgres service.
  - Cloud-ready: Provide IaC templates (future) for managed Postgres and container runtime (e.g., AWS ECS, Azure App Service).

## 6. Component Design
- Web App (Flask/Flask-RESTful):
  - REST API endpoints for data ingestion and management.
  - Server-rendered UI (Jinja2) or hybrid SPA (limited scope) for CRUD screens and dashboards.
  - Authentication/Authorization: JWT for API, session-based for UI (initially single user, easily extendable).
- Data Sync Service:
  - Endpoint to accept payloads from Android app (receipts, images) with signature verification.
  - Receipts stored in raw form; triggers normalization pipeline.
- Import Pipelines:
  - Bank Statement Importer: Parser modules keyed by bank + format; scheduled or manual uploads.
  - Amazon Importer: CSV parser with mapping to transactions and item catalog.
- Data Cleanup Engine:
  - Deduplication rules (fuzzy matching by amount/date/vendor).
  - Normalization tasks (merchant name cleanup, category mapping suggestions, currency conversion if required).
  - User-facing UI to review flagged issues and apply fixes.
- Master Data Management:
  - CRUD modules for category, shop, item entities.
  - Versioning/audit trail for changes.
  - Auto-suggest categories during receipt import using ML-lite heuristics (future enhancement).
- Background Worker:
  - Executes imports, cleanup, and sync tasks asynchronously.
  - Uses Redis or RabbitMQ as message broker.
- Notification/Alerting (future):
  - Email or in-app notifications on import completion, data issues, or summary reports.

## 7. Data Model (Initial Draft)
- Entities:
  - User (for future multi-user support): id, email, password hash, roles.
  - Receipt: id, user_id, source (Android, bank, Amazon), issued_at, total_amount, currency, vendor_name, status, raw_payload, attachment_path.
  - ReceiptLineItem: id, receipt_id, item_name, quantity, unit_price, category_id, notes.
  - BankTransaction: id, user_id, account_id, txn_date, posted_date, amount, description, category_id, statement_id, external_reference.
  - BankAccount: id, user_id, bank_name, account_number_masked, type, currency.
  - AmazonOrder: id, order_number, order_date, total_amount, currency, payment_method, shipment_status, raw_payload.
  - AmazonOrderItem: id, order_id, item_name, quantity, unit_price, category_id, asin, seller.
  - Category: id, name, parent_id, type (expense/income/transfer), active.
  - Shop: id, name, default_category_id, metadata.
  - Item: id, name, default_category_id, default_shop_id, metadata.
  - CleanupIssue: id, target_type, target_id, issue_type, description, status, resolution_notes, created_at, resolved_at.
  - ImportJob: id, type, source, status, submitted_by, started_at, completed_at, log.

### 7.1 Android App Source Schema Reference
- Receipts table fields: `shop_name`, `date`, `total_amount`, `currency` (default `USD`), `tax_amount`, `payment_method`, `receipt_number`, `location`, `raw_ocr_text`, `processing_engine` (default `unknown`), `confidence_score`, `language_detected`, timestamps.
- Receipt items table fields: `item_name`, `unit_price`, `quantity` (default `1.0`), `total_price`, `category`, `description`, timestamps, foreign key to receipt with cascade delete.
- Shops table fields: `name` (unique), `address`, `mcc_code`, `category`, `visit_count`, `last_visit_date`, timestamps.
- Categories table fields: `name` (unique), `color`, `icon`, `parent_category`, timestamps.
- Sync design should map these source columns onto the web schema, preserving defaults and constraints; additional metadata (e.g., confidence) stored either in dedicated columns or JSON payload columns for extensibility.

## 8. API Surface (Draft)
- `/api/auth/login` POST (session/JWT issuance).
- `/api/receipts` GET/POST/PATCH (list, create from Android payload, update status).
- `/api/receipts/{id}/upload` POST (receipt image upload).
- `/api/bank-statements/upload` POST (file upload + parser selection).
- `/api/bank-transactions` GET (list with filters) & PATCH (categorize, merge duplicates).
- `/api/amazon-orders/upload` POST.
- `/api/master-data/categories|shops|items` CRUD endpoints.
- `/api/cleanup-issues` GET/PATCH (review + resolve).
- `/api/import-jobs` GET (status polling).

## 9. User Interface (Draft)
- Dashboard: summary cards (spend by category, recent imports, outstanding cleanup tasks).
- Receipts Inbox: table of newly synced receipts with quick actions (assign category, mark duplicate, attach to bank transaction).
- Bank Statements: upload wizard, reconciliation view linking statements to transactions.
- Amazon Orders: list and detail pages; map items to categories.
- Cleanup Center: queue of issues with bulk actions and resolution tracking.
- Master Data: management tables with inline editing and history view.

## 10. Data Security & Privacy
- Secure API endpoints with HTTPS (self-signed for local, proper cert in production).
- Store secrets via environment variables (.env for local), integrate with secret manager in cloud deployments.
- Encrypt sensitive fields (e.g., masked account numbers).
- Enforce strict file upload validation (file type, size limits).
- Log access and changes for auditing.

## 11. Deployment Strategy
- Local development:
  - Option A: Python virtual environment + SQLite file datastore (default).
  - Option B: Docker Compose with services: `web`, `worker`, `cache`, optional `postgres` when scaling beyond SQLite.
- Continuous Integration:
  - Use GitHub Actions to run linting, tests, coverage, and builds.
- Production (future):
  - Containerized deployment to cloud (ECS, Azure Container Apps, or Kubernetes) with managed Postgres, reusing the same SQLAlchemy models and migrations for a low-friction database upgrade.
  - Include migration tooling (Alembic) and observability (OpenTelemetry, structured logging).

## 12. Implementation Roadmap (Phase 1)
1. Project scaffolding: Flask app, SQLAlchemy models, Alembic migrations, basic auth, SQLite configuration with env-driven DSN for future PostgreSQL swap.
2. Implement receipt sync endpoint and basic UI listing receipts.
3. Build bank statement importer (manual upload) with reconciliation view.
4. Implement Amazon order importer (CSV based) and associated UI.
5. Develop cleanup issue detection rules and review UI.
6. Create master data CRUD pages and API.
7. Add background worker and job tracking for imports.
8. Add automated tests (unit + integration) and continuous integration pipeline.

## 13. Open Questions
- Does the Android app support push model (web pulls) or will it push receipt data to an exposed endpoint?
- Preferred bank statement formats and parsing complexity (need sample files).
- Amazon data source: API integration vs. manual CSV uploads (depends on available credentials/permissions).
- Requirements for reporting/analytics beyond basic tables.
- Need for multi-language support or currency conversion.

## 14. Next Steps
- Validate assumptions with stakeholders (data sources, formats, volume).
- Collect sample datasets (Android payload, bank statements, Amazon CSV) for parser design.
- Decide on authentication approach for Android-to-web sync.
- Confirm local deployment preference (virtual env vs Docker) to set up development environment.

## 15. Development Workflow (Initial Draft)
- Environment setup:
  - Create Python virtual environment, install Flask, SQLAlchemy, Alembic, and lint/test tooling.
  - Configure `.env` with `DATABASE_URL=sqlite:///pfm.db` and run `schema.sql` (or Alembic migration) to initialize database.
- Application scaffolding:
  - Implement Flask application factory with config loading and SQLite connection.
  - Define SQLAlchemy models mirroring schema and register with Alembic for migrations.
- Core features build order:
  1. Receipts ingestion API for Android payload plus background processing stub.
  2. Receipts Inbox UI with filtering and category assignment workflow.
  3. Master data CRUD pages (categories, shops, items).
  4. Bank statement importer (file upload, parser interface, reconciliation view).
  5. Amazon order importer (CSV parser, list/detail UI).
  6. Cleanup issue detection and review UI tying into ingestion pipelines.
  7. Authentication basics (single user login/session management) once core workflows stabilized.
- Quality and operations:
  - Establish unit/integration test suites (Pytest) backed by in-memory or temp SQLite.
  - Add linting (`ruff`, `black`), type checking (`mypy`) to CI pipeline.
  - Document seed scripts for baseline categories/shops and data fixtures for testing.
  - Prepare Docker Compose template for web/worker/cache stacks using SQLite volume initially.
  - Define dockerization path: start with `docker/` directory containing base `Dockerfile` (Flask app) and incremental `docker-compose.yml` that can switch between SQLite volume and PostgreSQL service when productionizing.
