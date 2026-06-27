// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Tally Credit Note Export"] = {
// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt
  filters: [
    {
      fieldname: "from_date",
      label: __("From Date"),
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.month_start(frappe.datetime.get_today())
    },
    {
      fieldname: "to_date",
      label: __("To Date"),
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.get_today()
    },
    {
    fieldname: "invoice_no",
    label: __("Invoice No"),
    fieldtype: "Link",
    options: "Sales Invoice",
    get_query: function() {
        return {
            filters: {
                is_return: 1,
                docstatus: 1
            }
        };
    }
},
    {
      fieldname: "customer",
      label: __("Customer"),
      fieldtype: "Link",
      options: "Customer"
    },
    {
  fieldname: "location",
  label: __("Location"),
  fieldtype: "Link",
  options: "Warehouse"
}
  ]
};
