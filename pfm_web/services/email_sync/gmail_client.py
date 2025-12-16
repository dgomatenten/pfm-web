"""Gmail client using OAuth2 or IMAP."""
from __future__ import annotations

import base64
import pickle
from pathlib import Path
from typing import Iterator, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GmailClient:
    """Gmail API client with OAuth2 authentication."""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, token_file: Path):
        self.token_file = Path(token_file)
        self.creds = self._load_credentials()
        self.service = build('gmail', 'v1', credentials=self.creds)
    
    def _load_credentials(self) -> Credentials:
        """Load and refresh OAuth2 credentials."""
        if not self.token_file.exists():
            raise FileNotFoundError(
                f"Token file not found: {self.token_file}\n"
                f"Run 'flask email-sync setup-oauth' to generate token."
            )
        
        with open(self.token_file, 'rb') as token:
            creds = pickle.load(token)
        
        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return creds
    
    def search_amazon_emails(
        self, 
        after_date: Optional[str] = None,
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
            'from:(auto-confirm@amazon.com OR ship-confirm@amazon.com OR order-update@amazon.com)',
            'subject:(order OR shipped OR confirmation)',
        ]
        
        if after_date:
            query_parts.append(f'after:{after_date}')
        
        query = ' '.join(query_parts)
        
        try:
            # Search messages
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            for message_ref in messages:
                try:
                    # Fetch full message
                    msg = self.service.users().messages().get(
                        userId='me',
                        id=message_ref['id'],
                        format='full'
                    ).execute()
                    
                    yield self._parse_message(msg)
                except Exception as e:
                    print(f"Error fetching message {message_ref['id']}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error searching messages: {e}")
            raise
    
    def _parse_message(self, msg: dict) -> dict:
        """Parse Gmail API message into simplified dict."""
        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        
        # Extract body
        body_html = None
        body_text = None
        
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/html':
                    body_data = part['body'].get('data')
                    if body_data:
                        body_html = self._decode_body(body_data)
                elif part['mimeType'] == 'text/plain':
                    body_data = part['body'].get('data')
                    if body_data:
                        body_text = self._decode_body(body_data)
                elif 'parts' in part:  # Nested parts (multipart/alternative)
                    for subpart in part['parts']:
                        if subpart['mimeType'] == 'text/html':
                            body_data = subpart['body'].get('data')
                            if body_data:
                                body_html = self._decode_body(body_data)
                        elif subpart['mimeType'] == 'text/plain':
                            body_data = subpart['body'].get('data')
                            if body_data:
                                body_text = self._decode_body(body_data)
        else:
            # Single part message
            body_data = msg['payload']['body'].get('data')
            if body_data:
                mime_type = msg['payload'].get('mimeType')
                decoded = self._decode_body(body_data)
                if mime_type == 'text/html':
                    body_html = decoded
                else:
                    body_text = decoded
        
        return {
            'id': msg['id'],
            'message_id': headers.get('Message-ID', ''),
            'subject': headers.get('Subject', ''),
            'from': headers.get('From', ''),
            'date': headers.get('Date', ''),
            'body_html': body_html,
            'body_text': body_text,
        }
    
    @staticmethod
    def _decode_body(data: str) -> str:
        """Decode base64url encoded message body."""
        try:
            return base64.urlsafe_b64decode(data).decode('utf-8')
        except Exception as e:
            print(f"Error decoding body: {e}")
            return ""


def setup_oauth_interactive(client_id: str, client_secret: str, token_file: Path) -> Path:
    """
    Interactive OAuth2 setup for Gmail API.
    
    Args:
        client_id: Google OAuth2 client ID
        client_secret: Google OAuth2 client secret
        token_file: Path to save token
        
    Returns:
        Path to saved token file
    """
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    # Create OAuth flow
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
        scopes=GmailClient.SCOPES
    )
    
    # Run local server for OAuth callback
    creds = flow.run_local_server(port=0)
    
    # Save credentials
    token_path = Path(token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(token_path, 'wb') as token:
        pickle.dump(creds, token)
    
    return token_path
