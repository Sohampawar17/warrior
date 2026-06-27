// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.query_reports["Item Purchase and Selling Rate Report"] = {
	filters: [
        {
            fieldname: "item_code",
            label: "Item",
            fieldtype: "Link",
            options: "Item"
        },
        {
            fieldname: "brand",
            label: "Brand",
            fieldtype: "Link",
            options: "Brand"
        },
          {
            fieldname: "item_status",
            label: "Item Status",
            fieldtype: "Select",
            options: "\nEnabled\nDisabled\nAll",
            default: "Enabled"
        }
    
    ]
};
