# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from .queries import get_so_totals, get_si_totals, get_dn_totals, get_so_period_trend, get_si_period_trend, get_dn_period_trend
from .analytics import build_main_table, build_kpis, build_native_chart, build_comparison_table, build_extra_charts


def execute(filters: dict | None = None):
	
	if filters is None:
		filters = {}

	
	so_totals = get_so_totals(filters)
	si_totals = get_si_totals(filters)
	dn_totals = get_dn_totals(filters)
	so_period_trend = get_so_period_trend(filters)
	si_period_trend = get_si_period_trend(filters)
	dn_period_trend = get_dn_period_trend(filters)

	
	main_table = build_main_table(so_totals, si_totals, dn_totals, filters)
	kpis = build_kpis(so_totals, si_totals, dn_totals, main_table)
	native_chart = build_native_chart(so_period_trend, si_period_trend)

	columns = get_columns()
	data = [_serialize_row(row) for row in main_table]

	return columns, data, None, native_chart, kpis


def get_columns() -> list[dict]:
	
	return [
		{"label": _("Salesperson"), "fieldname": "sales_person", "fieldtype": "Link", "options": "Sales Person", "width": 150},
		{"label": _("# SO"), "fieldname": "so_count", "fieldtype": "Int", "width": 80},
		{"label": _("SO Amount"), "fieldname": "so_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("SI Amount"), "fieldname": "si_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Difference"), "fieldname": "difference", "fieldtype": "Currency", "width": 120},
		{"label": _("Difference %"), "fieldname": "difference_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Delivered"), "fieldname": "delivered_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Pending"), "fieldname": "pending_delivery", "fieldtype": "Currency", "width": 120},
		{"label": _("Fully Delivered"), "fieldname": "fully_delivered", "fieldtype": "Int", "width": 110},
		{"label": _("Partially Delivered"), "fieldname": "partial_delivered", "fieldtype": "Int", "width": 130},
		{"label": _("Pending Orders"), "fieldname": "pending_orders", "fieldtype": "Int", "width": 110},
		{"label": _("Avg Order Value"), "fieldname": "avg_order_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Customers"), "fieldname": "customer_count", "fieldtype": "Int", "width": 100},
		{"label": _("Invoice Conv %"), "fieldname": "invoice_conversion", "fieldtype": "Percent", "width": 110},
		{"label": _("Delivery Conv %"), "fieldname": "delivery_conversion", "fieldtype": "Percent", "width": 120},
		{"label": _("Achievement %"), "fieldname": "achievement_pct", "fieldtype": "Percent", "width": 110},
		{"label": _("Growth %"), "fieldname": "growth_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Last Month Sales"), "fieldname": "last_month_sales", "fieldtype": "Currency", "width": 130},
		{"label": _("Current Month Sales"), "fieldname": "current_month_sales", "fieldtype": "Currency", "width": 140},
		{"label": _("YTD Sales"), "fieldname": "ytd_sales", "fieldtype": "Currency", "width": 120},
	]


def _serialize_row(row: dict):
	
	columns = get_columns()
	return [row.get(col["fieldname"], "") for col in columns]


@frappe.whitelist()
def get_dashboard_data(filters_json=None):
	
	import json
	filters = json.loads(filters_json) if isinstance(filters_json, str) else filters_json or {}

	
	so_totals = get_so_totals(filters)
	si_totals = get_si_totals(filters)
	dn_totals = get_dn_totals(filters)
	so_period_trend = get_so_period_trend(filters)
	si_period_trend = get_si_period_trend(filters)
	dn_period_trend = get_dn_period_trend(filters)

	
	main_table = build_main_table(so_totals, si_totals, dn_totals, filters)
	comparison = build_comparison_table(main_table, filters.get("top_n"))
	extra_charts = build_extra_charts(so_period_trend, si_period_trend, dn_period_trend, main_table, filters)

	
	individual_perf = None
	sales_persons = filters.get("sales_person")
	if sales_persons:
		if isinstance(sales_persons, str):
			sales_persons = [sales_persons]
		if len(sales_persons) == 1:
			from .analytics import build_individual_performance
			grouping = filters.get("grouping", "Monthly")
			individual_perf = build_individual_performance(
				sales_persons[0], so_period_trend, si_period_trend, dn_period_trend, grouping
			)

	return {
		"comparison": comparison,
		"individual_performance": individual_perf,
		"extra_charts": extra_charts,
	}
