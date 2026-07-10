# Copyright (c) 2026, Trojan IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import get_first_day, get_quarter_start, get_year_start
from erpnext.accounts.utils import get_fiscal_year


def build_common_conditions(filters, doctype="Sales Order"):
	
	conditions = []
	values = []

	company = filters.get("company")
	if company:
		conditions.append("dt.company = %s")
		values.append(company)

	
	date_field = "dt.transaction_date" if doctype == "Sales Order" else "dt.posting_date"

	date_range = _resolve_date_range(filters)
	if date_range:
		from_date, to_date = date_range
		conditions.append(f"{date_field} >= %s")
		values.append(from_date)
		conditions.append(f"{date_field} <= %s")
		values.append(to_date)

	customer = filters.get("customer")
	if customer:
		conditions.append("dt.customer = %s")
		values.append(customer)

	territory = filters.get("territory")
	if territory:
		conditions.append("dt.territory = %s")
		values.append(territory)

	cost_center = filters.get("cost_center")
	if cost_center:
		conditions.append("dt.cost_center = %s")
		values.append(cost_center)

	project = filters.get("project")
	if project:
		conditions.append("dt.project = %s")
		values.append(project)

	
	item_group_list = filters.get("item_group")
	if item_group_list:
		item_groups = _resolve_item_group_hierarchy(item_group_list)
		if item_groups:
			placeholders = ",".join(["%s"] * len(item_groups))
			conditions.append(f"dt_item.item_group IN ({placeholders})")
			values.extend(item_groups)

	brand = filters.get("brand")
	if brand:
		conditions.append("dt_item.brand = %s")
		values.append(brand)

	warehouse = filters.get("warehouse")
	if warehouse:
		conditions.append("dt_item.warehouse = %s")
		values.append(warehouse)

	where = " AND ".join(conditions) if conditions else "1=1"
	return where, values


def _resolve_date_range(filters):
	
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if from_date and to_date:
		return (from_date, to_date)

	fiscal_year = filters.get("fiscal_year")
	if fiscal_year:
		fy = get_fiscal_year(fiscal_year, as_dict=True)
		return (fy.get("year_start_date"), fy.get("year_end_date"))

	
	fy = get_fiscal_year(as_dict=True)
	return (fy.get("year_start_date"), fy.get("year_end_date"))


def _resolve_item_group_hierarchy(item_groups):
	
	if not item_groups:
		return []

	if isinstance(item_groups, str):
		item_groups = [item_groups]

	result = []
	for ig in item_groups:
		lft, rgt = frappe.db.get_value("Item Group", ig, ["lft", "rgt"]) or (None, None)
		if lft is not None and rgt is not None:
			child_groups = frappe.db.get_list(
				"Item Group",
				filters={"lft": [">=", lft], "rgt": ["<=", rgt]},
				pluck="name"
			)
			result.extend(child_groups)

	return list(set(result))


def _resolve_sales_person_hierarchy(sales_persons):
	
	if not sales_persons:
		return []

	if isinstance(sales_persons, str):
		sales_persons = [sales_persons]

	result = []
	for sp in sales_persons:
		lft, rgt = frappe.db.get_value("Sales Person", sp, ["lft", "rgt"]) or (None, None)
		if lft is not None and rgt is not None:
			child_sps = frappe.db.get_list(
				"Sales Person",
				filters={"lft": [">=", lft], "rgt": ["<=", rgt], "enabled": 1},
				pluck="name"
			)
			result.extend(child_sps)

	return list(set(result))


def _apply_sales_person_filter(conditions, values, filters):
	
	sales_person = filters.get("sales_person")
	if not sales_person:
		return conditions, values

	sales_persons = _resolve_sales_person_hierarchy(sales_person)
	if sales_persons:
		placeholders = ",".join(["%s"] * len(sales_persons))
		conditions.append(f"st.sales_person IN ({placeholders})")
		values.extend(sales_persons)

	return conditions, values


