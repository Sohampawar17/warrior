// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Auto Order Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": "From Date",
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": "To Date",
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		}
	],
	after_datatable_render: function () {
		layout_side_by_side();
		render_total_chart();
	}
};

function layout_side_by_side() {
	const report = frappe.query_report;
	if (!report || !report.$chart) return;

	if (!report.$charts_row) {
		report.$charts_row = $(
			'<div class="auto-order-chart-row" style="display:flex; gap:16px; align-items:stretch; flex-wrap:wrap; margin-top:16px;"></div>'
		).insertBefore(report.$chart);
		report.$chart.appendTo(report.$charts_row);
	}

	report.$chart.css({
		flex: "1 1 520px",
		minWidth: "320px",
	});

	if (report.$totals_chart) {
		report.$totals_chart.css({
			flex: "1 1 320px",
			minWidth: "280px",
		});
	}
}

function render_total_chart() {
	const report = frappe.query_report;
	if (!report || !report.data || !report.data.length) return;

	const total_leads = report.data.reduce((sum, row) => sum + cint(row.no_of_leads || 0), 0);
	const total_orders = report.data.reduce((sum, row) => sum + cint(row.no_of_orders || 0), 0);
	if (!total_leads && !total_orders) return;

	if (!report.$totals_chart) {
		report.$totals_chart = $(
			'<div class="chart-wrapper auto-order-totals-chart"></div>'
		);
		report.$charts_row ? report.$totals_chart.appendTo(report.$charts_row) : report.$totals_chart.insertAfter(report.$chart);
	}

	layout_side_by_side();
	report.$totals_chart.empty().show();
	new frappe.Chart(report.$totals_chart[0], {
		data: {
			labels: ["Leads", "Orders"],
			datasets: [
				{
					name: "Totals",
					values: [total_leads, total_orders]
				}
			]
		},
		type: "donut",
		height: 240,
		colors: ["#4C78A8", "#59A14F"]
	});
}
