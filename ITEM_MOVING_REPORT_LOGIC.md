# Item Moving Report - Logic Explanation

## Table of Contents
1. [The Problem](#the-problem-it-solves)
2. [How It Works](#how-it-works-step-by-step)
3. [Real Example](#real-example-from-the-test-data)
4. [Core Logic](#the-key-logic-in-pseudo-code)
5. [Filters Explained](#how-filters-work)
6. [Why This Design](#why-this-design)
7. [Data Flow](#what-data-flows-through)
8. [Design Decisions](#the-why-behind-key-decisions)
9. [Plain English Summary](#in-plain-english)

---

## The Problem It Solves

You need to know which items in your inventory are:

- **Selling quickly** (Fast Moving) → stock them more, prepare for demand
- **Selling slowly** (Slow Moving) → might be dead stock soon, consider discounts
- **Not selling at all** (Non-Moving) → waste of storage space, should remove

---

## How It Works (Step-by-Step)

### Step 1: Gather Movement Data

The report looks at the `Stock Ledger Entry` table — every time stock moves (out of warehouse), a record is created:

```
Customer receives delivery  → Stock moves OUT (negative qty)
Item gets damaged          → Stock moves OUT (negative qty)
Internal transfer          → Stock moves OUT (negative qty)
```

The report **sums up all outward movements** for each item during your selected date range (e.g., June 10 - July 10).

### Step 2: Classify Items Using Thresholds

After calculating total outward qty for each item, compare it to your **threshold values**:

**Example:**
- Fast Moving Threshold = 3 units
- Slow Moving Threshold = 1 unit

Now classify:

```
Item "A4 Paper"    → 3 units sold  ≥ 3? YES  → "Fast Moving" ✓
Item "Trolley Bag"  → 1 unit sold   ≥ 3? NO, ≥ 1? YES → "Slow Moving" ✓
Item "Clay"         → 0 units sold  ≥ 1? NO  → "Non-Moving" ✓
```

### Step 3: Filter the Results

Once classified, you can filter the report to show only:

- Fast Moving items (to see what's hot)
- Slow Moving items (to watch these closely)
- Non-Moving items (to clean up inventory)
- All together (to see the full picture)

---

## Real Example from the Test Data

I tested with these settings:
- Date range: June 10 - July 10, 2026
- Fast threshold: 3 units
- Slow threshold: 1 unit

**Results:**

| Item | Qty Sold | Classification | Why? |
|------|----------|-----------------|------|
| A4 Paper | 3 | Fast Moving | 3 ≥ 3 ✓ |
| File | 4 | Fast Moving | 4 ≥ 3 ✓ |
| Trolley Bag 3PCS | 1 | Slow Moving | 1 ≥ 1, but < 3 ✓ |
| Gift Bag | 1 | Slow Moving | 1 ≥ 1, but < 3 ✓ |
| Trolley Bag | 0 | Non-Moving | 0 < 1 ✗ |
| Backpack | 0 | Non-Moving | 0 < 1 ✗ |

---

## The Key Logic (in Pseudo-code)

```
FOR EACH ITEM:
  1. Count all stock movements OUT during date range
     outward_qty = SUM(all negative entries in Stock Ledger Entry)
  
  2. Classify based on thresholds
     IF outward_qty >= fast_moving_threshold
        → "Fast Moving"
     ELSE IF outward_qty >= slow_moving_threshold
        → "Slow Moving"
     ELSE
        → "Non-Moving"
  
  3. Track last movement date
     last_date = MAX(posting_date from Stock Ledger Entry)

RETURN: Item Code, Name, Group, Brand, Qty Sold, Last Date, Classification
```

---

## How Filters Work

### 1. Narrowing Filters (scope the data)

These reduce the **scope** of what gets analyzed:

- **Company**: Only look at one company's stock movements
- **Warehouse**: Only look at stock leaving this warehouse (and its sub-warehouses)
- **Item Group**: Only analyze items in this category (expands to child groups)
- **Brand**: Only look at items from this brand

**Result**: Smaller dataset → faster query, more focused analysis

### 2. Date Filters (define the period)

- **From Date**: "Start counting from this date"
- **To Date**: "Stop counting at this date"

**Example**: "Give me movement from Jan 1 to Dec 31 2026"

### 3. Threshold Filters (set classification boundaries)

- **Fast Moving Threshold**: The minimum qty to be considered "Fast Moving"
- **Slow Moving Threshold**: The minimum qty to be considered "Slow Moving"

**Example**: 
- If Fast = 100 and Slow = 10:
  - 150 units → Fast Moving
  - 50 units → Slow Moving
  - 5 units → Non-Moving

### 4. Classification Filter (show what you want)

- **All**: Show every item (all 3 classifications)
- **Fast Moving**: Show only items selling well
- **Slow Moving**: Show only the risky items
- **Non-Moving**: Show only the dead stock

---

## Why This Design?

### ✓ Simple to Understand

- One number per item (total qty sold)
- One rule (compare to threshold)
- Three outcomes (Fast/Slow/Non-Moving)

### ✓ Easy to Configure

- Change thresholds via filter (no code change needed)
- Different businesses can use different numbers:
  - Fashion store: Fast ≥ 50/month (fast-moving industry)
  - Specialty tools: Fast ≥ 5/month (slow-moving by nature)

### ✓ Fast to Calculate

- Single database query (not per-item lookups)
- Leverages existing indexes
- Works on millions of stock movements

### ✓ Aligns with ERPNext

- Uses same patterns as other ERPNext stock reports
- Reuses existing warehouse tree logic
- Respects item group hierarchies

---

## What Data Flows Through

```
User opens report in Desk
         ↓
Enters filters (Company, Warehouse, Dates, etc.)
         ↓
Report receives: {"from_date": "2026-06-10", "to_date": "2026-07-10", ...}
         ↓
Validate: Is from_date ≤ to_date? (error if not)
         ↓
Query database:
  - Look up Stock Ledger Entry table
  - Find all records where:
    * posting_date is between from_date and to_date
    * warehouse matches filter (including child warehouses)
    * item belongs to filtered item_group/brand
    * not cancelled
  - Sum negative quantities per item_code
  - Get MAX(posting_date) as last_movement_date
         ↓
For each item returned:
  - outward_qty ≥ fast_threshold?  → "Fast Moving"
  - outward_qty ≥ slow_threshold?  → "Slow Moving"
  - else                            → "Non-Moving"
         ↓
Apply classification filter (if user selected "Fast Moving", drop others)
         ↓
Return to Desk with 7 columns:
  Item Code, Item Name, Item Group, Brand, Outward Qty, Last Date, Classification
         ↓
User sees report and can:
  - Sort by Outward Qty
  - Filter to Fast/Slow/Non-Moving
  - Click item code to see full item details
```

---

## The "Why" Behind Key Decisions

### Q: Why sum ALL negative quantities, not just sales?

**A:** Because stock leaves warehouses for many reasons:
- Customer sales (Delivery Note)
- Internal consumption (Stock Entry for manufacturing)
- Damage/loss (Negative Stock Reconciliation)
- All of these mean "the item is being used" → valuable signal

### Q: Why are thresholds configurable filters, not hardcoded?

**A:** Different businesses move different quantities:
- A bakery might say Fast = 100 loaves/day
- A luxury store might say Fast = 5 items/month
- Your thresholds reflect your business, not ours

### Q: Why group by item_code, not by warehouse?

**A:** You want to know "Is item X moving?" not "Is item X moving in warehouse Y?"
- If you select a warehouse, the query is scoped to that warehouse
- But you get one row per item, not per warehouse-item combo
- This tells you the overall demand signal more clearly

### Q: Why calculate last_movement_date?

**A:** Context. An item with qty=5 that last moved 1 year ago is different from one that moved yesterday.
- Non-Moving: Last moved = old → definitely dead
- Slow Moving + last moved = recent → maybe just a seasonal dip
- Helps you decide "should I keep this item?"

### Q: Why one database query instead of per-item lookups?

**A:** Performance and scalability:
- One query to get all items at once = fast
- Per-item lookups = 1000 items = 1000 queries (slow)
- Works on warehouses with 100,000+ items and millions of stock movements

---

## Report Columns Explained

| Column | Type | What It Shows | Where It Comes From |
|--------|------|---------------|--------------------|
| **Item Code** | Link to Item | Unique identifier | Stock Ledger Entry |
| **Item Name** | Text | Full name of item | Item master |
| **Item Group** | Link to Item Group | Category (e.g., "Bags", "Paper") | Item master |
| **Brand** | Link to Brand | Manufacturer/brand | Item master |
| **Outward Qty** | Number | Total units moved out in period | SUM of negative Stock Ledger Entry quantities |
| **Last Movement Date** | Date | When item was last sold/used | MAX posting_date from Stock Ledger Entry |
| **Classification** | Text | Fast/Slow/Non-Moving | Calculated by comparing Outward Qty to thresholds |

---

## In Plain English

> Your warehouse has hundreds of items. Every time something is sold or used, it gets tracked. This report asks: "Which items are leaving the warehouse fastest?"
>
> It counts how many units of each item left during a month. Then it draws three lines:
> - Items leaving **3+ units**: These are hot sellers (Fast Moving)
> - Items leaving **1-2 units**: These are okay (Slow Moving)
> - Items leaving **0 units**: Nobody wants these (Non-Moving)
>
> You can then filter to see only the ones you care about—maybe focus on keeping Fast Moving items in stock, or decide to stop ordering Non-Moving items.

---

## Example Workflow

### Scenario: Store Manager Analyzing Q3 Inventory

**Step 1: Open Report**
- Go to Desk → Item Moving Report
- Filters appear: Company, Warehouse, Dates, Classification, Thresholds

**Step 2: Set Filters**
```
Company: Luxury Store Ltd
Warehouse: Main Warehouse
From Date: July 1, 2026
To Date: September 30, 2026
Fast Threshold: 50 units
Slow Threshold: 10 units
Classification: All (show everything)
```

**Step 3: Report Runs**
- Database counts all stock leaving Main Warehouse from July-Sep
- For each item, computes total outward qty
- Classifies into Fast/Slow/Non-Moving
- Returns 85 items total:
  - 12 Fast Moving (50+ units) → popular items
  - 28 Slow Moving (10-50 units) → selling but slower
  - 45 Non-Moving (0 units) → dead stock

**Step 4: Manager Takes Action**
- Filters to see only "Non-Moving" items
- Sees 45 items not sold all quarter
- Decides: "Delete 20 low-value items, discount 15, keep 10 as backup stock"
- Improves warehouse efficiency immediately

---

## Performance Notes

### What Makes It Fast?

1. **Single Database Query**
   - All calculation happens in SQL
   - Returns only aggregated data per item
   - Not pulling millions of rows to app

2. **Existing Database Index**
   - Stock Ledger Entry already indexed by `(item_code, warehouse, posting_date)`
   - Query uses this index automatically
   - No table scans or slow joins

3. **Smart Filtering**
   - Narrows dataset BEFORE aggregation
   - A warehouse filter reduces 1M rows to 10K rows first
   - Then aggregates only the 10K

### What If You Have Millions of Stock Movements?

✓ No problem. Still runs in seconds because:
- Index lookup is O(log N) not O(N)
- Aggregation happens in database
- Only returns ~1000 items, not millions of rows

---

## Customization Examples

### Use Case 1: Fast Fashion Store

```
Fast Threshold: 500 units/month
Slow Threshold: 100 units/month

Result: "Fast Moving" = items selling 500+ units
This matches their business reality
```

### Use Case 2: Specialty Bookstore

```
Fast Threshold: 5 units/month
Slow Threshold: 1 unit/month

Result: "Fast Moving" = books selling 5+ copies
This matches their slower-moving business
```

### Use Case 3: Manufacturing (Internal Movement)

```
Filter: By Warehouse = "Raw Materials"
Result: Shows which raw materials are being consumed fastest
Helps with just-in-time procurement
```

---

## Summary

| Aspect | Description |
|--------|-------------|
| **What** | Classifies inventory items as Fast/Slow/Non-Moving |
| **How** | Counts outward stock movements, compares to thresholds |
| **Why** | Helps decide what to stock, discount, or remove |
| **Speed** | Single query, uses indexes, works on millions of records |
| **Flexibility** | Thresholds configurable per business needs |
| **Accuracy** | Counts all outflows (sales, internal, loss) |
| **Output** | 7 columns per item: code, name, group, brand, qty, date, classification |

---

**Last Updated**: July 10, 2026  
**Report Location**: Desk → Item Moving Report  
**File**: `luxury_report/luxury_report/report/item_moving/item_moving.py`
