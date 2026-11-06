// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

const PCR_METHOD = "luxury_report.luxury_report.report.pos_commission_report.pos_commission_report";
const PCR_PAGE_SIZES = [20, 100, 500, 2500];
const PCR_STATUS_COLORS = { Submitted: "green", Return: "orange", Cancelled: "red" };

// Any filter change starts again from the first batch
function pcr_refresh() {
	const report = frappe.query_report;
	if (!pcr_dates_valid(report)) return;
	report.refresh();
}

function pcr_dates_valid(report) {
	const from_date = report.get_filter_value("from_date");
	const to_date = report.get_filter_value("to_date");
	if (from_date && to_date && from_date > to_date) {
		frappe.msgprint({ title: __("Invalid Date Range"), message: __("From Date cannot be after To Date."), indicator: "red" });
		return false;
	}
	return true;
}

frappe.query_reports["POS Commission Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
			on_change: pcr_refresh,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
			on_change: pcr_refresh,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
			on_change: pcr_refresh,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			on_change: pcr_refresh,
		},
		{
			fieldname: "cashier",
			label: __("Cashier"),
			fieldtype: "Link",
			options: "User",
			get_query: () => ({ filters: { user_type: "System User", enabled: 1 } }),
			on_change: pcr_refresh,
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
			on_change: () => {
				// POS Profiles picked earlier may not belong to the new branch
				frappe.query_report.set_filter_value("pos_profile", []);
				pcr_refresh();
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
			on_change: pcr_refresh,
		},
		{
			fieldname: "journal_entry",
			label: __("Journal Entry (JV)"),
			fieldtype: "Link",
			options: "Journal Entry",
			// only commission payment JVs
			get_query: () => ({ filters: { commission_sales_invoice: ["is", "set"], docstatus: 1 } }),
			on_change: pcr_refresh,
		},
		{
			fieldname: "page_size",
			label: __("Page Size"),
			fieldtype: "Select",
			options: PCR_PAGE_SIZES.map(String),
			default: String(PCR_PAGE_SIZES[0]),
			// set from the paging area under the table
			hidden: 1,
			on_change: pcr_refresh,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "invoice_status" && data.invoice_status) {
			const color = PCR_STATUS_COLORS[data.invoice_status] || "gray";
			return `<span class="indicator-pill ${color}">${__(data.invoice_status)}</span>`;
		}
		if (column.fieldname === "commission_paid" && flt(data.commission_paid) < 0) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},

	get_datatable_options(options) {
		// the report has its own Sl. No. column that keeps counting across Load More
		return Object.assign(options, { serialNoColumn: false });
	},

	onload(report) {
		pcr_setup_paging_area(report);
	},

	after_refresh(report) {
		pcr_index(report);
		pcr_update_paging_area(report);
	},
};

/* ---------- paging ---------- */

function pcr_index(report) {
	report.pcr_loaded = new Set((report.data || []).map((row) => row.name));
}

function pcr_total_invoices(report) {
	const summary = (report.raw_data && report.raw_data.report_summary) || [];
	const card = summary.find((c) => c.key === "invoice_count");
	return card ? cint(card.value) : 0;
}

// Page size pills and Load More under the table, like the list view paging area
function pcr_setup_paging_area(report) {
	if (report.pcr_paging_area) return;

	const $area = $(
		`<div class="list-paging-area level pcr-paging-area">
			<div class="level-left"></div>
			<div class="level-right">
				<span class="pcr-count text-muted small mr-3"></span>
			</div>
		</div>`
	)
		.hide()
		.insertAfter(report.$report);

	const page_size_buttons = new frappe.ui.TabButtons({
		label: __("Page Size"),
		options: PCR_PAGE_SIZES.map((value) => ({ label: String(value), value })),
		value: cint(report.get_filter_value("page_size")) || PCR_PAGE_SIZES[0],
		// the page_size filter's on_change reloads the first batch with the new size
		on_change: (value) => report.set_filter_value("page_size", String(value)),
	});
	$area.find(".level-left").append(page_size_buttons.$el);

	$area.find(".level-right").append(
		frappe.ui.button({
			label: __("Load More"),
			css_class: "btn-more",
			onclick: () => pcr_load_more(report),
		})
	);

	report.pcr_paging_area = $area;
}

function pcr_update_paging_area(report) {
	const $area = report.pcr_paging_area;
	if (!$area) return;

	const total = pcr_total_invoices(report);
	const loaded = (report.pcr_loaded || new Set()).size;
	$area.toggle(loaded > 0);
	$area.find(".pcr-count").text(
		__("Showing {0} of {1}", [format_number(loaded, null, 0), format_number(total, null, 0)])
	);
	$area.find(".btn-more").toggle(loaded < total);
}

function pcr_load_more(report) {
	const $btn = report.pcr_paging_area.find(".btn-more");
	if ($btn.prop("disabled")) return;
	$btn.prop("disabled", true).text(__("Loading..."));

	frappe
		.call({
			method: `${PCR_METHOD}.get_page`,
			args: { filters: report.get_filter_values(), start: report.pcr_loaded.size },
		})
		.then((r) => {
			// skip invoices already on screen (e.g. new invoices shifted the offset)
			const rows = ((r.message && r.message.rows) || []).filter((row) => !report.pcr_loaded.has(row.name));
			if (rows.length) {
				report.data.push(...rows);
				report.datatable.appendRows(rows);
				rows.forEach((row) => report.pcr_loaded.add(row.name));
			}
			pcr_update_paging_area(report);
		})
		.catch(() => {
			frappe.msgprint({ title: __("Error"), message: __("Could not load more records. Please try again."), indicator: "red" });
		})
		.finally(() => $btn.prop("disabled", false).text(__("Load More")));
}