def _apply_status_filters(conditions, values, filters, doctype):
	
	if doctype == "Sales Order":
		so_status = filters.get("so_status")
		if so_status:
			if isinstance(so_status, str):
				so_status = [so_status]
			if so_status:
				placeholders = ",".join(["%s"] * len(so_status))
				conditions.append(f"dt.status IN ({placeholders})")
				values.extend(so_status)

		delivery_status = filters.get("delivery_status")
		if delivery_status:
			if isinstance(delivery_status, str):
				delivery_status = [delivery_status]
			if delivery_status:
				placeholders = ",".join(["%s"] * len(delivery_status))
				conditions.append(f"dt.delivery_status IN ({placeholders})")
				values.extend(delivery_status)

	elif doctype == "Sales Invoice":
		si_status = filters.get("si_status")
		if si_status:
			if isinstance(si_status, str):
				si_status = [si_status]
			if si_status:
				placeholders = ",".join(["%s"] * len(si_status))
				conditions.append(f"dt.status IN ({placeholders})")
				values.extend(si_status)

		billing_status = filters.get("invoice_status")
		if billing_status:
			if isinstance(billing_status, str):
				billing_status = [billing_status]
			if billing_status:
				placeholders = ",".join(["%s"] * len(billing_status))
				conditions.append(f"dt.billing_status IN ({placeholders})")
				values.extend(billing_status)

	return conditions, values


def get_so_totals(filters):
	
	conditions = ["dt.docstatus = 1"]
	values = []

	base_where, base_values = build_common_conditions(filters, "Sales Order")
	if base_where != "1=1":
		conditions.append(base_where)
		values.extend(base_values)

	conditions, values = _apply_sales_person_filter(conditions, values, filters)
	conditions, values = _apply_status_filters(conditions, values, filters, "Sales Order")

	where = " AND ".join(conditions)

	sql = """
		SELECT
			st.sales_person,
			COUNT(DISTINCT dt.name) as so_count,
			COUNT(DISTINCT dt.customer) as customer_count,
			SUM(COALESCE(dt_item.base_net_amount * st.allocated_percentage / 100, 0)) as so_amount,
			COUNT(DISTINCT CASE WHEN dt.delivery_status = 'Fully Delivered' THEN dt.name END) as fully_delivered_orders,
			COUNT(DISTINCT CASE WHEN dt.delivery_status = 'Partly Delivered' THEN dt.name END) as partial_delivered_orders,
			COUNT(DISTINCT CASE WHEN dt.delivery_status = 'Not Delivered' THEN dt.name END) as pending_orders,
			SUM(COALESCE(CASE WHEN dt.billing_status = 'Fully Billed' THEN dt_item.base_net_amount * st.allocated_percentage / 100 ELSE 0 END, 0)) as fully_billed_amount
		FROM `tabSales Order` dt
		INNER JOIN `tabSales Order Item` dt_item ON dt_item.parent = dt.name
		INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Sales Order'
		WHERE {}
		GROUP BY st.sales_person
	""".format(where)

	result = frappe.db.sql(sql, tuple(values), as_dict=True)
	return {row.sales_person: row for row in result}


def get_si_totals(filters):
	
	conditions = ["dt.docstatus = 1"]
	values = []

	base_where, base_values = build_common_conditions(filters, "Sales Invoice")
	if base_where != "1=1":
		conditions.append(base_where)
		values.extend(base_values)

	conditions, values = _apply_sales_person_filter(conditions, values, filters)
	conditions, values = _apply_status_filters(conditions, values, filters, "Sales Invoice")

	where = " AND ".join(conditions)

	sql = """
		SELECT
			st.sales_person,
			SUM(COALESCE(dt_item.base_net_amount * st.allocated_percentage / 100, 0)) as si_amount,
			COUNT(DISTINCT dt.name) as si_count
		FROM `tabSales Invoice` dt
		INNER JOIN `tabSales Invoice Item` dt_item ON dt_item.parent = dt.name
		INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Sales Invoice'
		WHERE {}
		GROUP BY st.sales_person
	""".format(where)

	result = frappe.db.sql(sql, tuple(values), as_dict=True)
	return {row.sales_person: row for row in result}


