# Amazon Email Automation - Setup Guide

## Implementation Status: ✅ COMPLETE

All code has been implemented. Follow the steps below to configure and start using the email automation system.

---

## Prerequisites

- Python 3.8+ installed
- Access to Google Cloud Console
- Gmail account with Amazon order emails

---

## Step 0: Activate Virtual Environment

**Important:** Always activate the virtual environment before running any commands:
```bash
source /home/dgoma/app_dev/pfm-web/pfm/bin/activate
```

Your prompt should show `(pfm)` when the environment is active.

---

## Step 1: Install Dependencies

With the virtual environment activated, install the required packages:

```bash
cd /home/dgoma/app_dev/pfm-web
source pfm/bin/activate
pip install -r requirements.txt
```

Or install packages individually:

```bash
pip install google-auth>=2.23.0 google-auth-oauthlib>=1.1.0 google-auth-httplib2>=0.1.1
pip install google-api-python-client>=2.100.0 beautifulsoup4>=4.12.0 lxml>=4.9.0
```

---

## Step 2: Run Database Migration

Create the new tables (`email_sync_config`, `email_processing_log`) and update `amazon_orders` table:

```bash
source pfm/bin/activate
flask db upgrade
```

**Expected Output:**
```
INFO  [alembic.runtime.migration] Running upgrade ... -> f8c9d4e5f6a7, add email sync tables
```

---

## Step 3: Set Up Google Cloud Console

### 3.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Note the Project ID

### 3.2 Enable Gmail API

1. In your project, go to **APIs & Services > Library**
2. Search for "Gmail API"
3. Click **Enable**

### 3.3 Create OAuth 2.0 Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Configure consent screen if prompted:
   - User Type: **External** (unless you have Google Workspace)
   - App name: `PFM Amazon Email Sync`
   - User support email: Your email
   - Add scope: `https://www.googleapis.com/auth/gmail.readonly`
   - Add test users: Your Gmail address
4. Application type: **Desktop app**
5. Name: `pfm-email-sync`
6. Click **Create**

### 3.4 Download Credentials

**Option A: Download JSON (Recommended)**
1. Click the download button (⬇) next to your OAuth 2.0 Client ID
2. Save the file as `credentials.json` in the pfm-web root directory

**Option B: Copy Client ID and Secret**
1. Click on your OAuth 2.0 Client ID
2. Copy the **Client ID** and **Client Secret**
3. You'll add these to `.env` in the next step

---

## Step 4: Configure Environment Variables

### Option A: Using credentials.json (Recommended)

If you downloaded `credentials.json`, the OAuth script will read it automatically. Just create/update `.env`:

```bash
# .env file
GMAIL_TOKEN_FILE=data/gmail_token.pickle
```

### Option B: Using Client ID/Secret Directly

If you copied the credentials manually, add them to `.env`:

```bash
# .env file
GMAIL_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret-here
GMAIL_TOKEN_FILE=data/gmail_token.pickle
```

**Create the data directory:**
```bash
mkdir -p data
```

---
## Step 5: Generate OAuth Token

**Important:** Make sure your virtual environment is activated before running these commands.

### Method 1: Using the Standalone Script (Recommended)

```bash
cd /home/dgoma/app_dev/pfm-web
source pfm/bin/activate
python scripts/generate_gmail_token.py
```

### Method 2: Using Flask CLI

```bash
source pfm/bin/activate
flask email-sync setup-oauth
```sk email-sync setup-oauth
```

### What Happens During OAuth Setup:

1. Script opens your browser automatically
2. Sign in with your Gmail account
3. Review permissions (readonly access to Gmail)
4. Click **Allow**
5. Browser shows "The authentication flow has completed"
6. Token saved to `data/gmail_token.pickle`

**Common Issues:**

- **"Access blocked: This app's request is invalid"**
  - Make sure you added your email as a test user in the OAuth consent screen
  
- **"Redirect URI mismatch"**
  - Use Desktop app type (not Web application)

- **Browser doesn't open**
## Step 6: Test the Email Parser (Optional)

If you have a sample Amazon order email saved as HTML:

```bash
source pfm/bin/activate
flask email-sync test-parser path/to/amazon_email.html
```

This will show you what data the parser extracts without actually syncing.

---

## Step 7: Run Your First Sync

Sync Amazon orders from the last 7 days for user ID 1:

```bash
source pfm/bin/activate
flask email-sync sync-now --user-id 1 --days 7
```c Amazon orders from the last 7 days for user ID 1:

```bash
flask email-sync sync-now --user-id 1 --days 7
```

**Example Output:**
```
Syncing Amazon orders from last 7 days for user ID: 1
Found 5 Amazon order emails
Processing: Order #123-4567890-1234567 (2025-12-10)
  ✓ Created order with 2 items
