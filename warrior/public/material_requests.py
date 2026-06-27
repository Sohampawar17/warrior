import frappe

@frappe.whitelist()
def items_by_supplier(supplier=None):
    """Get items filtered by supplier for Material Request Item field."""
    if not supplier:
        return []
    # items=frappe.get_all("supplier item table",filters={"supplier_id":supplier},pluck="parent")
    items=frappe.get_all("Item Supplier",filters={"supplier":supplier},pluck="parent")
    return items

@frappe.whitelist()
def get_purchase_order_map(source_name):

    mr = frappe.get_doc("Material Request", source_name)

    po = frappe.new_doc("Purchase Order")

    po.naming_series = "PUR-ORD-.YYYY.-"
    po.supplier = mr.custom_supplier
    po.company = mr.company
    po.transaction_date = frappe.utils.nowdate()
    po.schedule_date = mr.schedule_date
    po.set_warehouse = mr.set_warehouse
    po.buying_price_list = mr.buying_price_list
    po.tc_name = "Terms And Condition"

    po.custom_reference_type = "Material Request"
    po.custom_reference_name = mr.name

    for row in mr.items:
        po.append("items", {
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": row.qty,
            "uom": row.uom,
            "rate": row.rate,
            "amount": row.amount,
            "warehouse": row.warehouse,
            "stock_uom":row.stock_uom,
            "conversion_factor":row.conversion_factor,
            "expense_account":row.expense_account
        })

    # ❌ DO NOT INSERT
    # po.insert()

    return po.as_dict()