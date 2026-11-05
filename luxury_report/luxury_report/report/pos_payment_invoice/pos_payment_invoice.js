// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

const PPI_METHOD = "luxury_report.luxury_report.report.pos_payment_invoice";
const PPI_PAGE_SIZES = [50, 100, 500, 1000, 2500];
const PPI_INVOICE_FIELDS = [
	"sl_no",
	"name",
	"posting_date",
	"customer",
	"customer_name",
	"pos_profile",
	"branch",
	"channel",
	"payment_method",
	"payment_status",
	"grand_total",
	"paid_amount",
	"outstanding_amount",
];
const PPI_STATUS_COLORS = { Paid: "green", Unpaid: "red", "Partially Paid": "orange" };

// Any filter change starts again from the first batch, with an empty selection
function ppi_reset_and_refresh() {
	const report = frappe.query_report;
	if (!ppi_dates_valid(report)) return;
	ppi_selected(report).clear();
	report.refresh();
}

function ppi_dates_valid(report) {
	const from_date = report.get_filter_value("from_date");
	const to_date = report.get_filter_value("to_date");
	if (from_date && to_date && from_date > to_date) {
		frappe.msgprint({ title: __("Invalid Date Range"), message: __("From Date cannot be after To Date."), indicator: "red" });
		return false;
	}
	return true;
}

