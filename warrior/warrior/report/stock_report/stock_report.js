frappe.query_reports["Stock Report"] = {
    filters: [

        {
            fieldname: "warehouse",
            label: "Warehouse",
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "item",
            label: "Item",
            fieldtype: "Link",
            options: "Item"
        },
        {
            fieldname: "brand",
            label: "Brand",
            fieldtype: "Link",
            options: "Brand"
        }
    ]
};