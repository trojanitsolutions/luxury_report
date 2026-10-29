# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt

PAGE_SIZES = (20, 100, 500, 2500)

# outstanding_amount based payment state, shared by the filter and the column
PAYMENT_STATUS_SQL = """
	case
		when si.outstanding_amount <= 0 then 'Paid'
		when si.outstanding_amount >= si.grand_total then 'Unpaid'
		else 'Partly Paid'
	end
"""


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})

	columns = get_columns()
	data = get_data(filters, get_row_limit(filters))
	totals = get_totals(filters)

	return columns, data, None, None, get_report_summary(totals)


def get_columns() -> list[dict]:
	return [
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Channel"), "fieldname": "channel", "fieldtype": "Link", "options": "Channel", "width": 120},
		{"label": _("POS Profile"), "fieldname": "pos_profile", "fieldtype": "Link", "options": "POS Profile", "width": 140},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Data", "width": 120},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 160},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Payment Status"), "fieldname": "payment_status", "fieldtype": "Data", "width": 110},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
		{"label": _("Paid Amount"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 130},
	]


def get_row_limit(filters) -> int:
	"""Rows loaded on screen: page size times the number of pages loaded."""
	page_size = cint(filters.get("page_size")) or PAGE_SIZES[0]
	if page_size not in PAGE_SIZES:
		page_size = PAGE_SIZES[0]
	return page_size * max(cint(filters.get("page_count")), 1)


def get_data(filters, limit: int) -> list[dict]:
	conditions, values = build_conditions(filters)
	values["limit"] = limit

	return frappe.db.sql(
		f"""
		select
			si.name, si.posting_date, si.customer, {_channel_field()} as channel,
			si.pos_profile, {_branch_field()} as branch,
			(select min(sii.sales_order) from `tabSales Invoice Item` sii where sii.parent = si.name) as sales_order,
			si.status, {PAYMENT_STATUS_SQL} as payment_status,
			si.grand_total, si.grand_total - si.outstanding_amount as paid_amount, si.outstanding_amount
		from `tabSales Invoice` si
		left join `tabPOS Profile` pp on pp.name = si.pos_profile
		where {conditions}
		order by si.posting_date desc, si.name desc
		limit %(limit)s
		""",
		values,
		as_dict=True,
	)


def get_totals(filters) -> dict:
	"""Totals over every matching invoice, not only the loaded page."""
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		select
			count(*) as invoice_count,
			coalesce(sum(si.grand_total), 0) as grand_total,
			coalesce(sum(si.grand_total - si.outstanding_amount), 0) as paid_amount,
			coalesce(sum(si.outstanding_amount), 0) as outstanding_amount,
			coalesce(sum(si.outstanding_amount <= 0), 0) as paid_count,
			coalesce(sum(si.outstanding_amount > 0), 0) as unpaid_count
		from `tabSales Invoice` si
		left join `tabPOS Profile` pp on pp.name = si.pos_profile
		where {conditions}
		""",
		values,
		as_dict=True,
	)[0]


def build_conditions(filters) -> tuple[str, dict]:
	conditions = []
	values = {}

	for field in ("company", "from_date", "to_date"):
		values[field] = filters.get(field)
	if filters.get("company"):
		conditions.append("si.company = %(company)s")
	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")

	status = _as_list(filters.get("status"))
	if status:
		conditions.append("si.status in %(status)s")
		values["status"] = status
	else:
		conditions.append("si.docstatus = 1")

	payment_status = filters.get("payment_status")
	if payment_status:
		conditions.append(f"({PAYMENT_STATUS_SQL}) = %(payment_status)s")
		values["payment_status"] = payment_status

	channel = _as_list(filters.get("channel"))
	if channel and _has_channel():
		conditions.append("si.channel in %(channel)s")
		values["channel"] = channel

	pos_profile = _as_list(filters.get("pos_profile"))
	if pos_profile:
		conditions.append("si.pos_profile in %(pos_profile)s")
		values["pos_profile"] = pos_profile

	if filters.get("branch") and _has_branch():
		conditions.append("pp.branch = %(branch)s")
		values["branch"] = filters.get("branch")

	return " and ".join(conditions), values


def get_report_summary(totals: dict) -> list[dict]:
	return [
		{"key": "invoice_count", "label": _("Invoices"), "value": cint(totals.invoice_count), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Grand Total"), "value": flt(totals.grand_total), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Paid Amount"), "value": flt(totals.paid_amount), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Outstanding"), "value": flt(totals.outstanding_amount), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Paid Invoices"), "value": cint(totals.paid_count), "datatype": "Int", "indicator": "Green"},
		{"label": _("Unpaid Invoices"), "value": cint(totals.unpaid_count), "datatype": "Int", "indicator": "Orange"},
	]


@frappe.whitelist()
def get_branches() -> list[str]:
	if not _has_branch():
		return []
	return frappe.get_all(
		"POS Profile",
		filters={"branch": ("is", "set")},
		pluck="branch",
		distinct=True,
		order_by="branch asc",
	)


def _as_list(value) -> list:
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return [v for v in value if v]


def _has_channel() -> bool:
	# Channel is an Accounting Dimension from luxury_api; sites without it have no column
	return frappe.db.has_column("Sales Invoice", "channel")


def _has_branch() -> bool:
	return frappe.db.has_column("POS Profile", "branch")


def _channel_field() -> str:
	return "si.channel" if _has_channel() else "null"


def _branch_field() -> str:
	return "pp.branch" if _has_branch() else "null"