Processing: Order #123-9876543-7654321 (2025-12-11)
  ⚠ Order already exists (skipped)
...
Sync completed: 3 new orders, 2 skipped
```

### Sync Options:

- `--user-id`: Your user ID in the database (required)
- `--days`: How many days back to search (default: 7)
- `--max-results`: Maximum emails to fetch (default: 100)

## Step 8: Set Up Automated Syncing (Optional)

### Option A: Cron Job (Linux/Mac)

Add to crontab to sync daily at 6 AM:

```bash
crontab -e
```

Add line:
```
0 6 * * * cd /home/dgoma/app_dev/pfm-web && /home/dgoma/app_dev/pfm-web/pfm/bin/flask email-sync sync-now --user-id 1 --days 1 >> /var/log/pfm-email-sync.log 2>&1
```
0 6 * * * cd /home/dgoma/app_dev/pfm-web && /path/to/venv/bin/flask email-sync sync-now --user-id 1 --days 1 >> /var/log/pfm-email-sync.log 2>&1
```

### Option B: systemd Timer (Linux)

Create `/etc/systemd/system/pfm-email-sync.service`:

```ini
[Unit]
Description=PFM Amazon Email Sync
After=network.target

[Service]
Type=oneshot
User=dgoma
WorkingDirectory=/home/dgoma/app_dev/pfm-web
Environment="PATH=/home/dgoma/app_dev/pfm-web/pfm/bin:/usr/bin:/bin"
ExecStart=/home/dgoma/app_dev/pfm-web/pfm/bin/flask email-sync sync-now --user-id 1 --days 1
```

Create `/etc/systemd/system/pfm-email-sync.timer`:

```ini
[Unit]
Description=Daily PFM Email Sync
Requires=pfm-email-sync.service

[Timer]
OnCalendar=daily
OnCalendar=06:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable pfm-email-sync.timer
sudo systemctl start pfm-email-sync.timer
```

---

## Verification Checklist

- [ ] Virtual environment activated (`source pfm/bin/activate`)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Database migrated (`flask db upgrade`)
- [ ] Google Cloud project created
- [ ] Gmail API enabled
- [ ] OAuth 2.0 credentials created
- [ ] Credentials configured in `.env` or `credentials.json`
- [ ] OAuth token generated (`gmail_token.pickle` exists)
- [ ] Test sync successful (`flask email-sync sync-now`)
- [ ] Orders visible in database/web interface

---

## Troubleshooting

### Token Expired

If you see "Token has been expired or revoked":

```bash
source pfm/bin/activate
rm data/gmail_token.pickle
python scripts/generate_gmail_token.py
```

### No Emails Found

1. Check Gmail search query in logs
2. Verify emails exist: Search Gmail for `from:auto-confirm@amazon.com`
3. Try increasing `--days` parameter
### Parser Errors

1. Save failing email as HTML file
2. Test parser: `source pfm/bin/activate && flask email-sync test-parser email.html`
3. Check logs in `email_processing_log` table for specific errors

### Database Issues

Check if migration ran:
```bash
source pfm/bin/activate
flask db current
```

Should show: `f8c9d4e5f6a7 (head)`
Should show: `f8c9d4e5f6a7 (head)`

---

## Architecture Overview

### Components Created:

1. **pfm_web/services/email_sync/gmail_client.py**
   - Gmail API OAuth2 client
   - Email fetching and search

2. **pfm_web/services/email_sync/email_parser.py**
   - Amazon email HTML parsing
   - Order/item data extraction

3. **pfm_web/services/email_sync/sync_service.py**
   - Orchestration: fetch → parse → save
   - Deduplication via message IDs

4. **pfm_web/cli/email_sync_commands.py**
   - Flask CLI commands
   - User-friendly interface

5. **scripts/generate_gmail_token.py**
   - Standalone OAuth token generator
   - One-time setup script

6. **Database Tables:**
   - `email_sync_config` - OAuth tokens and settings
   - `email_processing_log` - Deduplication and error tracking
   - `amazon_orders` - Extended with source tracking

---

## Security Notes

- `gmail_token.pickle` contains OAuth refresh token - **DO NOT COMMIT**
- `credentials.json` contains OAuth credentials - **DO NOT COMMIT**
- Add to `.gitignore`:
  ```
  data/gmail_token.pickle
  credentials.json
  ```
- Token has readonly Gmail access only
- OAuth consent screen limits access to test users

---

## Support

For detailed implementation information, see `AMAZON_EMAIL_AUTOMATION_PLAN.md`

For issues:
1. Check logs: `email_processing_log` table
2. Test parser with sample email
3. Verify OAuth token is valid
4. Check Gmail API quota (10,000 queries/day)
