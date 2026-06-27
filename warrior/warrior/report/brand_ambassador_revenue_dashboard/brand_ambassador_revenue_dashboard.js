// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Brand Ambassador Revenue Dashboard"] = {
	 tree: true,
    name_field: "employee_name",
    parent_field: "parent_employee",
    initial_depth: 10,
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (data && data.is_group) {
            value = `<strong>${value || ""}</strong>`;
        }
        return value;
    },

    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            reqd: 1
        }
    ]
};
