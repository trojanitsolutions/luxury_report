# Sales Person Wise Sales Report — Implementation

## Overview

The **Sales Person Wise Sales** report has been transformed into a comprehensive **Salesperson Performance Dashboard** with:
- Dynamic filters across Company, Sales Person, dates, territories, item groups, brands, warehouses, projects, cost centers, and document statuses
- 12 KPI summary cards (Total Orders, Amounts, Achievements, etc.)
- Main performance table with 20 columns per salesperson (sortable, column-hideable)
- Multi-salesperson Comparison Dashboard
- Individual Performance Analysis (drill-down on single salesperson with Daily/Weekly/Monthly/Quarterly/Yearly trends)
- Historical YoY/MoM/WoW analysis
- 10 interactive Frappe Charts that update on every filter change
- Professional 7-sheet Excel export with proper formatting (freeze panes, currency formatting, headers, totals)

## Architecture

### File Structure

```
luxury_report/report/sales_person_wise_sales/
├── sales_person_wise_sales.py       # Main report entry point (execute, get_columns, get_dashboard_data endpoint)
├── queries.py                        # All SQL/Query Builder access (6 aggregate queries)
├── analytics.py                      # Pure Python data derivation (main table, KPIs, charts, individual perf, historical)
├── excel_export.py                   # Excel workbook generation (7 sheets, formatting, download endpoint)
├── sales_person_wise_sales.js        # Filters, injected dashboard sections, chart rendering
├── sales_person_wise_sales.json      # Report metadata (no changes needed)
└── __init__.py                       # Package marker
```

### Data Flow

```
execute(filters)
├── Call 6 queries (SO/SI/DN totals + trends)
├── Derive main_table, kpis, native_chart via analytics
└── Return (columns, data, message, chart, report_summary)

get_dashboard_data(filters) [whitelisted endpoint, called from JS on every filter change]
├── Call same 6 queries
├── Derive comparison, individual_performance, extra_charts
└── Return JSON with all dashboard sections

download_excel(filters_json) [whitelisted endpoint, called on Excel button click]
├── Call 6 queries
├── Derive all data
├── Build 7-sheet workbook with xlsxwriter
└── Stream as binary download
```

## Query Strategy (Optimized for Large Datasets)

**Total cost: 6 SQL queries per request (execute + get_dashboard_data = 12 queries per filter change), O(1) regardless of date range or salesperson count.**

### Query 1-3: Totals by Salesperson

```sql
SELECT st.sales_person,
    COUNT(DISTINCT dt.name) as so_count,
    COUNT(DISTINCT dt.customer) as customer_count,
    SUM(dt_item.base_net_amount * st.allocated_percentage / 100) as so_amount,
    ...status breakdowns...
FROM `tabSales Order` dt
INNER JOIN `tabSales Order Item` dt_item ON dt_item.parent = dt.name
INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Sales Order'
WHERE ...filters...
GROUP BY st.sales_person
```

**Key points:**
- Distinct counts (`COUNT(DISTINCT dt.name)`) prevent double-counting from item×team join
- Amount allocation via `base_net_amount * allocated_percentage / 100` (allocated percentages sum to 100)
- Replicated for Sales Invoice and Delivery Note with respective field names

### Query 4-6: Daily Trend by Salesperson

```sql
SELECT st.sales_person, dt.transaction_date, 
    COUNT(DISTINCT dt.name) as so_count,
    SUM(...weighted amounts...) as so_amount
GROUP BY st.sales_person, dt.transaction_date
ORDER BY dt.transaction_date
```

**Single source for all trend/grouping needs** — Python re-buckets daily rows into Week/Month/Quarter/Year as requested, avoiding separate queries per grouping.

### Filter Handling

