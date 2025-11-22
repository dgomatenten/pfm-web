# Analytics Dashboard

## 🎉 Your Analytics Dashboard is Ready!

The web-based analytics dashboard has been successfully created and is now accessible.

## 📊 Features

The dashboard provides comprehensive analytics combining both receipt and Amazon order data:

### Summary Cards
- **Total Spent**: Combined spending across all sources
- **Transactions**: Total number of purchases
- **Items**: Total products purchased
- **Average per Transaction**: Average spending per purchase

### Interactive Charts
1. **Spending by Category** (Doughnut Chart)
   - Visual breakdown of spending across different categories
   - Interactive with hover details

2. **Spending by Source** (Bar Chart)
   - Compare spending between Receipts and Amazon orders
   - Side-by-side comparison

3. **Spending Trend** (Line Chart)
   - Daily spending trend over the last 30 days
   - Smooth curve showing spending patterns

### Detailed Category Table
- Category-by-category breakdown
- Shows: Total spent, percentage, item count, transaction count, average per item
- Sortable and easy to read

## 🚀 How to Access

### 1. Start the Flask Server (if not already running)
```bash
cd /home/dgoma/app_dev/pfm-web
/home/dgoma/app_dev/pfm-web/pfm/bin/python3 -m flask run --host=0.0.0.0 --port=5000
```

### 2. Open in Your Browser
Navigate to one of these URLs:
- **Local**: http://127.0.0.1:5000/analytics
- **Network**: http://10.0.0.19:5000/analytics

## 🎛️ Dashboard Controls

### Time Period Filter
Select different time ranges to analyze:
- Last 7 Days
- Last 30 Days
- Last 90 Days
- Last 6 Months
- Last Year (default)

Click **Refresh Data** button to reload analytics with the selected time period.

## 📡 API Endpoints

The dashboard uses these REST API endpoints (you can use them directly too):

### 1. Spending Summary
```bash
GET /api/analytics/summary?days=365
```
Returns overall spending summary with totals and breakdowns.

### 2. Category Breakdown
```bash
GET /api/analytics/categories?days=365
```
Returns detailed spending by category with percentages.

### 3. Time Series
```bash
GET /api/analytics/time-series?days=30&group_by=day
```
Returns spending trends grouped by day/week/month/year.

### 4. Compare Sources
```bash
GET /api/analytics/compare-sources?days=365
```
Returns comparison between receipts and Amazon orders.

### 5. Top Merchants
```bash
GET /api/analytics/merchants?days=365&limit=10
```
Returns top spending merchants/vendors.

### 6. Monthly Trends
```bash
GET /api/analytics/monthly-trends
```
Returns 12-month spending trends with direction indicators.

## 🧪 Testing API Endpoints

### Using curl:
```bash
# Get summary
curl http://127.0.0.1:5000/api/analytics/summary?days=365

# Get category breakdown
curl http://127.0.0.1:5000/api/analytics/categories?days=90

# Get time series
curl http://127.0.0.1:5000/api/analytics/time-series?days=30&group_by=day
```

### Using browser:
Just paste the URL in your browser:
```
http://127.0.0.1:5000/api/analytics/summary?days=365
```

## 🎨 Dashboard Features

### Responsive Design
- Works on desktop, tablet, and mobile
- Charts automatically resize
- Grid layout adjusts to screen size

### Interactive Charts
- Hover over charts for detailed information
- Charts use Chart.js library for smooth animations
- Color-coded for easy identification

### Real-time Data
- All data is fetched from the database in real-time
- Click "Refresh Data" to update with latest information
- No caching - always shows current data

## 📈 Current Data Summary

Based on the last test (365 days):
- **Total Spending**: $414,494.02
  - Receipts: $406,008.83 (98.0%)
  - Amazon: $8,485.19 (2.0%)
- **Transactions**: 467 total
- **Items**: 1,231 total
- **Top Categories**:
  1. Food & Beverages: $4,313.83 (61.6%)
  2. Home & Kitchen: $850.28 (12.1%)
  3. Health & Personal Care: $824.33 (11.8%)

## 🔧 CLI Commands

You can also access analytics via command line:

### Spending Summary
```bash
cd /home/dgoma/app_dev/pfm-web
/home/dgoma/app_dev/pfm-web/pfm/bin/python3 -m flask spending-summary --days 365
```

### Category Report
```bash
/home/dgoma/app_dev/pfm-web/pfm/bin/python3 -m flask category-report --days 365 --limit 15
```

## 📂 File Locations

- **Dashboard HTML**: `pfm_web/templates/analytics_dashboard.html`
- **Analytics Logic**: `pfm_web/analytics.py`
- **API Endpoints**: `pfm_web/analytics_api.py`
- **Web Routes**: `pfm_web/web/views.py`

## 🔮 Future Enhancements

Potential improvements you can add:
- Export data to CSV/Excel
- Date range picker (custom dates)
- More chart types (heatmaps, scatter plots)
- Budget tracking and alerts
- Merchant-level analysis
- Category comparison over time
- Spending predictions using ML
- Multi-user support with filters

## 🐛 Troubleshooting

### Server not running?
Make sure Flask is running:
```bash
/home/dgoma/app_dev/pfm-web/pfm/bin/python3 -m flask run --host=0.0.0.0 --port=5000
```

### Page shows "Failed to load analytics data"?
Check if:
1. Flask server is running
2. Database file exists at `pfm.db`
3. Check browser console for errors (F12)

### Charts not displaying?
- Check browser console for JavaScript errors
- Ensure Chart.js CDN is accessible
- Try refreshing the page

## 🎯 Quick Start

1. **Start server**: `/home/dgoma/app_dev/pfm-web/pfm/bin/python3 -m flask run --host=0.0.0.0 --port=5000`
2. **Open browser**: http://127.0.0.1:5000/analytics
3. **Enjoy your analytics!** 📊✨

---

**Happy Analyzing!** 🚀💰
