// Copyright (c) 2026, Trojan IT Solutions and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Person Wise Sales"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
			get_query: function () {
				return {
					filters: { enabled: 1 }
				};
			},
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
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
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "so_status",
			label: __("SO Status"),
			fieldtype: "MultiSelectList",
			get_data: function () {
				return [
					{ label: __("Draft"), value: "Draft" },
					{ label: __("To Deliver"), value: "To Deliver and Bill" },
					{ label: __("Partially Delivered"), value: "Partly Delivered" },
					{ label: __("Delivered"), value: "To Bill" },
					{ label: __("Closed"), value: "Closed" },
					{ label: __("Cancelled"), value: "Cancelled" },
				];
			},
		},
		{
			fieldname: "delivery_status",
			label: __("Delivery Status"),
			fieldtype: "MultiSelectList",
			get_data: function () {
				return [
					{ label: __("Pending"), value: "Not Delivered" },
					{ label: __("Partially Delivered"), value: "Partly Delivered" },
					{ label: __("Fully Delivered"), value: "Fully Delivered" },
				];
			},
		},
		{
			fieldname: "invoice_status",
			label: __("Invoice Status"),
			fieldtype: "MultiSelectList",
			get_data: function () {
				return [
					{ label: __("Not Invoiced"), value: "Not Billed" },
					{ label: __("Partially Invoiced"), value: "Partly Billed" },
					{ label: __("Fully Invoiced"), value: "Fully Billed" },
				];
			},
		},
		{
			fieldname: "grouping",
			label: __("Grouping"),
			fieldtype: "Select",
			options: "Daily\nWeekly\nMonthly\nQuarterly\nYearly",
			default: "Monthly",
		},
		{
			fieldname: "comparison_mode",
			label: __("Comparison Mode"),
			fieldtype: "Select",
			options: "Compare Salespersons\nIndividual Salesperson",
			default: "Compare Salespersons",
		},
		{
			fieldname: "top_n",
			label: __("Top N Salespersons"),
			fieldtype: "Int",
			default: 10,
		},
	],
	onload: function (report) {
		// Inject dashboard container
		const $dashboard = $(`
			<div class="spws-dashboard" style="margin-top: 20px; padding: 20px; background: #f8f9fa; border-radius: 4px;">
				<div class="spws-comparison-section" style="display: none;">
					<h4>${__("Comparison Dashboard")}</h4>
					<div id="spws-comparison-table"></div>
				</div>
				<div class="spws-individual-section" style="display: none;">
					<h4>${__("Individual Performance Analysis")}</h4>
					<div style="margin-bottom: 10px;">
						<button class="btn btn-xs btn-default spws-grouping-btn" data-grouping="Daily">${__("Daily")}</button>
						<button class="btn btn-xs btn-default spws-grouping-btn" data-grouping="Weekly">${__("Weekly")}</button>
						<button class="btn btn-xs btn-default spws-grouping-btn active" data-grouping="Monthly">${__("Monthly")}</button>
						<button class="btn btn-xs btn-default spws-grouping-btn" data-grouping="Quarterly">${__("Quarterly")}</button>
						<button class="btn btn-xs btn-default spws-grouping-btn" data-grouping="Yearly">${__("Yearly")}</button>
					</div>
					<div id="spws-individual-performance"></div>
					<div id="spws-individual-chart" style="margin-top: 20px;"></div>
				</div>
				<div class="spws-historical-section" style="display: none;">
					<h4>${__("Historical Analysis")}</h4>
					<div id="spws-historical-table"></div>
				</div>
				<div style="margin-top: 30px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;">
					<div id="spws-monthly-trend-chart"></div>
					<div id="spws-weekly-trend-chart"></div>
					<div id="spws-delivery-status-chart"></div>
					<div id="spws-invoice-conversion-chart"></div>
					<div id="spws-top-salespersons-chart"></div>
					<div id="spws-yoy-chart"></div>
					<div id="spws-heatmap-chart"></div>
					<div id="spws-achievement-gauge-chart"></div>
				</div>
			</div>
		`);

		report.$spws = $dashboard.insertAfter(report.$report);

		// Add Excel download button
		report.page.add_inner_button(__("Download Excel"), function () {
			const filters = report.get_filter_values();
			const filters_json = JSON.stringify(filters);
			const url = frappe.urllib.get_full_url(
				`/api/method/luxury_report.luxury_report.report.sales_person_wise_sales.excel_export.download_excel?filters_json=${encodeURIComponent(filters_json)}`
			);
			window.open(url);
		}, __("Actions"));

		// Bind grouping button clicks
		$(document).on("click", ".spws-grouping-btn", function () {
			$(".spws-grouping-btn").removeClass("active");
			$(this).addClass("active");
			const grouping = $(this).data("grouping");
			frappe.query_report.set_filter_value("grouping", grouping);
		});
	},

	after_refresh: function (report) {
		const filters = report.get_filter_values();
		const comparison_mode = filters.comparison_mode || "Compare Salespersons";

		// Hide/show sections based on comparison mode
		if (comparison_mode === "Individual Salesperson") {
			report.$spws.find(".spws-comparison-section").hide();
			report.$spws.find(".spws-individual-section").show();
			report.$spws.find(".spws-historical-section").show();
		} else {
			report.$spws.find(".spws-comparison-section").show();
			report.$spws.find(".spws-individual-section").hide();
			report.$spws.find(".spws-historical-section").hide();
		}

		// Fetch dashboard data
		frappe.call({
			method: "luxury_report.luxury_report.report.sales_person_wise_sales.sales_person_wise_sales.get_dashboard_data",
			args: { filters_json: JSON.stringify(filters) },
			callback: function (r) {
				if (!r.message) return;

				const dashboard = r.message;

				// Render comparison table
				if (dashboard.comparison && dashboard.comparison.length > 0) {
					_render_comparison_table("#spws-comparison-table", dashboard.comparison);
				}

				// Render individual performance
				if (dashboard.individual_performance) {
					_render_individual_performance("#spws-individual-performance", dashboard.individual_performance);
					_render_individual_chart("#spws-individual-chart", dashboard.individual_performance.trend_data);
				}

				// Render extra charts
				if (dashboard.extra_charts) {
					_render_extra_charts(dashboard.extra_charts, report.$spws);
				}
			},
		});
	},
};