- **Item-level filters** (Item Group, Brand, Warehouse) apply as simple `WHERE item.<field> IN (...)` (no extra joins to `tabItem` needed — fields are denormalized onto child rows)
- **Hierarchical filters** (Sales Person, Item Group) expand via lft/rgt nested-set columns before building SQL placeholders
- **Date filters** resolved in precedence order: explicit From/To > Date Range preset > Fiscal Year > default (current FY)
- **Company, Customer, Territory, Cost Center, Project** filter directly at header level

## Analytics (Pure Python — No DB Access)

### build_main_table()
Merges SO/SI/DN totals per salesperson, computes:
- `Difference = SO Amount - SI Amount` (uninvoiced remainder)
- `Invoice Conversion % = SI Amount / SO Amount * 100`
- `Delivery Conversion % = Delivered Amount / SO Amount * 100`
- `Achievement % = Invoice Conversion %` (per spec)
- `Average Order Value = SO Amount / SO Count`

Returns: `List[dict]` with 20 fields per salesperson row.

### build_kpis()
12 KPI cards (Total Orders, Amounts, Achievements, Customers, Monthly Averages, High/Low months, etc.).

Structure:
```python
{
    "value": float,
    "indicator": "Green"/"Red"/"Blue"/"Grey",
    "label": _("Human-readable label"),
    "datatype": "Currency"/"Int"/"Percent"
}
```

### build_individual_performance()
Single-salesperson drill-down. Selects that salesperson's trend rows, buckets by grouping (Daily/Weekly/Monthly/Quarterly/Yearly), computes:
- Average sales, invoices, delivered amounts
- Moving average (3-period)
- Growth % from last period
- Best/worst month/week
- Performance Score (weighted composite: 40% achievement, 30% delivery, 20% growth, 10% order count)

### build_historical_analysis()
YoY/MoM/WoW comparison. Aggregates by month, computes growth rates.

### build_extra_charts()
9 chart datasets (Salesperson Comparison, Monthly/Weekly Trends, Delivery Status Distribution, Invoice Conversion Trend, Top Performers, YoY Comparison, Monthly Heatmap, Achievement Gauge).

All use `frappe.Chart()` compatible data format:
```python
{
    "data": {
        "labels": [...],
        "datasets": [{"name": "...", "values": [...]}]
    },
    "type": "bar|line|pie|percentage|heatmap",
    "barOptions": {...}
}
```

## JavaScript Frontend

### Filters
- **Link fields** (Company, Customer, Territory, Item Group, Brand, Warehouse, Project, Cost Center): standard Link input
- **MultiSelectList fields** (Sales Person, SO/Invoice/Delivery Status): multi-select with fetched options
- **Select fields** (Grouping, Comparison Mode): dropdown
- **Date fields** (From/To): date pickers
- **Link fields with hierarchy** (Sales Person, Item Group): auto-expanded via `_resolve_*_hierarchy()` in Python (user sees individual names, server expands to include child groups)

### Dashboard Sections
Injected into `report.page.main` after the native datatable:

1. **Comparison Dashboard** — Multi-salesperson table (Rank, Amounts, Differences, Achievements, Growth, Variance)
2. **Individual Performance** — Single-salesperson drill-down with Grouping toggle buttons and trend metrics
3. **Historical Analysis** — YoY/MoM/WoW growth table
4. **Chart Grid** — 8 additional charts (monthly trend, weekly trend, delivery status, conversion trend, top performers, YoY, heatmap, achievement gauge)

### Refresh Behavior
- **Native report components** (KPI cards, datatable, native SO vs SI chart) update via framework's native `execute()` refresh
- **Injected dashboard sections** update via one combined `frappe.call` to `get_dashboard_data()` in the `after_refresh()` hook (fires on every filter change)
- **Section visibility** controlled client-side off the `comparison_mode` filter (no extra request needed)

## Excel Export

**7 sheets, sourced from analytics outputs (no fresh queries):**

1. **Summary** — KPI list
2. **Performance** — Main table
3. **Comparison** — Comparison table
4. **Monthly Breakdown** — Aggregated by month
5. **Weekly Breakdown** — Aggregated by week
6. **Raw Data** — Flattened trend rows (Date, Salesperson, DocType, Amount)
7. **Chart Data** — Salesperson × SO Amount (chart source data)