def get_dn_totals(filters):
	
	conditions = ["dt.docstatus = 1"]
	values = []

	base_where, base_values = build_common_conditions(filters, "Delivery Note")
	if base_where != "1=1":
		conditions.append(base_where)
		values.extend(base_values)

	conditions, values = _apply_sales_person_filter(conditions, values, filters)

	where = " AND ".join(conditions)

	sql = """
		SELECT
			st.sales_person,
			SUM(COALESCE(dt_item.base_net_amount * st.allocated_percentage / 100, 0)) as delivered_amount
		FROM `tabDelivery Note` dt
		INNER JOIN `tabDelivery Note Item` dt_item ON dt_item.parent = dt.name
		INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Delivery Note'
		WHERE {}
		GROUP BY st.sales_person
	""".format(where)

	result = frappe.db.sql(sql, tuple(values), as_dict=True)
	return {row.sales_person: row for row in result}


def get_so_period_trend(filters):
	
	conditions = ["dt.docstatus = 1"]
	values = []

	base_where, base_values = build_common_conditions(filters, "Sales Order")
	if base_where != "1=1":
		conditions.append(base_where)
		values.extend(base_values)

	conditions, values = _apply_sales_person_filter(conditions, values, filters)
	conditions, values = _apply_status_filters(conditions, values, filters, "Sales Order")

	where = " AND ".join(conditions)

	sql = """
		SELECT
			st.sales_person,
			dt.transaction_date,
			COUNT(DISTINCT dt.name) as so_count,
			SUM(COALESCE(dt_item.base_net_amount * st.allocated_percentage / 100, 0)) as so_amount
		FROM `tabSales Order` dt
		INNER JOIN `tabSales Order Item` dt_item ON dt_item.parent = dt.name
		INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Sales Order'
		WHERE {}
		GROUP BY st.sales_person, dt.transaction_date
		ORDER BY dt.transaction_date
	""".format(where)

	result = frappe.db.sql(sql, tuple(values), as_dict=True)
	return result


def get_si_period_trend(filters):
	
	conditions = ["dt.docstatus = 1"]
	values = []

	base_where, base_values = build_common_conditions(filters, "Sales Invoice")
	if base_where != "1=1":
		conditions.append(base_where)
		values.extend(base_values)

	conditions, values = _apply_sales_person_filter(conditions, values, filters)
	conditions, values = _apply_status_filters(conditions, values, filters, "Sales Invoice")

	where = " AND ".join(conditions)

	sql = """
		SELECT
			st.sales_person,
			dt.posting_date as transaction_date,
			COUNT(DISTINCT dt.name) as si_count,
			SUM(COALESCE(dt_item.base_net_amount * st.allocated_percentage / 100, 0)) as si_amount
		FROM `tabSales Invoice` dt
		INNER JOIN `tabSales Invoice Item` dt_item ON dt_item.parent = dt.name
		INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Sales Invoice'
		WHERE {}
		GROUP BY st.sales_person, dt.posting_date
		ORDER BY dt.posting_date
	""".format(where)

	result = frappe.db.sql(sql, tuple(values), as_dict=True)
	return result


def get_dn_period_trend(filters):
	
	conditions = ["dt.docstatus = 1"]
	values = []

	base_where, base_values = build_common_conditions(filters, "Delivery Note")
	if base_where != "1=1":
		conditions.append(base_where)
		values.extend(base_values)

	conditions, values = _apply_sales_person_filter(conditions, values, filters)

	where = " AND ".join(conditions)

	sql = """
		SELECT
			st.sales_person,
			dt.posting_date as transaction_date,
			COUNT(DISTINCT dt.name) as dn_count,
			SUM(COALESCE(dt_item.base_net_amount * st.allocated_percentage / 100, 0)) as delivered_amount
		FROM `tabDelivery Note` dt
		INNER JOIN `tabDelivery Note Item` dt_item ON dt_item.parent = dt.name
		INNER JOIN `tabSales Team` st ON st.parent = dt.name AND st.parenttype = 'Delivery Note'
		WHERE {}
		GROUP BY st.sales_person, dt.posting_date
		ORDER BY dt.posting_date
	""".format(where)

	result = frappe.db.sql(sql, tuple(values), as_dict=True)
	return result
