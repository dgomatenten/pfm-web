"""PFM web application factory."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from .config import adjust_sqlite_connect_args, get_config
from .extensions import db, migrate
from . import importers  # noqa: E402  # CLI helpers


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    _load_environment()

    config_class = get_config(config_name)
    config_obj = config_class()
    adjust_sqlite_connect_args(config_obj)

    app = Flask(__name__)
    app.config.from_object(config_obj)

    config_obj.init_app(app)

    _init_extensions(app)
    _register_blueprints(app)
    _configure_logging(app)
    _register_shellcontext(app)
    _register_template_filters(app)
    _register_cli_commands(app)

    return app


def _load_environment() -> None:
    """Load environment variables from a local .env if present."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)


def _register_blueprints(app: Flask) -> None:
    from .routes import health_bp
    from .web import web_bp
    from .api import api_bp
    from .analytics_api import analytics_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(analytics_bp)


def _configure_logging(app: Flask) -> None:
    log_level = app.config.get("LOG_LEVEL", "INFO")
    app.logger.setLevel(log_level)
    logging.basicConfig(level=log_level)


def _register_shellcontext(app: Flask) -> None:
    from . import models  # noqa: WPS433 lazy import to register models

    @app.shell_context_processor
    def shell_context():  # type: ignore
        return {"db": db, "models": models}


def _register_template_filters(app: Flask) -> None:
    @app.template_filter("currency")
    def currency_filter(value, currency_code="USD"):
        if value is None:
            return "--"
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return str(value)
        symbol = _currency_symbol(currency_code)
        return f"{symbol}{amount:,.2f}" if symbol else f"{amount:,.2f} {currency_code}"


def _currency_symbol(code: str | None) -> str:
    if not code:
        return ""
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
    }
    return symbols.get(code.upper(), "")


def _register_cli_commands(app: Flask) -> None:
    import click
    from . import amazon_importer
    from .analytics import UnifiedAnalytics

    @app.cli.command("import-receipts")
    @click.argument("path", type=click.Path(exists=True, dir_okay=False))
    def import_receipts_command(path: str) -> None:
        payload = importers.load_receipts_export(Path(path))
        result = importers.import_receipts_export(payload)
        click.echo(
            f"Imported {result.receipts_created} receipts "
            f"({result.line_items_created} items). "
            f"Skipped {result.receipts_skipped} duplicates."
        )

    @app.cli.command("import-amazon")
    @click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
    def import_amazon_command(csv_path: str) -> None:
        """Import Amazon order history from CSV file."""
        result = amazon_importer.import_amazon_csv(Path(csv_path))
        click.echo(
            f"Imported {result.orders_created} orders "
            f"({result.items_created} items, {result.items_categorized} auto-categorized). "
            f"Skipped {result.orders_skipped} duplicates."
        )

    @app.cli.command("spending-summary")
    @click.option("--days", type=int, default=30, help="Number of days to analyze (default: 30)")
    def spending_summary_command(days: int) -> None:
        """Show spending summary combining receipts and Amazon orders."""
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        summary = UnifiedAnalytics.get_spending_summary(start_date, end_date)
        
        click.echo(f"\n{'='*60}")
        click.echo(f"Spending Summary (Last {days} Days)")
        click.echo(f"{'='*60}")
        click.echo(f"Total Spent:       ${summary.total_amount:,.2f}")
        click.echo(f"Transactions:      {summary.transaction_count}")
        click.echo(f"Items Purchased:   {summary.item_count}")
        click.echo(f"Avg Transaction:   ${summary.avg_transaction:.2f}")
        click.echo(f"\nBy Source:")
        click.echo(f"  Receipts:        ${summary.by_source['receipts']:,.2f}")
        click.echo(f"  Amazon:          ${summary.by_source['amazon']:,.2f}")
        
        if summary.by_category:
            click.echo(f"\nTop 5 Categories:")
            sorted_cats = sorted(summary.by_category.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat_name, amount in sorted_cats:
                pct = (amount / summary.total_amount * 100) if summary.total_amount > 0 else 0
                click.echo(f"  {cat_name:30} ${amount:>10,.2f} ({pct:>5.1f}%)")
        
        click.echo(f"{'='*60}\n")

    @app.cli.command("category-report")
    @click.option("--days", type=int, default=30, help="Number of days to analyze")
    @click.option("--limit", type=int, default=10, help="Number of categories to show")
    def category_report_command(days: int, limit: int) -> None:
        """Show detailed spending breakdown by category."""
        from datetime import datetime, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        breakdown = UnifiedAnalytics.get_category_breakdown(start_date, end_date, limit=limit)
        
        click.echo(f"\n{'='*80}")
        click.echo(f"Category Breakdown (Last {days} Days)")
        click.echo(f"{'='*80}")
        click.echo(f"{'Category':<25} {'Spent':>12} {'%':>6} {'Items':>7} {'Avg/Item':>12}")
        click.echo(f"{'-'*80}")
        
        for cat in breakdown:
            click.echo(
                f"{cat.category_name:<25} "
                f"${cat.total_spent:>11,.2f} "
                f"{cat.percentage:>5.1f}% "
                f"{cat.item_count:>7} "
                f"${cat.avg_item_price:>11,.2f}"
            )
        
        click.echo(f"{'='*80}\n")
