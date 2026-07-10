// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Item Moving"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company") || frappe.defaults.get_user_default("Company"),
					},
				};
			},
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "classification",
			label: __("Classification"),
			fieldtype: "Select",
			options: ["", "Fast Moving", "Slow Moving", "Non-Moving"],
		},
		{
			fieldname: "fast_moving_threshold",
			label: __("Fast Moving Threshold (Qty)"),
			fieldtype: "Float",
			reqd: 1,
			default: 100,
		},
		{
			fieldname: "slow_moving_threshold",
			label: __("Slow Moving Threshold (Qty)"),
			fieldtype: "Float",
			reqd: 1,
			default: 10,
		},
	],
};
