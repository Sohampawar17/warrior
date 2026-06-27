// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Campaign-wise Revenue"] = {
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
		},
		{
			"fieldname": "campaign",
			"label": "Campaign",
			"fieldtype": "Link",
			"options": "Campaign"
		}
	],
	after_datatable_render: function () {
		render_total_chart();
	}
};

function render_total_chart() {
	const report = frappe.query_report;
	if (!report || !report.data || !report.data.length) return;

	const total_leads = report.data.reduce((sum, row) => sum + cint(row.no_of_leads || 0), 0);
	const total_orders = report.data.reduce((sum, row) => sum + cint(row.no_of_orders || 0), 0);
	if (!total_leads && !total_orders) return;

	if (!report.$totals_chart) {
		report.$totals_chart = $(
			'<div class="chart-wrapper campaign-wise-totals-chart" style="margin-top: 16px;"></div>'
		).insertAfter(report.$chart);
	}

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
