# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_first_day, get_first_day_of_week, get_quarter_start, get_year_start
from collections import defaultdict
from datetime import datetime, timedelta
import statistics

# Formula constants
ACHIEVEMENT_PERCENT_WEIGHT = 0.4
DELIVERY_CONVERSION_WEIGHT = 0.3
GROWTH_PERCENT_WEIGHT = 0.2
ORDER_COUNT_WEIGHT = 0.1


def build_main_table(so_totals, si_totals, dn_totals, filters):
	
	all_salespersons = set(so_totals.keys()) | set(si_totals.keys()) | set(dn_totals.keys())

	rows = []
	for sp in sorted(all_salespersons):
		so = so_totals.get(sp, {})
		si = si_totals.get(sp, {})
		dn = dn_totals.get(sp, {})

		so_amount = so.get("so_amount", 0) or 0
		si_amount = si.get("si_amount", 0) or 0
		delivered_amount = dn.get("delivered_amount", 0) or 0

		difference = so_amount - si_amount
		difference_pct = (difference / so_amount * 100) if so_amount else 0

		invoice_conversion = (si_amount / so_amount * 100) if so_amount else 0
		delivery_conversion = (delivered_amount / so_amount * 100) if so_amount else 0

		pending_delivery = so_amount - delivered_amount
		avg_order_value = (so_amount / so.get("so_count", 1)) if so.get("so_count") else 0

		so_count = so.get("so_count", 0) or 0
		customer_count = so.get("customer_count", 0) or 0
		fully_delivered = so.get("fully_delivered_orders", 0) or 0
		partial_delivered = so.get("partial_delivered_orders", 0) or 0
		pending_orders = so.get("pending_orders", 0) or 0

		rows.append({
			"sales_person": sp,
			"so_count": so_count,
			"so_amount": so_amount,
			"si_amount": si_amount,
			"difference": difference,
			"difference_pct": difference_pct,
			"delivered_amount": delivered_amount,
			"pending_delivery": pending_delivery,
			"fully_delivered": fully_delivered,
			"partial_delivered": partial_delivered,
			"pending_orders": pending_orders,
			"avg_order_value": avg_order_value,
			"customer_count": customer_count,
			"invoice_conversion": invoice_conversion,
			"delivery_conversion": delivery_conversion,
			"achievement_pct": invoice_conversion,
			"growth_pct": 0,
			"last_month_sales": 0,
			"current_month_sales": 0,
			"ytd_sales": so_amount,
		})

	return rows


def build_kpis(so_totals, si_totals, dn_totals, main_rows):
	
	total_so = sum(r.get("so_amount", 0) for r in so_totals.values())
	total_si = sum(r.get("si_amount", 0) for r in si_totals.values())
	total_dn = sum(r.get("delivered_amount", 0) for r in dn_totals.values())

	total_so_count = sum(r.get("so_count", 0) for r in so_totals.values())
	total_customers = len(set(r.get("customer") for r in so_totals.values() if r.get("customer")))

	pending_delivery = total_so - total_dn
	invoice_achievement = (total_si / total_so * 100) if total_so else 0
	delivery_achievement = (total_dn / total_so * 100) if total_so else 0
	avg_order_value = (total_so / total_so_count) if total_so_count else 0
	avg_monthly_sales = total_so / 12

	highest_month = max((r.get("current_month_sales", 0) for r in main_rows), default=0)
	lowest_month = min((r.get("current_month_sales", 0) for r in main_rows if r.get("current_month_sales", 0) > 0), default=0)

	return [
		{"value": total_so_count, "indicator": "Green" if total_so_count > 0 else "Grey", "label": _("Total Sales Orders"), "datatype": "Int"},
		{"value": total_so, "indicator": "Green" if total_so > 0 else "Grey", "label": _("Total SO Amount"), "datatype": "Currency"},
		{"value": total_si, "indicator": "Green" if total_si > 0 else "Grey", "label": _("Total SI Amount"), "datatype": "Currency"},
		{"value": total_dn, "indicator": "Green" if total_dn > 0 else "Grey", "label": _("Total Delivered Amount"), "datatype": "Currency"},
		{"value": pending_delivery, "indicator": "Blue" if pending_delivery > 0 else "Green", "label": _("Pending Delivery Amount"), "datatype": "Currency"},
		{"value": invoice_achievement, "indicator": "Green" if invoice_achievement >= 80 else "Blue" if invoice_achievement >= 50 else "Red", "label": _("Invoice Achievement %"), "datatype": "Percent"},
		{"value": delivery_achievement, "indicator": "Green" if delivery_achievement >= 80 else "Blue" if delivery_achievement >= 50 else "Red", "label": _("Delivery Achievement %"), "datatype": "Percent"},
		{"value": avg_order_value, "indicator": "Blue", "label": _("Average Order Value"), "datatype": "Currency"},
		{"value": total_customers, "indicator": "Blue", "label": _("Total Customers"), "datatype": "Int"},
		{"value": avg_monthly_sales, "indicator": "Blue", "label": _("Average Monthly Sales"), "datatype": "Currency"},
		{"value": highest_month, "indicator": "Green", "label": _("Highest Sales Month"), "datatype": "Currency"},
		{"value": lowest_month, "indicator": "Blue", "label": _("Lowest Sales Month"), "datatype": "Currency"},
	]


