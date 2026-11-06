# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt

from . import queries


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	queries.validate_setup()

	columns = get_columns()
	rows = get_rows(filters, start=0, page_size=queries.get_page_size(filters))
	summary = get_report_summary(queries.get_totals(filters))

	return columns, rows, None, None, summary


@frappe.whitelist()
def get_page(filters: str | dict | None = None, start: int = 0) -> dict:
	"""Next batch of invoices for Load More. Rows already loaded are not read again."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	filters = frappe._dict(frappe.parse_json(filters) or {})
	queries.validate_setup()

	return {"rows": get_rows(filters, start=cint(start), page_size=queries.get_page_size(filters))}


def get_columns() -> list[dict]:
	return [
		{"label": _("Sl. No."), "fieldname": "sl_no", "fieldtype": "Int", "width": 70},
		{"label": _("Transaction Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("Invoice Amount"), "fieldname": "invoice_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Commission Paid"), "fieldname": "commission_paid", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Journal Entry (JV)"), "fieldname": "commission_journal_entry", "fieldtype": "Link", "options": "Journal Entry", "width": 170},
		{"label": _("Sales Person"), "fieldname": "sales_person", "fieldtype": "Data", "width": 140},
		{"label": _("Cashier"), "fieldname": "cashier", "fieldtype": "Link", "options": "User", "width": 160},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Data", "width": 120},
		{"label": _("POS Profile"), "fieldname": "pos_profile", "fieldtype": "Link", "options": "POS Profile", "width": 140},
		{"label": _("POS Opening Entry"), "fieldname": "pos_opening_entry", "fieldtype": "Link", "options": "POS Opening Entry", "width": 170},
		{"label": _("Invoice Status"), "fieldname": "invoice_status", "fieldtype": "Data", "width": 110},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_rows(filters, start: int, page_size: int) -> list[dict]:
	invoices = queries.get_invoice_page(filters, start, page_size)
	sales_persons = queries.get_sales_persons([inv.name for inv in invoices])
	opening_entries = queries.get_opening_entries(invoices)

	for idx, inv in enumerate(invoices, start + 1):
		inv.update(
			sl_no=idx,
			sales_person=sales_persons.get(inv.name, ""),
			pos_opening_entry=opening_entries.get(inv.name),
			invoice_status=get_invoice_status(inv),
		)
		for field in ("posting_time", "pos_closing_entry", "is_return", "docstatus"):
			inv.pop(field, None)
	return invoices


def get_invoice_status(invoice) -> str:
	if invoice.docstatus == 2:
		return _("Cancelled")
	return _("Return") if invoice.is_return else _("Submitted")


def get_report_summary(totals: dict) -> list[dict]:
	return [
		{"key": "invoice_count", "label": _("Invoices"), "value": cint(totals.invoice_count), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Invoice Amount"), "value": flt(totals.invoice_amount), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Commission Paid"), "value": flt(totals.commission_paid), "datatype": "Currency", "indicator": "Green"},
	]
