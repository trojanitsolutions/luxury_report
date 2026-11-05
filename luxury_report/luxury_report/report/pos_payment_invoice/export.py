# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

"""Excel / CSV export of selected invoices or of every invoice that matches the filters."""

import io
from datetime import date, datetime

import frappe
import xlsxwriter
from frappe import _
from frappe.desk.utils import provide_binary_file
from frappe.utils import cint, flt
from frappe.utils.csvutils import build_csv_response

from . import queries
from .pos_payment_invoice import AMOUNT_FIELDS, build_rows, get_columns

CHUNK_SIZE = 1000
FILE_NAME = "POS_Payment_Invoice"


@frappe.whitelist()
def export_report(filters: str | dict | None = None, invoices: str | list | None = None, file_format: str = "Excel"):
	"""Export selected invoices, or all filtered invoices when nothing is selected.

	Selected invoices are still checked against the current filters.
	"""
	frappe.has_permission("Sales Invoice", "export", throw=True)
	filters = frappe._dict(frappe.parse_json(filters) or {})
	selected = queries.as_list(frappe.parse_json(invoices) if isinstance(invoices, str) else invoices) or None

	columns = [c for c in get_columns(filters) if not c.get("hidden")]
	rows = iter_export_rows(filters, selected)
	filename = f"{FILE_NAME}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

	if file_format == "CSV":
		build_csv_response(_to_table(columns, rows), filename)
	else:
		provide_binary_file(filename, "xlsx", _to_xlsx(columns, rows))


def iter_export_rows(filters, selected: list | None):
	"""Yield report rows in screen order, CHUNK_SIZE invoices per query batch."""
	show_items = cint(filters.get("show_item_details"))
	start = 0
	for batch in _invoice_batches(filters, selected):
		yield from build_rows(batch, start, show_items)
		start += len(batch)


def _invoice_batches(filters, selected: list | None):
	if selected is None:
		start = 0
		while True:
			batch = queries.get_invoice_page(filters, start, CHUNK_SIZE)
			if batch:
				yield batch
			if len(batch) < CHUNK_SIZE:
				return
			start += CHUNK_SIZE
		return

	invoices = []
	names = sorted(set(selected))
	for i in range(0, len(names), CHUNK_SIZE):
		chunk = names[i : i + CHUNK_SIZE]
		invoices += queries.get_invoice_page(filters, 0, len(chunk), chunk)

	invoices.sort(key=lambda row: (row.posting_date, row.name), reverse=True)
	for i in range(0, len(invoices), CHUNK_SIZE):
		yield invoices[i : i + CHUNK_SIZE]


def _to_table(columns, rows) -> list[list]:
	table = [[c["label"] for c in columns]]
	totals = dict.fromkeys(AMOUNT_FIELDS, 0.0)

	for row in rows:
		table.append([_plain(row.get(c["fieldname"])) for c in columns])
		_add_totals(totals, row)

	table.append([_("TOTAL") if i == 0 else totals.get(c["fieldname"], "") for i, c in enumerate(columns)])
	return table


def _to_xlsx(columns, rows) -> bytes:
	output = io.BytesIO()
	workbook = xlsxwriter.Workbook(output, {"in_memory": True, "constant_memory": True})
	formats = _formats(workbook)
	sheet = workbook.add_worksheet(_("POS Invoices"))
	sheet.freeze_panes(1, 0)

	for col, column in enumerate(columns):
		sheet.set_column(col, col, max(column.get("width", 120) // 7, 8))
		sheet.write(0, col, column["label"], formats["header"])

	totals = dict.fromkeys(AMOUNT_FIELDS, 0.0)
	row_num = 0
	for row_num, row in enumerate(rows, 1):
		style = "item" if row.get("row_type") == "item" else "invoice"
		for col, column in enumerate(columns):
			_write_cell(sheet, row_num, col, column, row.get(column["fieldname"]), formats, style)
		_add_totals(totals, row)

	total_row = row_num + 1
	sheet.write(total_row, 0, _("TOTAL"), formats["total"])
	for col, column in enumerate(columns):
		if column["fieldname"] in totals:
			sheet.write_number(total_row, col, totals[column["fieldname"]], formats["total"])

	workbook.close()
	return output.getvalue()


def _write_cell(sheet, row_num, col, column, value, formats, style):
	if value in (None, ""):
		sheet.write_blank(row_num, col, None, formats[f"{style}_text"])
	elif column["fieldtype"] == "Date":
		sheet.write_datetime(row_num, col, datetime.combine(value, datetime.min.time()), formats[f"{style}_date"])
	elif column["fieldtype"] in ("Currency", "Float", "Int"):
		sheet.write_number(row_num, col, flt(value), formats[f"{style}_number"])
	else:
		sheet.write_string(row_num, col, str(value), formats[f"{style}_text"])


def _formats(workbook) -> dict:
	base = {"border": 1}
	item = {"border": 1, "font_color": "#555555", "bg_color": "#F7F7F7"}
	return {
		"header": workbook.add_format({"bold": True, "bg_color": "#4472C4", "font_color": "white", "border": 1}),
		"invoice_text": workbook.add_format(base),
		"invoice_date": workbook.add_format({**base, "num_format": "yyyy-mm-dd"}),
		"invoice_number": workbook.add_format({**base, "num_format": "#,##0.00"}),
		"item_text": workbook.add_format({**item, "indent": 1}),
		"item_date": workbook.add_format({**item, "num_format": "yyyy-mm-dd"}),
		"item_number": workbook.add_format({**item, "num_format": "#,##0.00"}),
		"total": workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "num_format": "#,##0.00"}),
	}


def _add_totals(totals: dict, row: dict):
	if row.get("row_type") == "invoice":
		for field in AMOUNT_FIELDS:
			totals[field] += flt(row.get(field))


def _plain(value):
	if isinstance(value, date):
		return value.isoformat()
	return "" if value is None else value
