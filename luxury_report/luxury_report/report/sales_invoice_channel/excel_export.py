# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import io
from datetime import datetime

import frappe
import xlsxwriter
from frappe import _
from frappe.desk.utils import provide_binary_file

from .sales_invoice_channel import get_columns, get_data, get_report_summary, get_row_limit, get_totals

TOTAL_FIELDS = ("grand_total", "paid_amount", "outstanding_amount")


@frappe.whitelist()
def download_excel(filters_json=None):
	"""Export the same rows the report shows on screen (page size x pages loaded)."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	filters = frappe._dict(frappe.parse_json(filters_json) or {})

	rows = get_data(filters, get_row_limit(filters))
	summary = get_report_summary(get_totals(filters))

	output = io.BytesIO()
	workbook = xlsxwriter.Workbook(output, {"in_memory": True})
	formats = {
		"header": workbook.add_format({"bold": True, "bg_color": "#4472C4", "font_color": "white", "border": 1}),
		"text": workbook.add_format({"border": 1}),
		"date": workbook.add_format({"border": 1, "num_format": "yyyy-mm-dd"}),
		"currency": workbook.add_format({"border": 1, "num_format": "#,##0.00"}),
		"total": workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "num_format": "#,##0.00"}),
	}

	_write_invoices_sheet(workbook.add_worksheet(_("Invoices")), rows, formats)
	_write_summary_sheet(workbook.add_worksheet(_("Summary")), summary, formats)
	workbook.close()

	filename = f"Sales_Invoice_Channel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
	provide_binary_file(filename, "xlsx", output.getvalue())


def _write_invoices_sheet(sheet, rows, formats):
	columns = get_columns()
	sheet.freeze_panes(1, 0)

	for col, column in enumerate(columns):
		sheet.set_column(col, col, max(column.get("width", 120) // 7, 10))
		sheet.write(0, col, column["label"], formats["header"])

	for row_num, row in enumerate(rows, 1):
		for col, column in enumerate(columns):
			value = row.get(column["fieldname"])
			if column["fieldtype"] == "Date" and value:
				sheet.write_datetime(row_num, col, datetime.combine(value, datetime.min.time()), formats["date"])
			elif column["fieldtype"] == "Currency":
				sheet.write_number(row_num, col, value or 0, formats["currency"])
			else:
				sheet.write(row_num, col, value or "", formats["text"])

	total_row = len(rows) + 1
	sheet.write(total_row, 0, _("TOTAL"), formats["total"])
	for col, column in enumerate(columns):
		if column["fieldname"] in TOTAL_FIELDS:
			sheet.write_number(total_row, col, sum(r.get(column["fieldname"]) or 0 for r in rows), formats["total"])


def _write_summary_sheet(sheet, summary, formats):
	sheet.set_column(0, 0, 25)
	sheet.set_column(1, 1, 20)
	sheet.write(0, 0, _("Metric"), formats["header"])
	sheet.write(0, 1, _("Value (all matching invoices)"), formats["header"])

	for row_num, card in enumerate(summary, 1):
		value_format = formats["currency"] if card["datatype"] == "Currency" else formats["text"]
		sheet.write(row_num, 0, card["label"], formats["text"])
		sheet.write_number(row_num, 1, card["value"], value_format)
