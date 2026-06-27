frappe.query_reports["Visit Report"] = {
  filters: [
    { fieldname: "from_date", label: "From Date", fieldtype: "Date", default: frappe.datetime.month_start() },
    { fieldname: "to_date", label: "To Date", fieldtype: "Date", default: frappe.datetime.month_end() },

    { fieldname: "search", label: "Search (Customer / Mobile / Order)", fieldtype: "Data" },

    { fieldname: "marketplace", label: "Marketplace", fieldtype: "Data" },

    {
      fieldname: "profile_status",
      label: "Profile Status",
      fieldtype: "Select",
      options: "\nRegistered\nUnregistered"
    },

    { fieldname: "owner", label: "Owner", fieldtype: "Link", options: "User" }
  ]
};