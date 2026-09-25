# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import escape_html, get_datetime, nowdate


def execute(filters: dict | None = None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	return [
		{"label": _("Employee Checkin Code"), "fieldname": "name", "fieldtype": "Link", "options": "Employee Checkin", "width": 170},
		{"label": _("Employee Code"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Time"), "fieldname": "time", "fieldtype": "Datetime", "width": 160},
		{"label": _("Log Type"), "fieldname": "log_type", "fieldtype": "Data", "width": 90},
		{"label": _("Shift"), "fieldname": "shift", "fieldtype": "Link", "options": "Shift Type", "width": 120},
		{"label": _("Attachment"), "fieldname": "attachment", "fieldtype": "HTML", "width": 120},
	]


def get_data(filters: dict) -> list[dict]:
	from_date = filters.get("from_date") or nowdate()
	to_date = filters.get("to_date") or nowdate()

	checkin = frappe.qb.DocType("Employee Checkin")
	query = (
		frappe.qb.from_(checkin)
		.select(checkin.name, checkin.employee, checkin.employee_name, checkin.time, checkin.log_type, checkin.shift)
		.where(checkin.time >= get_datetime(f"{from_date} 00:00:00"))
		.where(checkin.time <= get_datetime(f"{to_date} 23:59:59"))
		.orderby(checkin.time, order=frappe.qb.desc)
	)

	if employee := filters.get("employee"):
		query = query.where(checkin.employee == employee)

	log_type = filters.get("log_type")
	if log_type and log_type != "All":
		query = query.where(checkin.log_type == log_type)

	data = query.run(as_dict=True)

	attachments = _get_attachment_cells([row.name for row in data])
	for row in data:
		row["attachment"] = attachments.get(row.name, "")

	return data


def _get_attachment_cells(checkin_names: list[str]) -> dict[str, str]:
	"""One batch query for all rows' attachments, instead of a query per row."""
	if not checkin_names:
		return {}

	file = frappe.qb.DocType("File")
	files = (
		frappe.qb.from_(file)
		.select(file.attached_to_name, file.file_url)
		.where(file.attached_to_doctype == "Employee Checkin")
		.where(file.attached_to_name.isin(checkin_names))
		.where(file.is_private == 0)
		.orderby(file.creation)
		.run(as_dict=True)
	)

	# last (most recently created) public file per checkin wins
	urls = {f.attached_to_name: f.file_url for f in files if f.file_url and f.file_url.startswith("/files/")}

	return {
		name: (
			f'<a href="{escape_html(url)}" target="_blank">'
			f'<img src="{escape_html(url)}" style="height: 60px; width: 60px; '
			f'object-fit: cover; border-radius: 3px;"></a>'
		)
		for name, url in urls.items()
	}
