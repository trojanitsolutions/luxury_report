# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""SQL for the POS Commission Report.

One row per POS Sales Invoice whose commission was actually paid: the invoice's
commission Journal Entry (luxury_api `commission_journal_entry`) is submitted.
The paid amount is read from that Journal Entry, not from the Sales Team rows,
so multiple Sales Team rows can never duplicate or inflate an invoice.

Returns carry the recovery Journal Entry (the sales person gave money back), so
their amount is negative. Cancelled invoices whose commission JE was kept are
included, because that cash was paid out.

Paging is done on invoices only. Sales person and POS Opening Entry are read in
one query each for the invoice names of a batch, and merged in Python.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate

PAGE_SIZES = (20, 100, 500, 2500)

# ERPNext uses the rounded total as the invoice total when rounding is on
INVOICE_TOTAL_SQL = "if(si.disable_rounded_total = 1 or si.rounded_total = 0, si.grand_total, si.rounded_total)"

# The commission JE has one debit and one credit line of the same amount
COMMISSION_PAID_SQL = "if(si.is_return = 1, -je.total_debit, je.total_debit)"

FROM_SQL = """
	from `tabSales Invoice` si
	inner join `tabJournal Entry` je on je.name = si.commission_journal_entry
	left join `tabPOS Profile` pp on pp.name = si.pos_profile
"""


def get_page_size(filters) -> int:
	page_size = cint(filters.get("page_size"))
	return page_size if page_size in PAGE_SIZES else PAGE_SIZES[0]


def validate_setup():
	# commission_journal_entry is a custom field created by luxury_api
	if not frappe.db.has_column("Sales Invoice", "commission_journal_entry"):
		frappe.throw(_("Commission payment fields are missing. Install luxury_api and run migrate."))


def validate_dates(filters):
	from_date, to_date = filters.get("from_date"), filters.get("to_date")
	if from_date and to_date and getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date."))


def build_conditions(filters) -> tuple[str, dict]:
	validate_dates(filters)
	conditions = [
		"je.docstatus = 1",
		"si.docstatus in (1, 2)",
		"si.is_pos = 1",
		"si.is_created_using_pos = 1",
	]
	values = {}

	for field, condition in (
		("company", "si.company = %(company)s"),
		("from_date", "si.posting_date >= %(from_date)s"),
		("to_date", "si.posting_date <= %(to_date)s"),
		("customer", "si.customer = %(customer)s"),
		("cashier", "si.owner = %(cashier)s"),
		("journal_entry", "si.commission_journal_entry = %(journal_entry)s"),
	):
		if filters.get(field):
			conditions.append(condition)
			values[field] = filters.get(field)

	if filters.get("branch") and has_branch():
		conditions.append("pp.branch = %(branch)s")
		values["branch"] = filters.get("branch")

	pos_profiles = as_list(filters.get("pos_profile"))
	if pos_profiles:
		conditions.append("si.pos_profile in %(pos_profile)s")
		values["pos_profile"] = tuple(pos_profiles)

	return " and ".join(conditions), values


def get_invoice_page(filters, start: int, page_size: int) -> list[dict]:
	conditions, values = build_conditions(filters)
	values.update(start=max(cint(start), 0), page_size=page_size)

	# name is unique, so the order is stable and Load More never repeats or skips a row
	return frappe.db.sql(
		f"""
		select
			si.name, si.posting_date, si.posting_time, si.customer, si.customer_name,
			si.pos_profile, {branch_field()} as branch, si.owner as cashier,
			si.pos_closing_entry, si.is_return, si.docstatus, si.currency,
			{INVOICE_TOTAL_SQL} as invoice_amount,
			{COMMISSION_PAID_SQL} as commission_paid,
			si.commission_journal_entry
		{FROM_SQL}
		where {conditions}
		order by si.posting_date desc, si.posting_time desc, si.name desc
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
			coalesce(sum({INVOICE_TOTAL_SQL}), 0) as invoice_amount,
			coalesce(sum({COMMISSION_PAID_SQL}), 0) as commission_paid
		{FROM_SQL}
		where {conditions}
		""",
		values,
		as_dict=True,
	)[0]


def get_sales_persons(invoice_names: list[str]) -> dict[str, str]:
	if not invoice_names:
		return {}

	rows = frappe.db.sql(
		"""
		select parent, group_concat(distinct sales_person order by idx separator ', ') as sales_person
		from `tabSales Team`
		where parenttype = 'Sales Invoice' and parent in %(names)s
		group by parent
		""",
		{"names": tuple(invoice_names)},
		as_dict=True,
	)
	return {row.parent: row.sales_person for row in rows}


def get_opening_entries(invoices: list[dict]) -> dict[str, str]:
	"""POS Opening Entry of the shift each invoice was made in.

	A closed shift: the invoice's POS Closing Entry names its opening entry.
	A shift still open: the latest Open entry of the invoice's POS Profile that
	started before the invoice.
	"""
	opening = get_closed_shift_openings(invoices)
	pending = [inv for inv in invoices if inv.name not in opening and inv.pos_profile]
	opening.update(get_open_shift_openings(pending))
	return opening


def get_closed_shift_openings(invoices: list[dict]) -> dict[str, str]:
	closing_entries = {inv.pos_closing_entry for inv in invoices if inv.pos_closing_entry}
	if not closing_entries:
		return {}

	opening_by_closing = dict(
		frappe.db.sql(
			"select name, pos_opening_entry from `tabPOS Closing Entry` where name in %(names)s",
			{"names": tuple(closing_entries)},
		)
	)
	return {
		inv.name: opening_by_closing[inv.pos_closing_entry]
		for inv in invoices
		if opening_by_closing.get(inv.pos_closing_entry)
	}


def get_open_shift_openings(invoices: list[dict]) -> dict[str, str]:
	profiles = {inv.pos_profile for inv in invoices}
	if not profiles:
		return {}

	shifts = {}
	for row in frappe.db.sql(
		"""
		select name, pos_profile, period_start_date
		from `tabPOS Opening Entry`
		where docstatus = 1 and status = 'Open' and pos_profile in %(profiles)s
		order by period_start_date desc
		""",
		{"profiles": tuple(profiles)},
		as_dict=True,
	):
		shifts.setdefault(row.pos_profile, []).append(row)

	result = {}
	for inv in invoices:
		posted_at = get_datetime(f"{inv.posting_date} {inv.posting_time or '00:00:00'}")
		# shifts are newest first, so the first one that started before the invoice is its shift
		for shift in shifts.get(inv.pos_profile, []):
			if get_datetime(shift.period_start_date) <= posted_at:
				result[inv.name] = shift.name
				break
	return result


def as_list(value) -> list:
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return [v for v in value if v]


def has_branch() -> bool:
	# POS Profile.branch is a custom Data field from luxury_api, fetched from warehouse.branch
	return frappe.db.has_column("POS Profile", "branch")


def branch_field() -> str:
	return "pp.branch" if has_branch() else "null"
