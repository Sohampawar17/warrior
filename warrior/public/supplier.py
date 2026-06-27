import frappe

def create_or_update_pricelist(doc, method):

    if not doc.supplier_name:
        return

    price_list_name = f"{doc.name}-{doc.supplier_name}"

    # 🔍 check existing
    existing = frappe.db.get_value(
        "Price List",
        {"price_list_name": price_list_name},
        "name"
    )

    if existing:
        # ✅ ensure supplier has it set
        if doc.default_price_list != existing:
            frappe.db.set_value("Supplier", doc.name, "default_price_list", existing)

        # (optional) update fields if needed
        frappe.db.set_value("Price List", existing, {
            "currency": "INR",
            "buying": 1,
            "enabled": 1
        })

    else:
        # ✅ create new
        pricelist = frappe.new_doc("Price List")
        pricelist.price_list_name = price_list_name
        pricelist.currency = "INR"
        pricelist.buying = 1
        pricelist.selling = 0
        pricelist.enabled = 1

        pricelist.insert(ignore_permissions=True)

        frappe.db.set_value("Supplier", doc.name, "default_price_list", pricelist.name)