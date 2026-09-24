# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_datetime, nowdate


def execute(filters: dict | None = None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	return [
		{"label": _("Employee Code"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Datetime", "width": 160},
		{"label": _("Log Type"), "fieldname": "log_type", "fieldtype": "Data", "width": 90},
		{"label": _("Shift"), "fieldname": "shift", "fieldtype": "Link", "options": "Shift Type", "width": 120},
	]


def get_data(filters: dict) -> list[dict]:
	from_date = filters.get("from_date") or nowdate()
	to_date = filters.get("to_date") or nowdate()

	checkin = frappe.qb.DocType("Employee Checkin")
	query = (
		frappe.qb.from_(checkin)
		.select(checkin.employee, checkin.employee_name, checkin.time, checkin.log_type, checkin.shift)
		.where(checkin.time >= get_datetime(f"{from_date} 00:00:00"))
		.where(checkin.time <= get_datetime(f"{to_date} 23:59:59"))
		.orderby(checkin.time, order=frappe.qb.desc)
	)

	if employee := filters.get("employee"):
		query = query.where(checkin.employee == employee)

	log_type = filters.get("log_type")
	if log_type and log_type != "All":
		query = query.where(checkin.log_type == log_type)

	return query.run(as_dict=True)
