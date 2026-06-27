// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Purchase Order History"] = {
  filters: [
	  {
      fieldname: "company",
      label: "Company",
      fieldtype: "Link",
      options: "Company",
      default: frappe.defaults.get_user_default("Company"),
    },
    {
      fieldname: "from_date",
      label: "From Date",
      fieldtype: "Date",
      default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
      reqd: 1
    },
    {
      fieldname: "to_date",
      label: "To Date",
      fieldtype: "Date",
      default: frappe.datetime.get_today(),
      reqd: 1
    },
  
    {
      fieldname: "supplier",
      label: "Supplier",
      fieldtype: "Link",
      options: "Supplier"
    },
    {
      fieldname: "purchase_order",
      label: "Purchase Order",
      fieldtype: "Link",
      options: "Purchase Order"
    },
    {
      fieldname: "status",
      label: "Status",
      fieldtype: "Select",
      options: "\nDraft\nTo Receive and Bill\nTo Bill\nTo Receive\nCompleted\nCancelled\nClosed\nOn Hold"
    },
    {
      fieldname: "item_code",
      label: "Item",
      fieldtype: "Link",
      options: "Item"
    },
  ]

};