**Formatting:**
- Bold headers with blue background, white text
- Currency formatting on amount columns
- Freeze panes (row 1 locked, columns A locked)
- Autofilter on all columns
- Totals row (sums on amount columns)
- Auto column width (content-based heuristic)

**Implementation:** Built with `xlsxwriter` directly (not `frappe.utils.xlsxutils.make_xlsx`) to support freeze panes and autofilter — reuses style-dict shapes from `XLSXStyleBuilder` for consistency.

## Formula Definitions

- **Achievement %** = `SI Amount / SO Amount * 100` (zero-guarded)
- **Delivery Conversion %** = `Delivered Amount / SO Amount * 100` (zero-guarded)
- **Difference** = `SO Amount - SI Amount`
- **Difference %** = `Difference / SO Amount * 100` (zero-guarded)
- **Ranking** = SO Amount descending; **Variance** = salesperson's SO Amount − group mean
- **Performance Score** = `0.4*achievement% + 0.3*delivery_conversion% + 0.2*clamp(growth%,0,100) + 0.1*normalized(order_count)`
- **Growth %** = `(current - previous) / previous * 100` (zero-guarded)
- **Moving Average** = trailing 3-period mean

## Verification Steps

### Before First Use

1. **Ensure app is installed:**
   ```bash
   bench --site local.com install-app luxury_report
   bench --site local.com migrate
   bench --site local.com clear-cache
   ```

2. **Verify files are in place:**
   ```bash
   ls -l apps/luxury_report/luxury_report/luxury_report/report/sales_person_wise_sales/
   ```
   Should show: `queries.py`, `analytics.py`, `excel_export.py`, `sales_person_wise_sales.py`, `sales_person_wise_sales.js`, `sales_person_wise_sales.json`, `__init__.py`

3. **Check Python syntax:**
   ```bash
   python3 -m py_compile apps/luxury_report/luxury_report/luxury_report/report/sales_person_wise_sales/*.py
   ```

4. **Start the development server:**
   ```bash
   bench start
   ```

### During First Access

1. Open `/app/query-report/Sales Person Wise Sales` in a browser (must be logged in as a user with Sales Manager/Sales User/Accounts User role)

2. **Verify all 14 filters appear and are functional:**
   - Company (Link)
   - Sales Person (MultiSelectList with group expansion)
   - Fiscal Year, From Date, To Date
   - Customer, Territory, Item Group, Brand, Warehouse, Project, Cost Center
   - SO Status, Delivery Status, Invoice Status (multi-select)
   - Grouping (Select: Daily/Weekly/Monthly/Quarterly/Yearly)
   - Comparison Mode (Select: Compare Salespersons / Individual Salesperson)
   - Top N Salespersons (Int)

3. **Verify native components:**
   - 12 KPI cards appear at the top (Total Orders, Amounts, Achievements, etc.) — check indicator colors (Green/Blue/Red based on thresholds)
   - One native chart (SO vs SI, bar chart by month) renders below KPIs
   - Main datatable appears with 20 columns — click column headers to sort, right-click for column picker

4. **Verify injected dashboard (switching between modes):**
   - Change `Comparison Mode` to "Compare Salespersons" — see Comparison Dashboard table and 8 extra charts grid
   - Change `Comparison Mode` to "Individual Salesperson", select exactly one Sales Person — Comparison Dashboard hides, Individual Performance section shows with Grouping toggle buttons and trend metrics
   - Test grouping toggle (Daily/Weekly/Monthly/Quarterly/Yearly) — metrics and trend chart update

5. **Verify filter reactivity:**
   - Change any filter — entire report (table, KPIs, all charts) refreshes in place
   - Network tab should show exactly 2 requests: one to framework's report endpoint, one to `get_dashboard_data`

