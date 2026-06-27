// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Employee KM Report"] = {
	"filters": [
{
			"fieldname": "company",
			"label": "Company",
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company")
		},
		
		{
			"fieldname": "from_date",
			"label": "From Date",
			"fieldtype": "Date",
			"default": frappe.datetime.month_start(),
			reqd: 1,

		},
		{
			"fieldname": "to_date",
			"label": "To Date",
			"fieldtype": "Date",
			"default": frappe.datetime.month_end(),
             reqd: 1,
		},
		{
    "fieldname": "employee",
    "label": "Employee",
    "fieldtype": "Link",
    "options": "Employee",
    "ignore_user_permissions": 1
}
	]
};
