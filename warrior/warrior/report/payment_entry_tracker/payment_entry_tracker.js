frappe.query_reports["Payment Entry Tracker"] = {
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
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "custom_purchase_order_id",
			label: __("Purchase Order ID"),
			fieldtype: "Link",
			options: "Purchase Order",
		},
		{
			fieldname: "custom_payment_term",
			label: __("Payment Term"),
			fieldtype: "Data",
		},
		{
			fieldname: "custom_payment_status",
			label: __("Payment Status"),
			fieldtype: "Select",
			options: "\nOverdue\nDue\nIn Credit Period",
		},
		{
			fieldname: "custom_utr_no",
			label: __("UTR No"),
			fieldtype: "Data",
		},
		{
			fieldname: "po_workflow_state",
			label: __("Purchase Order Status"),
			fieldtype: "Data",
		},
		{
			fieldname: "name",
			label: __("Payment Entry ID"),
			fieldtype: "Link",
			options: "Payment Entry",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const formatted = default_formatter(value, row, column, data);
		const fieldname = column.fieldname;
		const status_value = (value || "").toString().trim();

		const color_map = {
			Overdue: "red",
			Due: "orange",
			"Approved By Manager": "blue",
			"In Credit Period": "green",
			Credit: "blue",
			Completed: "green",
			Closed: "gray",
			Open: "orange",
			Pending: "orange",
			Cancelled: "red",
			Inwarded: "blue",
		};

		if (!["custom_payment_status", "payment_status_from", "po_workflow_state", "status"].includes(fieldname)) {
			return formatted;
		}

		if (!status_value) {
			return formatted;
		}

		const color = color_map[status_value] || "gray";
		return `<span class="indicator ${color}">${frappe.utils.escape_html(status_value)}</span>`;
	},
};
