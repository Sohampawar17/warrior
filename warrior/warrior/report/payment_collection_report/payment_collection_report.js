// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Payment Collection Report"] = {
    filters: [
        {
            fieldname: "status",
            label: "Status",
            fieldtype: "Select",
            options: ["", "Success", "Pending", "Failed"]
        },
        {
            fieldname: "order_id",
            label: __("Order ID"),
            fieldtype: "Data",
            width: 140
        },
        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
            width: 180
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            width: 120
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            width: 120
        }
    ]
};
