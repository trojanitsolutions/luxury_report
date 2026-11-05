# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""SQL for the POS Payment Invoice report.

Paging is done on invoices only. Payment methods and items are read in one
query each for the invoice names of a batch, and merged in Python, so child
tables never multiply invoice rows.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

PAGE_SIZES = (50, 100, 500, 1000, 2500)
PAYMENT_STATUSES = ("Paid", "Unpaid", "Partially Paid")

# ERPNext computes outstanding_amount against the rounded total when rounding is on
INVOICE_TOTAL_SQL = "if(si.disable_rounded_total = 1 or si.rounded_total = 0, si.grand_total, si.rounded_total)"

PAYMENT_STATUS_SQL = f"""
	case
		when si.outstanding_amount <= 0 then 'Paid'
		when si.outstanding_amount >= {INVOICE_TOTAL_SQL} then 'Unpaid'
		else 'Partially Paid'
	end
"""

FROM_SQL = """
	from `tabSales Invoice` si
	left join `tabPOS Profile` pp on pp.name = si.pos_profile
"""


def get_page_size(filters) -> int:
	page_size = cint(filters.get("page_size"))
	return page_size if page_size in PAGE_SIZES else PAGE_SIZES[0]


def build_conditions(filters, invoices: list | None = None) -> tuple[str, dict]:
	validate_dates(filters)
	conditions = ["si.is_pos = 1", "si.docstatus = 1"]
	values = {}

	for field, condition in (
		("company", "si.company = %(company)s"),
		("from_date", "si.posting_date >= %(from_date)s"),
		("to_date", "si.posting_date <= %(to_date)s"),
		("customer", "si.customer = %(customer)s"),
		("invoice", "si.name = %(invoice)s"),
	):
		if filters.get(field):
			conditions.append(condition)
			values[field] = filters.get(field)

	if filters.get("branch") and has_branch():
		conditions.append("pp.branch = %(branch)s")
		values["branch"] = filters.get("branch")

	for field, condition, enabled in (
		("pos_profile", "si.pos_profile in %(pos_profile)s", True),
		("channel", "si.channel in %(channel)s", has_channel()),
		(
			"mode_of_payment",
			"""exists (
				select 1 from `tabSales Invoice Payment` sip
				where sip.parent = si.name and sip.parenttype = 'Sales Invoice'
					and sip.amount <> 0 and sip.mode_of_payment in %(mode_of_payment)s
			)""",
			True,
		),
	):
		selected = as_list(filters.get(field))
		if selected and enabled:
			conditions.append(condition)
			values[field] = tuple(selected)

	payment_status = filters.get("payment_status")
	if payment_status in PAYMENT_STATUSES:
		conditions.append(f"({PAYMENT_STATUS_SQL}) = %(payment_status)s")
		values["payment_status"] = payment_status

	if invoices is not None:
		conditions.append("si.name in %(invoices)s")
		values["invoices"] = tuple(invoices) or ("",)

	return " and ".join(conditions), values


def validate_dates(filters):
	from_date, to_date = filters.get("from_date"), filters.get("to_date")
	if from_date and to_date and getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def get_invoice_page(filters, start: int, page_size: int, invoices: list | None = None) -> list[dict]:
	conditions, values = build_conditions(filters, invoices)
	values.update(start=max(cint(start), 0), page_size=page_size)

	return frappe.db.sql(
		f"""
		select
			si.name, si.posting_date, si.customer, si.customer_name, si.pos_profile,
			{branch_field()} as branch, {channel_field()} as channel, si.currency,
			{PAYMENT_STATUS_SQL} as payment_status,
			si.grand_total,
			{INVOICE_TOTAL_SQL} - si.outstanding_amount as paid_amount,
			si.outstanding_amount
		{FROM_SQL}
		where {conditions}
		order by si.posting_date desc, si.name desc
		limit %(page_size)s offset %(start)s
		""",
		values,
		as_dict=True,
	)


def get_totals(filters) -> dict:
	"""Totals over every matching invoice, not only the loaded rows."""
	conditions, values = build_conditions(filters)

	return frappe.db.sql(
		f"""
		select
			count(*) as invoice_count,
			coalesce(sum(si.grand_total), 0) as grand_total,
			coalesce(sum({INVOICE_TOTAL_SQL} - si.outstanding_amount), 0) as paid_amount,
			coalesce(sum(si.outstanding_amount), 0) as outstanding_amount
		{FROM_SQL}
		where {conditions}
		""",
		values,
		as_dict=True,
	)[0]


def get_payment_methods(invoice_names: list[str]) -> dict[str, str]:
	if not invoice_names:
		return {}

	rows = frappe.db.sql(
		"""
		select parent, group_concat(distinct mode_of_payment order by idx separator ', ') as methods
		from `tabSales Invoice Payment`
		where parenttype = 'Sales Invoice' and parent in %(names)s and amount <> 0
		group by parent
		""",
		{"names": tuple(invoice_names)},
		as_dict=True,
	)
	return {row.parent: row.methods for row in rows}


def get_items(invoice_names: list[str]) -> dict[str, list[dict]]:
	if not invoice_names:
		return {}

	rows = frappe.db.sql(
		"""
		select parent, item_code, item_name, qty, uom, rate, amount
		from `tabSales Invoice Item`
		where parenttype = 'Sales Invoice' and parent in %(names)s
		order by parent, idx
		""",
		{"names": tuple(invoice_names)},
		as_dict=True,
	)
	items = {}
	for row in rows:
		items.setdefault(row.pop("parent"), []).append(row)
	return items


def as_list(value) -> list:
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return [v for v in value if v]


def has_channel() -> bool:
	# Channel is an Accounting Dimension from luxury_api; sites without it have no column
	return frappe.db.has_column("Sales Invoice", "channel")


def has_branch() -> bool:
	# POS Profile.branch is a custom Data field from luxury_api, fetched from warehouse.branch
	return frappe.db.has_column("POS Profile", "branch")


def channel_field() -> str:
	return "si.channel" if has_channel() else "null"


def branch_field() -> str:
	return "pp.branch" if has_branch() else "null"