def build_native_chart(so_period_trend, si_period_trend):

	so_by_month = defaultdict(float)
	si_by_month = defaultdict(float)

	for row in so_period_trend:
		date = row.get("transaction_date")
		if date:
			month_key = date.strftime("%Y-%m") if hasattr(date, "strftime") else str(date)[:7]
			so_by_month[month_key] += row.get("so_amount", 0)

	for row in si_period_trend:
		date = row.get("transaction_date")
		if date:
			month_key = date.strftime("%Y-%m") if hasattr(date, "strftime") else str(date)[:7]
			si_by_month[month_key] += row.get("si_amount", 0)

	months = sorted(set(so_by_month.keys()) | set(si_by_month.keys()))

	return {
		"data": {
			"labels": months,
			"datasets": [
				{"name": _("Sales Orders"), "values": [so_by_month.get(m, 0) for m in months]},
				{"name": _("Sales Invoices"), "values": [si_by_month.get(m, 0) for m in months]},
			],
		},
		"type": "bar",
		"barOptions": {"stacked": False},
	}


def build_comparison_table(main_rows, top_n=None):
	
	if top_n:
		rows = sorted(main_rows, key=lambda r: r.get("so_amount", 0), reverse=True)[:top_n]
	else:
		rows = sorted(main_rows, key=lambda r: r.get("so_amount", 0), reverse=True)

	
	mean_so = sum(r.get("so_amount", 0) for r in main_rows) / len(main_rows) if main_rows else 0
	for i, row in enumerate(rows):
		row["rank"] = i + 1
		row["variance"] = row.get("so_amount", 0) - mean_so

	return rows


def build_individual_performance(sp_name, so_period_trend, si_period_trend, dn_period_trend, grouping="Monthly"):

	sp_so_trend = [r for r in so_period_trend if r.get("sales_person") == sp_name]
	sp_si_trend = [r for r in si_period_trend if r.get("sales_person") == sp_name]
	sp_dn_trend = [r for r in dn_period_trend if r.get("sales_person") == sp_name]

	bucketed_so = _bucket_trend_data(sp_so_trend, grouping, "so_amount")
	bucketed_si = _bucket_trend_data(sp_si_trend, grouping, "si_amount")
	bucketed_dn = _bucket_trend_data(sp_dn_trend, grouping, "delivered_amount")


	so_values = list(bucketed_so.values())
	si_values = list(bucketed_si.values())
	dn_values = list(bucketed_dn.values())

	avg_so = sum(so_values) / len(so_values) if so_values else 0
	avg_si = sum(si_values) / len(si_values) if si_values else 0
	avg_dn = sum(dn_values) / len(dn_values) if dn_values else 0

	moving_avg_so = _calculate_moving_average(so_values, 3) if so_values else 0

	growth_pct = 0
	if len(so_values) > 1:
		prev_val = so_values[-2]
		curr_val = so_values[-1]
		if prev_val > 0:
			growth_pct = (curr_val - prev_val) / prev_val * 100

	highest_month = max(so_values) if so_values else 0
	lowest_month = min((v for v in so_values if v > 0), default=0) if so_values else 0

	best_week = max(so_values) if so_values else 0
	worst_week = min((v for v in so_values if v > 0), default=0) if so_values else 0

	return {
		"sales_person": sp_name,
		"grouping": grouping,
		"average_sales": avg_so,
		"average_invoices": avg_si,
		"average_delivered": avg_dn,
		"moving_average": moving_avg_so,
		"growth_pct": growth_pct,
		"highest_performing_period": highest_month,
		"lowest_performing_period": lowest_month,
		"best_period": best_week,
		"worst_period": worst_week,
		"performance_score": _calculate_performance_score(avg_so, avg_dn, growth_pct, 1),
		"trend_data": bucketed_so,
	}


