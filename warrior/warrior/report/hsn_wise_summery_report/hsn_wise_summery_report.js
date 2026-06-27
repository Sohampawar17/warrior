frappe.query_reports["HSN-wise Summery Report"] = {
  filters: [
	 {
      fieldname: "company",
      label: "Company",
      fieldtype: "Link",
      options: "Company"
    },
    {
      fieldname: "from_date",
      label: "From Date",
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.month_start()
    },
    {
      fieldname: "to_date",
      label: "To Date",
      fieldtype: "Date",
      reqd: 1,
      default: frappe.datetime.month_end()
    },
    {
      fieldname: "customer_group",
      label: "User Type (Customer Group)",
      fieldtype: "Link",
      options: "Customer Group"
    },
   
    {
      fieldname: "invoice",
      label: "Invoice ID",
      fieldtype: "Link",
      options: "Sales Invoice"
    },
    {
      fieldname: "item_code",
      label: "Product ID (Item Code)",
      fieldtype: "Link",
      options: "Item"
    },
    {
      fieldname: "gst_hsn_code",
      label: "HSN Code",
      fieldtype: "Data"
    }
  ]
};