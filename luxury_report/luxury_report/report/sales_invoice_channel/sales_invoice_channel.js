// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

const SIC_METHOD = "luxury_report.luxury_report.report.sales_invoice_channel";

// Any filter change starts again from the first page
function sic_reset_pages() {
	const report = frappe.query_report;
	if (report.get_filter_value("page_count") != 1) {
		report.set_filter_value("page_count", 1);
	} else {
		report.refresh();
	}
}

frappe.query_reports["Sales Invoice Channel"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
			on_change: sic_reset_pages,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			on_change: sic_reset_pages,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			on_change: sic_reset_pages,
		},
		{
			fieldname: "channel",
			label: __("Channel"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Channel", txt),
			on_change: sic_reset_pages,
		},
		{
			fieldname: "payment_status",
			label: __("Paid / Unpaid"),
			fieldtype: "Select",
			options: ["", "Paid", "Unpaid", "Partly Paid"],
			on_change: sic_reset_pages,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "MultiSelectList",
			get_data: () =>
				[
					"Draft",
					"Paid",
					"Unpaid",
					"Partly Paid",
					"Overdue",
					"Unpaid and Discounted",
					"Partly Paid and Discounted",
					"Overdue and Discounted",
					"Return",
					"Credit Note Issued",
					"Consolidated",
					"Internal Transfer",
					"Cancelled",
				].map((value) => ({ value, description: "" })),
			on_change: sic_reset_pages,
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Select",
			options: [""],
			on_change: () => {
				// POS Profiles picked earlier may not belong to the new branch
				frappe.query_report.set_filter_value("pos_profile", []);
				sic_reset_pages();
			},
		},
		{
			fieldname: "pos_profile",
			label: __("POS Profile"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => {
				const branch = frappe.query_report.get_filter_value("branch");
				return frappe.db.get_link_options("POS Profile", txt, branch ? { branch } : {});
			},
			on_change: sic_reset_pages,
		},
		{
			fieldname: "page_size",
			label: __("Page Size"),
			fieldtype: "Select",
			options: ["20", "100", "500", "2500"],
			default: "20",
			on_change: sic_reset_pages,
		},
		{
			fieldname: "page_count",
			label: __("Pages Loaded"),
			fieldtype: "Int",
			default: 1,
			hidden: 1,
		},
	],

	onload: function (report) {
		frappe.call({
			method: `${SIC_METHOD}.sales_invoice_channel.get_branches`,
			callback: (r) => {
				const branch_filter = report.get_filter("branch");
				branch_filter.df.options = [""].concat(r.message || []);
				branch_filter.refresh();
			},
		});

		report.sic_load_more = report.page.add_inner_button(__("Load More"), () => {
			const page_count = cint(report.get_filter_value("page_count")) || 1;
			report.set_filter_value("page_count", page_count + 1);
		});

		report.page.add_inner_button(__("Download Excel"), () => {
			const filters_json = JSON.stringify(report.get_filter_values());
			window.open(
				frappe.urllib.get_full_url(
					`/api/method/${SIC_METHOD}.excel_export.download_excel?filters_json=${encodeURIComponent(filters_json)}`
				)
			);
		});
	},

	after_refresh: function (report) {
		if (!report.sic_load_more) return;

		const summary = (report.raw_data && report.raw_data.report_summary) || [];
		const count_card = summary.find((card) => card.key === "invoice_count");
		const total = count_card ? count_card.value : 0;
		const loaded = (report.data || []).length;
		const has_more = loaded < total;

		report.sic_load_more
			.prop("disabled", !has_more)
			.text(has_more ? __("Load More ({0} of {1})", [loaded, total]) : __("All {0} loaded", [loaded]));
	},
};
