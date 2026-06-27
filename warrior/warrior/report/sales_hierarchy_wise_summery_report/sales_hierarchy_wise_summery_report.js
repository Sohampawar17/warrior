// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Hierarchy-wise Summery Report"] = {
	tree: true,
	name_field: "row_id",
	parent_field: "parent_row",
	initial_depth: 2,
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.is_group) {
			value = `<strong>${value || ""}</strong>`;
		}
		return value;
	},
	"filters": [
		{
			fieldname: "from_date",
			label: "From Date",
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: "To Date",
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "executive",
			label: "Executive",
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Employee", txt);
			},
		},
		{
			fieldname: "product",
			label: "Product",
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Item", txt);
			},
		},
		{
			fieldname: "state",
			label: "State",
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Territory", txt);
			},
		},
		{
			fieldname: "district",
			label: "District",
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("District", txt);
			},
		},
		{
			fieldname: "tehsil",
			label: "Tehsil",
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Tahshil", txt);
			},
		},
		{
			fieldname: "marketplace",
			label: "Marketplace",
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Marketplace", txt);
			},
		}
	]
};