function _render_comparison_table($selector, rows) {
	const $table = $(`
		<table class="table table-bordered table-striped">
			<thead>
				<tr>
					<th>${__("Rank")}</th>
					<th>${__("Salesperson")}</th>
					<th>${__("SO Total")}</th>
					<th>${__("SI Total")}</th>
					<th>${__("Difference")}</th>
					<th>${__("Diff %")}</th>
					<th>${__("Delivery %")}</th>
					<th>${__("Achievement %")}</th>
				</tr>
			</thead>
			<tbody></tbody>
		</table>
	`);

	rows.forEach(row => {
		const $tr = $(`
			<tr>
				<td>${row.rank || ""}</td>
				<td>${row.sales_person || ""}</td>
				<td>${frappe.format(row.so_amount || 0, { fieldtype: "Currency" })}</td>
				<td>${frappe.format(row.si_amount || 0, { fieldtype: "Currency" })}</td>
				<td>${frappe.format(row.difference || 0, { fieldtype: "Currency" })}</td>
				<td>${(row.difference_pct || 0).toFixed(2)}%</td>
				<td>${(row.delivery_conversion || 0).toFixed(2)}%</td>
				<td>${(row.achievement_pct || 0).toFixed(2)}%</td>
			</tr>
		`);
		$table.find("tbody").append($tr);
	});

	$($selector).empty().append($table);
}

function _render_individual_performance($selector, perf) {
	const html = `
		<div class="row" style="margin-bottom: 10px;">
			<div class="col-md-2"><strong>${__("Avg Sales")}</strong>: ${frappe.format(perf.average_sales || 0, { fieldtype: "Currency" })}</div>
			<div class="col-md-2"><strong>${__("Avg Invoices")}</strong>: ${frappe.format(perf.average_invoices || 0, { fieldtype: "Currency" })}</div>
			<div class="col-md-2"><strong>${__("Avg Delivered")}</strong>: ${frappe.format(perf.average_delivered || 0, { fieldtype: "Currency" })}</div>
			<div class="col-md-2"><strong>${__("Growth %")}</strong>: ${(perf.growth_pct || 0).toFixed(2)}%</div>
			<div class="col-md-2"><strong>${__("Performance Score")}</strong>: ${(perf.performance_score || 0).toFixed(2)}</div>
		</div>
	`;
	$($selector).empty().html(html);
}

function _render_individual_chart($selector, trend_data) {
	if (!trend_data || Object.keys(trend_data).length === 0) return;

	const labels = Object.keys(trend_data).sort();
	const values = labels.map(l => trend_data[l]);

	const options = {
		data: {
			labels: labels,
			datasets: [{ name: __("Sales"), values: values }],
		},
		type: "line",
	};

	const chart = new frappe.Chart($($selector)[0], options);
}

function _render_extra_charts(extra_charts, $parent) {
	const chart_configs = [
		{ key: "monthly_sales_trend", selector: "#spws-monthly-trend-chart" },
		{ key: "weekly_trend", selector: "#spws-weekly-trend-chart" },
		{ key: "delivery_status_distribution", selector: "#spws-delivery-status-chart" },
		{ key: "invoice_conversion_trend", selector: "#spws-invoice-conversion-chart" },
		{ key: "top_salespersons", selector: "#spws-top-salespersons-chart" },
		{ key: "yoy_comparison", selector: "#spws-yoy-chart" },
		{ key: "monthly_heatmap", selector: "#spws-heatmap-chart" },
		{ key: "achievement_gauge", selector: "#spws-achievement-gauge-chart" },
	];

	chart_configs.forEach(cfg => {
		const data = extra_charts[cfg.key];
		if (data) {
			const $container = $parent.find(cfg.selector);
			if ($container.length) {
				$container.empty();
				new frappe.Chart($container[0], data);
			}
		}
	});
}
