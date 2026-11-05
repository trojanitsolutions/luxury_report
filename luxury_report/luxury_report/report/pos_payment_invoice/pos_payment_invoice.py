# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt

from . import queries

AMOUNT_FIELDS = ("grand_total", "paid_amount", "outstanding_amount")


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})

	columns = get_columns(filters)
	rows = get_rows(filters, start=0, page_size=queries.get_page_size(filters))
	summary = get_report_summary(queries.get_totals(filters))

	return columns, rows, None, None, summary


@frappe.whitelist()
def get_page(filters: str | dict | None = None, start: int = 0) -> dict:
	"""Next batch of invoices for Load More. Rows already loaded are not read again."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	filters = frappe._dict(frappe.parse_json(filters) or {})

	return {"rows": get_rows(filters, start=cint(start), page_size=queries.get_page_size(filters))}


def get_columns(filters) -> list[dict]:
	columns = [
		{"label": _("Sl. No."), "fieldname": "sl_no", "fieldtype": "Int", "width": 70},
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
		{"label": _("POS Profile"), "fieldname": "pos_profile", "fieldtype": "Link", "options": "POS Profile", "width": 140},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Data", "width": 120},
		{"label": _("Channel"), "fieldname": "channel", "fieldtype": "Data", "width": 110},
		{"label": _("Payment Method"), "fieldname": "payment_method", "fieldtype": "Data", "width": 150},
		{"label": _("Payment Status"), "fieldname": "payment_status", "fieldtype": "Data", "width": 120},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Paid Amount"), "fieldname": "paid_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Outstanding Amount"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
	]

	if cint(filters.get("show_item_details")):
		columns += [
			{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
			{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
			{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 70},
			{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
			{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Currency", "options": "currency", "width": 110},
			{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		]

	columns += [
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
		{"label": _("Invoice Ref"), "fieldname": "invoice", "fieldtype": "Data", "hidden": 1},
		{"label": _("Row Type"), "fieldname": "row_type", "fieldtype": "Data", "hidden": 1},
	]
	return columns


def get_rows(filters, start: int, page_size: int, invoices: list | None = None) -> list[dict]:
	invoice_rows = queries.get_invoice_page(filters, start, page_size, invoices)
	return build_rows(invoice_rows, start, cint(filters.get("show_item_details")))


def build_rows(invoice_rows: list[dict], start: int, show_items: bool) -> list[dict]:
	names = [row.name for row in invoice_rows]
	payment_methods = queries.get_payment_methods(names)
	items = queries.get_items(names) if show_items else {}

	rows = []
	for idx, invoice in enumerate(invoice_rows, start + 1):
		invoice.update(
			sl_no=idx,
			invoice=invoice.name,
			row_type="invoice",
			payment_method=payment_methods.get(invoice.name, ""),
		)
		rows.append(invoice)

		# item rows carry no invoice amounts, so sums over rows never double-count
		for item in items.get(invoice.name, []):
			item.update(invoice=invoice.name, row_type="item", currency=invoice.currency)
			rows.append(item)

	return rows


def get_report_summary(totals: dict) -> list[dict]:
	return [
		{"key": "invoice_count", "label": _("Invoices"), "value": cint(totals.invoice_count), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Grand Total"), "value": flt(totals.grand_total), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Paid Amount"), "value": flt(totals.paid_amount), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Outstanding Amount"), "value": flt(totals.outstanding_amount), "datatype": "Currency", "indicator": "Red"},
	]
