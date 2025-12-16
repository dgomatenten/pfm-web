#!/usr/bin/env python3
"""
Generate Gmail OAuth2 token for email automation.

Usage:
    python scripts/generate_gmail_token.py

This script will:
1. Read OAuth credentials from environment or prompt
2. Open browser for Google authentication
3. Save token to data/gmail_token.pickle
"""
import os
import pickle
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def generate_token():
    """Generate and save Gmail OAuth2 token."""
    
    # Get credentials from environment
    client_id = os.getenv('GMAIL_CLIENT_ID')
    client_secret = os.getenv('GMAIL_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ Error: Gmail OAuth credentials not found!")
        print("")
        print("Please set these environment variables in .env:")
        print("  GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com")
        print("  GMAIL_CLIENT_SECRET=your-client-secret")
        print("")
        print("To get credentials:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project or select existing")
        print("  3. Enable Gmail API")
        print("  4. Create OAuth 2.0 Client ID (Desktop app)")
        print("  5. Download credentials or copy Client ID and Secret")
        return
    
    print("Gmail OAuth2 Token Generator")
    print("=" * 50)
    print(f"Client ID: {client_id[:30]}...")
    print("")
    
    # Create OAuth flow
    print("Creating OAuth flow...")
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        },
        scopes=SCOPES
    )
    
    print("Opening browser for authentication...")
    print("(If browser doesn't open, copy the URL from terminal)")
    print("")
    
    try:
        # Run local server for OAuth callback
        creds = flow.run_local_server(
            port=0,
            open_browser=True
        )
        
        # Save token
        token_dir = Path('data')
        token_dir.mkdir(exist_ok=True)
        
        token_file = token_dir / 'gmail_token.pickle'
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
        
        print("")
        print("✅ Token generated successfully!")
        print(f"   Saved to: {token_file}")
        print("")
        print("You can now run email sync:")
        print("  flask email-sync sync-now --user-id 1 --days 30")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("")
        print("Troubleshooting:")
        print("  - Make sure you're using correct Client ID and Secret")
        print("  - Check that Gmail API is enabled in Google Cloud Console")
        print("  - Verify OAuth consent screen is configured")
        print("  - Add your email as test user if app is not published")


if __name__ == '__main__':
    generate_token()
