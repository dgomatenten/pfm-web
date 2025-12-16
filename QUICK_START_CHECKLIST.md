# Amazon Email Automation - Quick Start Checklist

Use this checklist to get the email automation system up and running.

---

## Pre-Implementation (✅ COMPLETE)

- [x] Design document created
- [x] Core services implemented (gmail_client, email_parser, sync_service)
- [x] Database migration created
- [x] Flask CLI commands implemented
- [x] OAuth token generator script created
- [x] Configuration files updated
- [x] Dependencies added to requirements.txt

---

## Configuration Steps (⚠️ ACTION REQUIRED)

### Step 1: Install Dependencies
```bash
cd /home/dgoma/app_dev/pfm-web
pip install -r requirements.txt
```
- [ ] Dependencies installed successfully

### Step 2: Run Database Migration
```bash
flask db upgrade
```
- [ ] Migration completed (check for "f8c9d4e5f6a7" in output)
- [ ] Tables created: `email_sync_config`, `email_processing_log`
- [ ] `amazon_orders` table updated with new columns

### Step 3: Google Cloud Console Setup

#### 3.1 Create Project
- [ ] Go to https://console.cloud.google.com/
- [ ] Create new project or select existing
- [ ] Note project ID: ________________

#### 3.2 Enable Gmail API
- [ ] Navigate to APIs & Services > Library
- [ ] Search for "Gmail API"
- [ ] Click Enable

#### 3.3 Create OAuth Credentials
- [ ] Go to APIs & Services > Credentials
- [ ] Click "Configure consent screen"
  - [ ] User Type: External
  - [ ] App name: PFM Amazon Email Sync
  - [ ] Add scope: `https://www.googleapis.com/auth/gmail.readonly`
  - [ ] Add test users: Your Gmail address
- [ ] Click "Create Credentials > OAuth client ID"
  - [ ] Application type: Desktop app
  - [ ] Name: pfm-email-sync
- [ ] Download credentials.json OR copy Client ID/Secret

#### 3.4 Save Credentials
**Option A (Recommended):**
- [ ] Save `credentials.json` to `/home/dgoma/app_dev/pfm-web/credentials.json`

**Option B:**
- [ ] Add to `.env`:
  ```
  GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
  GMAIL_CLIENT_SECRET=your-client-secret
  ```

### Step 4: Create Data Directory
```bash
mkdir -p /home/dgoma/app_dev/pfm-web/data
```
- [ ] Directory created

### Step 5: Update .gitignore
Add these lines to `.gitignore`:
```
credentials.json
data/gmail_token.pickle
```
- [ ] .gitignore updated

### Step 6: Generate OAuth Token

**Method 1 (Recommended):**
```bash
python scripts/generate_gmail_token.py
```

**Method 2:**
```bash
flask email-sync setup-oauth
```

- [ ] Script started successfully
- [ ] Browser opened automatically (or copied URL manually)
- [ ] Signed in with Gmail account
- [ ] Clicked "Allow" on permissions screen
- [ ] Token saved to `data/gmail_token.pickle`

### Step 7: Test the System

#### 7.1 Test Parser (Optional)
If you have a sample Amazon email saved:
```bash
flask email-sync test-parser path/to/email.html
```
- [ ] Parser extracted order data correctly

#### 7.2 Run First Sync
```bash
flask email-sync sync-now --user-id 1 --days 7
```
- [ ] Command ran without errors
- [ ] Found Amazon emails
- [ ] Orders imported to database
- [ ] Check output for counts (X new orders, Y skipped)

#### 7.3 Verify in Database
```bash
flask shell
>>> from pfm_web.models import AmazonOrder
>>> AmazonOrder.query.filter_by(source_type='email').count()
>>> exit()
```
- [ ] Orders visible in database
- [ ] `source_type` = 'email'
- [ ] `email_message_id` populated

#### 7.4 Check Web Interface
- [ ] Start Flask app: `flask run`
- [ ] Navigate to Amazon orders page
- [ ] Verify email-imported orders appear correctly

---

## Optional: Set Up Automated Syncing

### Option A: Cron Job
```bash
crontab -e
```
Add line (sync daily at 6 AM):
```
0 6 * * * cd /home/dgoma/app_dev/pfm-web && /path/to/venv/bin/flask email-sync sync-now --user-id 1 --days 1 >> /var/log/pfm-email-sync.log 2>&1
```
- [ ] Cron job added
- [ ] Test cron job runs correctly

### Option B: systemd Timer
See `AMAZON_EMAIL_SETUP_GUIDE.md` for detailed instructions.
- [ ] Service file created
- [ ] Timer file created
- [ ] Timer enabled and started

---

## Troubleshooting

### Issue: "pip install fails"
- [ ] Check Python version: `python --version` (requires 3.8+)
- [ ] Try with virtual environment: `python -m venv venv && source venv/bin/activate`
- [ ] Install one package at a time to identify problem

### Issue: "flask db upgrade fails"
- [ ] Check Flask environment: `echo $FLASK_APP`
- [ ] Set if needed: `export FLASK_APP=pfm_web`
- [ ] Verify database path in config
- [ ] Check migration file syntax

### Issue: "Token expired or revoked"
- [ ] Delete token: `rm data/gmail_token.pickle`
- [ ] Regenerate: `python scripts/generate_gmail_token.py`

### Issue: "No emails found"
- [ ] Check Gmail manually: Search for `from:auto-confirm@amazon.com`
- [ ] Verify date range: Try `--days 30` for wider search
- [ ] Check OAuth scope includes gmail.readonly

### Issue: "Parser errors"
- [ ] Save failing email as HTML
- [ ] Test: `flask email-sync test-parser failing_email.html`
- [ ] Check `email_processing_log` table for error details
- [ ] Report parsing pattern issues for investigation

---

## Verification Checklist

- [ ] Dependencies installed
- [ ] Database migrated
- [ ] Google Cloud project created
- [ ] Gmail API enabled
- [ ] OAuth credentials created
- [ ] credentials.json downloaded (or env vars set)
- [ ] OAuth token generated
- [ ] Test sync successful
- [ ] Orders visible in database
- [ ] Orders visible in web interface
- [ ] .gitignore updated

---

## Success! What's Next?

Once all checkboxes are complete:

1. **Regular Usage:**
   - Run `flask email-sync sync-now --user-id 1 --days 1` daily
   - Or set up automated cron/systemd timer

2. **Monitor:**
   - Check `email_processing_log` table for errors
   - Review parsed orders for accuracy

3. **Optimize:**
   - Adjust sync frequency based on order volume
   - Fine-tune `--days` and `--max-results` parameters

4. **Enhance:**
   - Add multiple Gmail accounts
   - Implement web UI for OAuth setup
   - Create sync status dashboard

---

## Support

- **Detailed Setup:** `AMAZON_EMAIL_SETUP_GUIDE.md`
- **Implementation Details:** `AMAZON_EMAIL_IMPLEMENTATION_SUMMARY.md`
- **Architecture/Design:** `AMAZON_EMAIL_AUTOMATION_PLAN.md`