def build_historical_analysis(so_period_trend, si_period_trend, filters):

	sp_so_by_month = defaultdict(lambda: defaultdict(float))
	sp_si_by_month = defaultdict(lambda: defaultdict(float))

	for row in so_period_trend:
		sp = row.get("sales_person")
		date = row.get("transaction_date")
		if date:
			month_key = date.strftime("%Y-%m") if hasattr(date, "strftime") else str(date)[:7]
			sp_so_by_month[sp][month_key] += row.get("so_amount", 0)

	for row in si_period_trend:
		sp = row.get("sales_person")
		date = row.get("transaction_date")
		if date:
			month_key = date.strftime("%Y-%m") if hasattr(date, "strftime") else str(date)[:7]
			sp_si_by_month[sp][month_key] += row.get("si_amount", 0)


	historical = []
	for sp in sp_so_by_month.keys():
		months = sorted(sp_so_by_month[sp].keys())
		if len(months) >= 2:
			current_month = months[-1]
			prev_month = months[-2]

			current_so = sp_so_by_month[sp].get(current_month, 0)
			prev_so = sp_so_by_month[sp].get(prev_month, 0)

			mom_growth = ((current_so - prev_so) / prev_so * 100) if prev_so > 0 else 0

			historical.append({
				"sales_person": sp,
				"month": current_month,
				"so_amount": current_so,
				"si_amount": sp_si_by_month[sp].get(current_month, 0),
				"mom_growth": mom_growth,
			})

	return historical


def build_extra_charts(so_period_trend, si_period_trend, dn_period_trend, main_rows, filters):
	
	charts = {}

	
	top_sp = sorted(main_rows, key=lambda r: r.get("so_amount", 0), reverse=True)[:10]
	charts["salesperson_comparison"] = {
		"data": {
			"labels": [r.get("sales_person", "") for r in top_sp],
			"datasets": [{"name": _("SO Amount"), "values": [r.get("so_amount", 0) for r in top_sp]}],
		},
		"type": "bar",
	}

	
	so_by_month = defaultdict(float)
	for row in so_period_trend:
		date = row.get("transaction_date")
		if date:
			month_key = date.strftime("%Y-%m") if hasattr(date, "strftime") else str(date)[:7]
			so_by_month[month_key] += row.get("so_amount", 0)

	months = sorted(so_by_month.keys())
	charts["monthly_sales_trend"] = {
		"data": {
			"labels": months,
			"datasets": [{"name": _("Monthly Sales"), "values": [so_by_month[m] for m in months]}],
		},
		"type": "line",
	}

	
	so_by_week = defaultdict(float)
	for row in so_period_trend:
		date = row.get("transaction_date")
		if date:
			if hasattr(date, "strftime"):
				week_key = date.strftime("%Y-W%U")
			else:
				d = datetime.strptime(str(date), "%Y-%m-%d")
				week_key = d.strftime("%Y-W%U")
			so_by_week[week_key] += row.get("so_amount", 0)

	weeks = sorted(so_by_week.keys())[-12:]  # Last 12 weeks
	charts["weekly_trend"] = {
		"data": {
			"labels": weeks,
			"datasets": [{"name": _("Weekly Sales"), "values": [so_by_week[w] for w in weeks]}],
		},
		"type": "line",
	}

	
	total_so = sum(r.get("so_amount", 0) for r in main_rows)
	fully_delivered = sum(r.get("delivered_amount", 0) for r in main_rows)
	pending = total_so - fully_delivered

	charts["delivery_status_distribution"] = {
		"data": {
			"labels": [_("Delivered"), _("Pending")],
			"datasets": [{"name": _("Amount"), "values": [fully_delivered, pending]}],
		},
		"type": "pie",
	}

	
	si_by_month = defaultdict(float)
	for row in si_period_trend:
		date = row.get("transaction_date")
		if date:
			month_key = date.strftime("%Y-%m") if hasattr(date, "strftime") else str(date)[:7]
			si_by_month[month_key] += row.get("si_amount", 0)

	months_for_si = sorted(set(list(so_by_month.keys()) + list(si_by_month.keys())))
	conversion_rates = []
	for m in months_for_si:
		so = so_by_month.get(m, 0)
		si = si_by_month.get(m, 0)
		rate = (si / so * 100) if so > 0 else 0
		conversion_rates.append(rate)

	charts["invoice_conversion_trend"] = {
		"data": {
			"labels": months_for_si,
			"datasets": [{"name": _("Conversion %"), "values": conversion_rates}],
		},
		"type": "line",
	}

	
	top_5 = sorted(main_rows, key=lambda r: r.get("so_amount", 0), reverse=True)[:5]
	charts["top_salespersons"] = {
		"data": {
			"labels": [r.get("sales_person", "") for r in top_5],
			"datasets": [{"name": _("SO Amount"), "values": [r.get("so_amount", 0) for r in top_5]}],
		},
		"type": "bar",
	}

	
	charts["yoy_comparison"] = {
		"data": {
			"labels": months[-12:] if len(months) > 12 else months,
			"datasets": [
				{"name": _("Current Year"), "values": [so_by_month.get(m, 0) for m in (months[-12:] if len(months) > 12 else months)]},
			],
		},
		"type": "line",
	}

	
	heatmap_data = []
	for m in months:
		heatmap_data.append({"date": m, "value": so_by_month.get(m, 0)})

	charts["monthly_heatmap"] = {
		"data": {
			"labels": months,
			"datasets": [{"name": _("Sales"), "values": [so_by_month.get(m, 0) for m in months]}],
		},
		"type": "heatmap",
	}

	
	total_achievement = sum(r.get("achievement_pct", 0) for r in main_rows) / len(main_rows) if main_rows else 0

	charts["achievement_gauge"] = {
		"data": {
			"labels": [_("Achievement %")],
			"datasets": [{"name": _("Achievement"), "values": [total_achievement]}],
		},
		"type": "percentage",
	}

	return charts


