// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Checkin"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "today",
			label: __("Today"),
			fieldtype: "Check",
			default: 1,
			on_change: () => {
				if (!frappe.query_report.get_filter_value("today")) return;
				const today = frappe.datetime.get_today();
				frappe.query_report.set_filter_value({
					from_date: today,
					to_date: today,
				});
			},
		},
		{
			fieldname: "log_type",
			label: __("Log Type"),
			fieldtype: "Select",
			options: "All\nIN\nOUT",
			default: "All",
		},
	],
};
