# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.utils import provide_binary_file
from frappe.utils.xlsxutils import get_default_xlsx_styles, XLSXStyleBuilder
from .queries import (
	get_so_totals, get_si_totals, get_dn_totals,
	get_so_period_trend, get_si_period_trend, get_dn_period_trend
)
from .analytics import (
	build_main_table, build_kpis, build_comparison_table,
	build_individual_performance, build_historical_analysis
)
import xlsxwriter
from datetime import datetime


@frappe.whitelist()
def download_excel(filters_json=None):
	
	import json
	import tempfile
	import os

	filters = json.loads(filters_json) if isinstance(filters_json, str) else filters_json or {}

	
	so_totals = get_so_totals(filters)
	si_totals = get_si_totals(filters)
	dn_totals = get_dn_totals(filters)
	so_period_trend = get_so_period_trend(filters)
	si_period_trend = get_si_period_trend(filters)
	dn_period_trend = get_dn_period_trend(filters)

	
	main_table = build_main_table(so_totals, si_totals, dn_totals, filters)
	kpis = build_kpis(so_totals, si_totals, dn_totals, main_table)
	comparison = build_comparison_table(main_table)
	historical = build_historical_analysis(so_period_trend, si_period_trend, filters)

	
	filename = f"Salesperson_Performance_Dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
	temp_file = os.path.join(tempfile.gettempdir(), filename)
	workbook = xlsxwriter.Workbook(temp_file)

	
	header_fmt = workbook.add_format({
		'bold': True,
		'bg_color': '#4472C4',
		'font_color': 'white',
		'border': 1,
		'align': 'center',
		'valign': 'vcenter',
	})
	currency_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
	percentage_fmt = workbook.add_format({'num_format': '0.00%', 'border': 1})
	total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D9E1F2', 'border': 1})
	text_fmt = workbook.add_format({'border': 1})

	
	summary_sheet = workbook.add_worksheet(_("Summary"))
	_write_summary_sheet(summary_sheet, kpis, header_fmt, text_fmt, currency_fmt)

	
	perf_sheet = workbook.add_worksheet(_("Performance"))
	_write_performance_sheet(perf_sheet, main_table, header_fmt, text_fmt, currency_fmt, percentage_fmt)

	
	comp_sheet = workbook.add_worksheet(_("Comparison"))
	_write_comparison_sheet(comp_sheet, comparison, header_fmt, text_fmt, currency_fmt)

	
	monthly_sheet = workbook.add_worksheet(_("Monthly Breakdown"))
	_write_monthly_breakdown(monthly_sheet, so_period_trend, header_fmt, text_fmt, currency_fmt)

	
	weekly_sheet = workbook.add_worksheet(_("Weekly Breakdown"))
	_write_weekly_breakdown(weekly_sheet, so_period_trend, header_fmt, text_fmt, currency_fmt)

	
	raw_sheet = workbook.add_worksheet(_("Raw Data"))
	_write_raw_data_sheet(raw_sheet, so_period_trend, si_period_trend, dn_period_trend, header_fmt, text_fmt, currency_fmt)

	
	chart_sheet = workbook.add_worksheet(_("Chart Data"))
	_write_chart_data_sheet(chart_sheet, main_table, header_fmt, text_fmt, currency_fmt)

	workbook.close()

	
	with open(temp_file, 'rb') as f:
		file_content = f.read()

	
	try:
		os.remove(temp_file)
	except:
		pass

	provide_binary_file(filename.replace('.xlsx', ''), 'xlsx', file_content)