def _bucket_trend_data(trend_rows, grouping, amount_field):
	
	bucketed = defaultdict(float)

	for row in trend_rows:
		date = row.get("transaction_date")
		if not date:
			continue

		if isinstance(date, str):
			date = datetime.strptime(date, "%Y-%m-%d").date()

		if grouping == "Daily":
			key = str(date)
		elif grouping == "Weekly":
			first_day_week = get_first_day_of_week(date)
			key = first_day_week.strftime("%Y-W%U") if hasattr(first_day_week, "strftime") else str(first_day_week)
		elif grouping == "Monthly":
			first_day_month = get_first_day(date)
			key = first_day_month.strftime("%Y-%m") if hasattr(first_day_month, "strftime") else str(first_day_month)[:7]
		elif grouping == "Quarterly":
			first_day_quarter = get_quarter_start(date)
			if hasattr(first_day_quarter, "strftime"):
				q = (first_day_quarter.month - 1) // 3 + 1
				key = f"{first_day_quarter.year}-Q{q}"
			else:
				key = str(first_day_quarter)
		elif grouping == "Yearly":
			first_day_year = get_year_start(date)
			key = first_day_year.strftime("%Y") if hasattr(first_day_year, "strftime") else str(first_day_year)[:4]
		else:
			key = str(date)

		bucketed[key] += row.get(amount_field, 0)

	return dict(bucketed)


def _calculate_moving_average(values, window=3):
	
	if len(values) < window:
		return sum(values) / len(values) if values else 0
	return statistics.mean(values[-window:])


def _calculate_performance_score(achievement, delivery, growth, order_count_factor):
	
	achievement_pct = min(achievement / 100, 1) * 100 if achievement else 0
	delivery_pct = min(delivery / 100, 1) * 100 if delivery else 0
	growth_clamped = min(max(growth, 0), 100)
	order_factor = min(order_count_factor, 10) * 10  # Normalize to 0-100

	score = (
		(achievement_pct * ACHIEVEMENT_PERCENT_WEIGHT) +
		(delivery_pct * DELIVERY_CONVERSION_WEIGHT) +
		(growth_clamped * GROWTH_PERCENT_WEIGHT) +
		(order_factor * ORDER_COUNT_WEIGHT)
	)

	return min(score, 100)
