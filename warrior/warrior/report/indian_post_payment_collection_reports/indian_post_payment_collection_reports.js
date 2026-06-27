frappe.query_reports["Indian Post Payment Collection Reports"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "order_id",
			label: __("Order ID"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{
			fieldname: "tracking_id",
			label: __("Tracking ID"),
			fieldtype: "Data",
		},
		{
			fieldname: "invoice_id",
			label: __("Invoice ID"),
			fieldtype: "Link",
			options: "Sales Invoice",
		},
	],
};