def _write_summary_sheet(sheet, kpis, header_fmt, text_fmt, currency_fmt):
	
	sheet.set_column('A:A', 30)
	sheet.set_column('B:B', 20)
	sheet.freeze_panes(1, 0)

	
	sheet.write('A1', _('Metric'), header_fmt)
	sheet.write('B1', _('Value'), header_fmt)

	
	row = 1
	for kpi in kpis:
		sheet.write(row, 0, kpi.get('label', ''), text_fmt)

		value = kpi.get('value', 0)
		if kpi.get('datatype') == 'Currency':
			sheet.write(row, 1, value, currency_fmt)
		elif kpi.get('datatype') == 'Percent':
			sheet.write(row, 1, value / 100, currency_fmt)
		else:
			sheet.write(row, 1, value, text_fmt)

		row += 1


def _write_performance_sheet(sheet, rows, header_fmt, text_fmt, currency_fmt, percentage_fmt):
	
	columns = [
		('sales_person', _('Salesperson'), 20, text_fmt),
		('so_count', _('# SO'), 10, text_fmt),
		('so_amount', _('SO Amount'), 15, currency_fmt),
		('si_amount', _('SI Amount'), 15, currency_fmt),
		('difference', _('Difference'), 15, currency_fmt),
		('difference_pct', _('Diff %'), 10, percentage_fmt),
		('delivered_amount', _('Delivered'), 15, currency_fmt),
		('pending_delivery', _('Pending'), 15, currency_fmt),
		('fully_delivered', _('Fully Delivered'), 12, text_fmt),
		('partial_delivered', _('Partial'), 12, text_fmt),
		('pending_orders', _('Pending Orders'), 12, text_fmt),
		('avg_order_value', _('Avg Order Value'), 15, currency_fmt),
		('customer_count', _('Customers'), 12, text_fmt),
		('invoice_conversion', _('Invoice Conv %'), 12, percentage_fmt),
		('delivery_conversion', _('Delivery Conv %'), 12, percentage_fmt),
		('achievement_pct', _('Achievement %'), 12, percentage_fmt),
	]

	
	for i, (_, label, width, _) in enumerate(columns):
		sheet.set_column(i, i, width)

	sheet.freeze_panes(1, 0)

	
	for i, (_, label, _, fmt) in enumerate(columns):
		sheet.write(0, i, label, header_fmt)

	
	for row_num, row in enumerate(rows, 1):
		for col_num, (field, _, _, fmt) in enumerate(columns):
			value = row.get(field, '')
			sheet.write(row_num, col_num, value, fmt)

	
	if rows:
		total_row = len(rows) + 1
		total_fmt = header_fmt
		sheet.write(total_row, 0, _('TOTAL'), total_fmt)
		for col_num, (field, _, _, _) in enumerate(columns[1:], 1):
			if field in ['so_amount', 'si_amount', 'difference', 'delivered_amount', 'pending_delivery', 'avg_order_value']:
				total = sum(r.get(field, 0) for r in rows)
				sheet.write(total_row, col_num, total, total_fmt)


def _write_comparison_sheet(sheet, rows, header_fmt, text_fmt, currency_fmt):
	
	columns = [
		('rank', _('Rank'), 5),
		('sales_person', _('Salesperson'), 20),
		('so_amount', _('SO Total'), 15),
		('si_amount', _('SI Total'), 15),
		('difference', _('Difference'), 15),
		('difference_pct', _('Diff %'), 10),
		('delivery_conversion', _('Delivery %'), 12),
		('invoice_conversion', _('Achievement %'), 12),
		('growth_pct', _('Growth %'), 10),
		('variance', _('Variance'), 15),
	]

	for i, (_, label, width) in enumerate(columns):
		sheet.set_column(i, i, width)

	sheet.freeze_panes(1, 0)

	for i, (_, label, _) in enumerate(columns):
		sheet.write(0, i, label, header_fmt)

	for row_num, row in enumerate(rows, 1):
		for col_num, (field, _, _) in enumerate(columns):
			value = row.get(field, '')
			if field in ['so_amount', 'si_amount', 'difference', 'variance']:
				sheet.write(row_num, col_num, value, currency_fmt)
			else:
				sheet.write(row_num, col_num, value, text_fmt)