frappe.query_reports["POS Payment Invoice"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
			on_change: () => {
				// POS Profiles picked earlier may not belong to the new branch
				frappe.query_report.set_filter_value("pos_profile", []);
				ppi_reset_and_refresh();
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
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "mode_of_payment",
			label: __("Payment Method"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Mode of Payment", txt),
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "channel",
			label: __("Channel"),
			fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Channel", txt),
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "payment_status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: ["", "Paid", "Unpaid", "Partially Paid"],
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "invoice",
			label: __("Invoice"),
			fieldtype: "Link",
			options: "Sales Invoice",
			get_query: () => ({ filters: { is_pos: 1, docstatus: 1 } }),
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "show_item_details",
			label: __("Show Item Details"),
			fieldtype: "Check",
			default: 0,
			on_change: ppi_reset_and_refresh,
		},
		{
			fieldname: "page_size",
			label: __("Page Size"),
			fieldtype: "Select",
			options: PPI_PAGE_SIZES.map(String),
			default: String(PPI_PAGE_SIZES[0]),
			// set from the paging area under the table
			hidden: 1,
			on_change: ppi_reset_and_refresh,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (data.row_type === "item") {
			if (column.fieldname === "item_code") {
				return `<span class="text-muted" style="padding-left: 16px">↳ ${value}</span>`;
			}
			return `<span class="text-muted">${value}</span>`;
		}

		if (column.fieldname === "payment_status" && data.payment_status) {
			const color = PPI_STATUS_COLORS[data.payment_status] || "gray";
			return `<span class="indicator-pill ${color}">${__(data.payment_status)}</span>`;
		}
		if (frappe.query_report.get_filter_value("show_item_details") && PPI_INVOICE_FIELDS.includes(column.fieldname)) {
			return `<b>${value}</b>`;
		}
		return value;
	},

	get_datatable_options(options) {
		return Object.assign(options, {
			checkboxColumn: true,
			// the report has its own invoice-level Sl. No. column
			serialNoColumn: false,
			events: {
				onCheckRow: (row) => ppi_on_check_row(frappe.query_report, row),
			},
		});
	},

	onload(report) {
		ppi_setup_paging_area(report);
		report.page.add_inner_button(__("Export Selected"), () => ppi_export(report, true), __("Export"));
		report.page.add_inner_button(__("Export All Filtered"), () => ppi_export(report, false), __("Export"));
	},

	after_refresh(report) {
		// a refresh always reloads the first batch, so earlier checks no longer apply
		ppi_reindex(report);
		ppi_clear_selection(report);
		ppi_update_paging_area(report);
	},
};

/* ---------- selection ---------- */

function ppi_selected(report) {
	if (!report.ppi_selected) report.ppi_selected = new Set();
	return report.ppi_selected;
}

// invoice name -> datatable row indexes, so all lines of an invoice are checked together
function ppi_reindex(report) {
	report.ppi_rows_by_invoice = {};
	(report.data || []).forEach((row, index) => {
		(report.ppi_rows_by_invoice[row.invoice] ||= []).push(index);
	});
}

function ppi_on_check_row(report, row) {
	if (report.ppi_syncing || !report.datatable) return;
	const rowmanager = report.datatable.rowmanager;
	const selected = ppi_selected(report);

	if (!row) {
		// header Select All / unselect all over the loaded rows
		selected.clear();
		rowmanager.getCheckedRows().forEach((index) => {
			const data = report.data[index];
			if (data) selected.add(data.invoice);
		});
		ppi_apply_selection(report);
	} else {
		const data = report.data[row.meta.rowIndex];
		if (!data) return;
		const checked = rowmanager.checkMap[row.meta.rowIndex] === 1;
		if (checked) selected.add(data.invoice);
		else selected.delete(data.invoice);
		ppi_set_invoice_checked(report, data.invoice, checked);
	}
	ppi_update_selection_count(report);
}

function ppi_set_invoice_checked(report, invoice, checked) {
	const rowmanager = report.datatable.rowmanager;
	report.ppi_syncing = true;
	try {
		(report.ppi_rows_by_invoice[invoice] || []).forEach((index) => {
			if ((rowmanager.checkMap[index] === 1) !== checked) rowmanager.checkRow(index, checked);
		});
	} finally {
		report.ppi_syncing = false;
	}
}

// re-check every row of the selected invoices, e.g. after Load More re-renders the body
function ppi_apply_selection(report) {
	ppi_selected(report).forEach((invoice) => ppi_set_invoice_checked(report, invoice, true));
}

function ppi_clear_selection(report) {
	ppi_selected(report).clear();
	if (report.datatable) {
		report.ppi_syncing = true;
		try {
			report.datatable.rowmanager.checkAll(false);
		} finally {
			report.ppi_syncing = false;
		}
	}
	ppi_update_selection_count(report);
}

function ppi_update_selection_count(report) {
	const $area = report.ppi_paging_area;
	if (!$area) return;
	const count = ppi_selected(report).size;
	$area.find(".ppi-selected-count").text(__("{0} invoice(s) selected", [format_number(count, null, 0)]));
	$area.find(".ppi-selection").toggle(count > 0);
}

/* ---------- paging ---------- */

function ppi_total_invoices(report) {
	const summary = (report.raw_data && report.raw_data.report_summary) || [];
	const card = summary.find((c) => c.key === "invoice_count");
	return card ? cint(card.value) : 0;
}

function ppi_loaded_invoices(report) {
	return Object.keys(report.ppi_rows_by_invoice || {}).length;
}

// Page size pills, Load More and the selection count under the table, like the list view paging area
function ppi_setup_paging_area(report) {
	if (report.ppi_paging_area) return;

	const $area = $(
		`<div class="list-paging-area level ppi-paging-area">
			<div class="level-left"></div>
			<div class="level-right">
				<span class="ppi-selection mr-3" style="display: none">
					<span class="ppi-selected-count text-muted small mr-2"></span>
				</span>
				<span class="ppi-count text-muted small mr-3"></span>
			</div>
		</div>`
	)
		.hide()
		.insertAfter(report.$report);

	const page_size_buttons = new frappe.ui.TabButtons({
		label: __("Page Size"),
		options: PPI_PAGE_SIZES.map((value) => ({ label: String(value), value })),
		value: cint(report.get_filter_value("page_size")) || PPI_PAGE_SIZES[0],
		// the page_size filter's on_change reloads the first batch with the new size
		on_change: (value) => report.set_filter_value("page_size", String(value)),
	});
	$area.find(".level-left").append(page_size_buttons.$el);

	$area.find(".ppi-selection").append(
		frappe.ui.button({
			label: __("Clear Selection"),
			css_class: "btn-xs btn-default",
			onclick: () => ppi_clear_selection(report),
		})
	);
	$area.find(".level-right").append(
		frappe.ui.button({
			label: __("Load More"),
			css_class: "btn-more",
			onclick: () => ppi_load_more(report),
		})
	);

	report.ppi_paging_area = $area;
}

function ppi_update_paging_area(report) {
	const $area = report.ppi_paging_area;
	if (!$area) return;

	const total = ppi_total_invoices(report);
	const loaded = ppi_loaded_invoices(report);
	$area.toggle(loaded > 0);
	$area.find(".ppi-count").text(
		__("Showing {0} of {1}", [format_number(loaded, null, 0), format_number(total, null, 0)])
	);
	$area.find(".btn-more").toggle(loaded < total);
	ppi_update_selection_count(report);
}

function ppi_load_more(report) {
	const $btn = report.ppi_paging_area.find(".btn-more");
	if ($btn.prop("disabled")) return;
	$btn.prop("disabled", true).text(__("Loading..."));

	frappe
		.call({
			method: `${PPI_METHOD}.pos_payment_invoice.get_page`,
			args: { filters: report.get_filter_values(), start: ppi_loaded_invoices(report) },
		})
		.then((r) => {
			// skip invoices already on screen (e.g. new invoices shifted the offset)
			const loaded = report.ppi_rows_by_invoice || {};
			const rows = ((r.message && r.message.rows) || []).filter((row) => !loaded[row.invoice]);
			if (rows.length) {
				report.data.push(...rows);
				report.datatable.appendRows(rows);
				ppi_reindex(report);
				ppi_apply_selection(report);
			}
			ppi_update_paging_area(report);
		})
		.catch(() => {
			frappe.msgprint({ title: __("Error"), message: __("Could not load more records. Please try again."), indicator: "red" });
		})
		.finally(() => $btn.prop("disabled", false).text(__("Load More")));
}

/* ---------- export ---------- */

function ppi_export(report, only_selected) {
	const invoices = Array.from(ppi_selected(report));

	if (only_selected && !invoices.length) {
		frappe.confirm(__("No invoices are selected. Export all invoices that match the current filters?"), () =>
			ppi_export(report, false)
		);
		return;
	}

	frappe.prompt(
		{
			fieldname: "file_format",
			label: __("File Format"),
			fieldtype: "Select",
			options: ["Excel", "CSV"],
			default: "Excel",
			reqd: 1,
		},
		({ file_format }) => {
			open_url_post(frappe.request.url, {
				cmd: `${PPI_METHOD}.export.export_report`,
				filters: report.get_filter_values(),
				invoices: only_selected ? invoices : [],
				file_format,
			});
		},
		only_selected ? __("Export {0} Selected Invoice(s)", [invoices.length]) : __("Export All Filtered Invoices"),
		__("Export")
	);
}
