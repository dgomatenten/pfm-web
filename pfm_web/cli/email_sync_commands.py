"""Flask CLI commands for email sync."""
import click
from flask import current_app
from flask.cli import with_appcontext
from pathlib import Path

from ..services.email_sync.sync_service import EmailSyncService
from ..services.email_sync.gmail_client import setup_oauth_interactive


@click.group()
def email_sync():
    """Email sync management commands."""
    pass


@email_sync.command()
@click.option('--user-id', required=True, type=int, help='User ID to sync for')
@click.option('--days', default=30, help='Days back to sync (default: 30)')
@with_appcontext
def sync_now(user_id, days):
    """Manually trigger email sync for a user."""
    token_file = Path(current_app.config.get('GMAIL_TOKEN_FILE', 'data/gmail_token.pickle'))
    
    if not token_file.exists():
        click.echo(f"❌ Token file not found: {token_file}")
        click.echo("Run 'flask email-sync setup-oauth' first")
        return
    
    click.echo(f"Starting email sync for user {user_id}...")
    click.echo(f"Searching for Amazon emails from last {days} days...")
    
    try:
        service = EmailSyncService(user_id, token_file)
        stats = service.sync_orders(days_back=days)
        
        click.echo(f"\n✅ Sync completed!")
        click.echo(f"   Emails processed: {stats['emails_processed']}")
        click.echo(f"   Orders created: {stats['orders_created']}")
        click.echo(f"   Orders updated: {stats['orders_updated']}")
        click.echo(f"   Orders skipped: {stats['orders_skipped']}")
        
        if stats['errors']:
            click.echo(f"\n⚠️  Errors: {len(stats['errors'])}")
            for error in stats['errors'][:5]:  # Show first 5
                click.echo(f"     - {error}")
    except Exception as e:
        click.echo(f"❌ Sync failed: {e}")
        raise


@email_sync.command()
@with_appcontext
def setup_oauth():
    """Interactive OAuth2 setup for Gmail."""
    client_id = current_app.config.get('GMAIL_CLIENT_ID')
    client_secret = current_app.config.get('GMAIL_CLIENT_SECRET')
    token_file = Path(current_app.config.get('GMAIL_TOKEN_FILE', 'data/gmail_token.pickle'))
    
    if not client_id or not client_secret:
        click.echo("❌ Gmail OAuth credentials not configured!")
        click.echo("Please set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env")
        return
    
    click.echo("Starting Gmail OAuth2 setup...")
    click.echo("This will open a browser window for authentication.")
    click.echo("")
    
    try:
        token_path = setup_oauth_interactive(client_id, client_secret, token_file)
        click.echo(f"\n✅ OAuth2 token saved to: {token_path}")
        click.echo("You can now run: flask email-sync sync-now --user-id 1")
    except Exception as e:
        click.echo(f"❌ OAuth setup failed: {e}")
        raise


@email_sync.command()
@click.argument('email_file', type=click.Path(exists=True))
@with_appcontext
def test_parser(email_file):
    """Test email parser with a sample email HTML file."""
    from ..services.email_sync.email_parser import AmazonEmailParser
    
    click.echo(f"Testing parser with: {email_file}")
    
    with open(email_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    parser = AmazonEmailParser()
    result = parser.parse_email(html_content)
    
    if result:
        click.echo(f"\n✅ Successfully parsed order!")
        click.echo(f"   Order ID: {result.order_id}")
        click.echo(f"   Order Date: {result.order_date}")
        click.echo(f"   Total: ${result.total_amount:.2f} {result.currency}")
        click.echo(f"   Status: {result.shipment_status}")
        click.echo(f"   Items: {len(result.items)}")
        
        for i, item in enumerate(result.items, 1):
            click.echo(f"      {i}. {item.name}")
            click.echo(f"         Qty: {item.quantity}, Price: ${item.price:.2f}")
            if item.asin:
                click.echo(f"         ASIN: {item.asin}")
    else:
        click.echo("❌ Failed to parse email")


def init_app(app):
    """Register CLI commands with Flask app."""
    app.cli.add_command(email_sync)