def _write_monthly_breakdown(sheet, trend, header_fmt, text_fmt, currency_fmt):
	
	from collections import defaultdict
	monthly_data = defaultdict(float)

	for row in trend:
		date = row.get('transaction_date')
		if date:
			if isinstance(date, str):
				month_key = date[:7]
			else:
				month_key = date.strftime('%Y-%m')
			monthly_data[month_key] += row.get('so_amount', 0)

	sheet.set_column('A:A', 15)
	sheet.set_column('B:B', 15)
	sheet.freeze_panes(1, 0)

	sheet.write('A1', _('Month'), header_fmt)
	sheet.write('B1', _('Sales Amount'), header_fmt)

	for row_num, (month, amount) in enumerate(sorted(monthly_data.items()), 1):
		sheet.write(row_num, 0, month, text_fmt)
		sheet.write(row_num, 1, amount, currency_fmt)


def _write_weekly_breakdown(sheet, trend, header_fmt, text_fmt, currency_fmt):
	
	from collections import defaultdict
	from datetime import datetime
	weekly_data = defaultdict(float)

	for row in trend:
		date = row.get('transaction_date')
		if date:
			if isinstance(date, str):
				d = datetime.strptime(date, '%Y-%m-%d')
			else:
				d = date
			week_key = d.strftime('%Y-W%U')
			weekly_data[week_key] += row.get('so_amount', 0)

	sheet.set_column('A:A', 15)
	sheet.set_column('B:B', 15)
	sheet.freeze_panes(1, 0)

	sheet.write('A1', _('Week'), header_fmt)
	sheet.write('B1', _('Sales Amount'), header_fmt)

	for row_num, (week, amount) in enumerate(sorted(weekly_data.items()), 1):
		sheet.write(row_num, 0, week, text_fmt)
		sheet.write(row_num, 1, amount, currency_fmt)


def _write_raw_data_sheet(sheet, so_trend, si_trend, dn_trend, header_fmt, text_fmt, currency_fmt):
	
	sheet.set_column('A:D', 15)
	sheet.freeze_panes(1, 0)

	sheet.write('A1', _('Date'), header_fmt)
	sheet.write('B1', _('Salesperson'), header_fmt)
	sheet.write('C1', _('Type'), header_fmt)
	sheet.write('D1', _('Amount'), header_fmt)

	row_num = 1
	for row in so_trend:
		sheet.write(row_num, 0, row.get('transaction_date'), text_fmt)
		sheet.write(row_num, 1, row.get('sales_person'), text_fmt)
		sheet.write(row_num, 2, 'SO', text_fmt)
		sheet.write(row_num, 3, row.get('so_amount', 0), currency_fmt)
		row_num += 1

	for row in si_trend:
		sheet.write(row_num, 0, row.get('transaction_date'), text_fmt)
		sheet.write(row_num, 1, row.get('sales_person'), text_fmt)
		sheet.write(row_num, 2, 'SI', text_fmt)
		sheet.write(row_num, 3, row.get('si_amount', 0), currency_fmt)
		row_num += 1

	for row in dn_trend:
		sheet.write(row_num, 0, row.get('transaction_date'), text_fmt)
		sheet.write(row_num, 1, row.get('sales_person'), text_fmt)
		sheet.write(row_num, 2, 'DN', text_fmt)
		sheet.write(row_num, 3, row.get('delivered_amount', 0), currency_fmt)
		row_num += 1


def _write_chart_data_sheet(sheet, main_rows, header_fmt, text_fmt, currency_fmt):
	
	sheet.set_column('A:B', 20)
	sheet.freeze_panes(1, 0)

	sheet.write('A1', _('Salesperson'), header_fmt)
	sheet.write('B1', _('SO Amount'), header_fmt)

	for row_num, row in enumerate(main_rows, 1):
		sheet.write(row_num, 0, row.get('sales_person'), text_fmt)
		sheet.write(row_num, 1, row.get('so_amount', 0), currency_fmt)