6. **Verify Excel export:**
   - Click "Download Excel" button
   - Browser downloads `.xlsx` file
   - Open in Excel/LibreOffice — all 7 sheets present, headers bold, columns frozen, formatting applied, totals row visible

### With Real Data

1. **Sanity-check allocation:**
   - Find a Sales Order with a 2-person Sales Team (e.g., 60/40 split)
   - Sum of that SO's amount per person should = order's `base_grand_total` with no rounding loss
   - SO count for each person should be 1 (not inflated by item×team join)

2. **Verify currency:**
   - All amounts displayed in company base currency (no transaction-specific currency shown in report, even if SO/SI are multi-currency)

3. **Check date filter interactions:**
   - Set Fiscal Year → should override From/To
   - Set explicit From/To → should override Fiscal Year
   - Verify date range spans full selected periods

4. **Performance test:**
   - Run report with large date range (e.g., 3 years) and multiple salespersons
   - Should load in <5 seconds on typical hardware (6 aggregation queries + Python derivation is O(1) in call count)
   - No N+1 queries, no per-salesperson or per-KPI additional queries

## Known Limitations & Design Choices

1. **Monthly Heatmap** — Uses GitHub-style calendar heatmap (day→amount), not a traditional salesperson×month grid, since frappe-charts lacks a generic 2D matrix heatmap widget.

2. **Achievement % Gauge** — Uses horizontal percentage bar (frappe-charts' "percentage" type) rather than a circular gauge, since frappe-charts lacks that widget.

3. **Project Filter** — Applied at header level (SO/SI/DN header `project` field), not item level, for simplicity. Filters entire transactions, not individual line items.

4. **Delivery Note Sales Team** — If left empty on the Delivery Note itself, delivered amount contributions will be zero for that salesperson (the table has its own independent Sales Team rows, not traced back to the originating SO's allocation).

5. **Excel via xlsxwriter** — Built directly with xlsxwriter (not `frappe.utils.xlsxutils.make_xlsx`) to support freeze panes and autofilter. Adds a small new dependency chain but is already available transitively via frappe's openpyxl requirement.

6. **Two HTTP round-trips per filter change** — The native `execute()` and the additional `get_dashboard_data()` call cannot be combined into one request due to Frappe's fixed 5-tuple return contract for Script Reports. This is acceptable (still O(1) total) and trades minor latency for cleaner architecture.

## Future Enhancements

- **Caching** — If `execute()` and `get_dashboard_data()` are called with identical filters in quick succession, cache the aggregation queries between them.
- **Saved filters** — Remember user's last filter selection (via browser localStorage or user preference).
- **Performance benchmarking** — Add query timing logs at the end of each query for performance monitoring.
- **Custom KPI weighting** — Make Performance Score formula weights configurable via DocType settings.
- **Email scheduled reports** — Set up a scheduler to email the Excel export weekly/monthly to stakeholders.
- **Drill-down to transactions** — Click a cell in the main table to drill down to underlying Sales Orders/Invoices/Deliveries.

## Testing

Run the basic integration test:
```bash
cd /home/trojan-technologies/frappe-bench
./env/bin/python3 apps/luxury_report/test_spws_integration.py
```

This verifies:
- All modules import correctly
- Column structure is valid
- `execute()` returns the correct 5-tuple
- KPI structure matches framework expectations
- Chart structure matches frappe-charts expectations
- `get_dashboard_data()` returns all required sections

## Code Quality Notes

- **Modular design** — Queries, analytics, and export are separate concerns, easy to test/maintain/enhance
- **No N+1 queries** — Constant-count queries regardless of data size
- **Pure functions** — Analytics functions have no side effects, fully testable without DB
- **Simple defaults** — Formulas and KPI indicators use sensible defaults, tunable via constants at module top
- **Minimal dependencies** — Uses only frappe core and xlsxwriter (already transitively available)
- **Ponytail principle** — Only code that's actually needed, no speculative abstractions or premature optimization
