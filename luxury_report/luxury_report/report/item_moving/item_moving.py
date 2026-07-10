# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Coalesce, Max, Sum
from frappe.utils import flt, getdate
from frappe.utils.nestedset import get_descendants_of

from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter


def execute(filters: dict | None = None):
	if filters is None:
		filters = {}

	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 120,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Item Group"),
			"fieldname": "item_group",
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 120,
		},
		{
			"label": _("Brand"),
			"fieldname": "brand",
			"fieldtype": "Link",
			"options": "Brand",
			"width": 100,
		},
		{
			"label": _("Outward Qty"),
			"fieldname": "outward_qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Last Movement Date"),
			"fieldname": "last_movement_date",
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"label": _("Classification"),
			"fieldname": "classification",
			"fieldtype": "Data",
			"width": 120,
		},
	]


def get_data(filters: dict) -> list[dict]:
	validate_filters(filters)
	query = build_aggregation_query(filters)
	results = query.run(as_dict=True)

	for row in results:
		row["classification"] = classify_item(row, filters)

	if filters.get("classification") and filters.get("classification") != "All":
		results = [r for r in results if r["classification"] == filters.get("classification")]

	return results


def validate_filters(filters: dict) -> None:
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required"))

	from_date = getdate(from_date)
	to_date = getdate(to_date)

	if from_date > to_date:
		frappe.throw(_("From Date must be before or equal to To Date"))


def build_aggregation_query(filters: dict):
	sle = frappe.qb.DocType("Stock Ledger Entry")
	item = frappe.qb.DocType("Item")

	from_date = getdate(filters.get("from_date"))
	to_date = getdate(filters.get("to_date"))

	outward_qty = Sum(
		Case().when(sle.actual_qty < 0, sle.actual_qty * -1).else_(0)
	).as_("outward_qty")

	last_movement = Max(sle.posting_date).as_("last_movement_date")

	query = (
		frappe.qb.from_(sle)
		.inner_join(item)
		.on(sle.item_code == item.name)
		.select(
			sle.item_code,
			item.item_name,
			item.item_group,
			item.brand,
			outward_qty,
			last_movement,
		)
		.where(sle.is_cancelled == 0)
		.where(sle.posting_date >= from_date)
		.where(sle.posting_date <= to_date)
		.groupby(sle.item_code)
	)

	if company := filters.get("company"):
		query = query.where(sle.company == company)

	query = apply_warehouse_filter(query, sle, filters)

	if item_group := filters.get("item_group"):
		children = get_descendants_of("Item Group", item_group, ignore_permissions=True)
		query = query.where(item.item_group.isin([*children, item_group]))

	if brand := filters.get("brand"):
		query = query.where(item.brand == brand)

	return query


def classify_item(row: dict, filters: dict) -> str:
	outward_qty = flt(row.get("outward_qty") or 0)
	fast_threshold = flt(filters.get("fast_moving_threshold") or 0)
	slow_threshold = flt(filters.get("slow_moving_threshold") or 0)

	if outward_qty >= fast_threshold:
		return "Fast Moving"
	elif outward_qty >= slow_threshold:
		return "Slow Moving"
	else:
		return "Non-Moving"
