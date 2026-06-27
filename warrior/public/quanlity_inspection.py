import frappe
from frappe.utils import flt

def set_qty_in_invoice(doc, method):
    # Validate reference
    if doc.reference_type != "Purchase Invoice" or not doc.reference_name:
        return

    # Validate quantities entered
    ok_qty = flt(doc.custom_ok_qty)
    faulty_qty = flt(doc.custom_faulty_qty)

    if ok_qty <= 0 and faulty_qty < 0:
        frappe.throw("Please enter OK Qty or Rejected Qty.")

    # Fetch PI item row
    pi_item = frappe.db.get_value(
        "Purchase Invoice Item",
        {
            "parent": doc.reference_name,
            "item_code": doc.item_code,
        },
        ["name", "qty"],
        as_dict=True,
    )

    if not pi_item:
        frappe.throw(
            f"Item {doc.item_code} not found in Purchase Invoice {doc.reference_name}."
        )

    # Fetch PI docstatus
    pi_docstatus = frappe.db.get_value(
        "Purchase Invoice",
        doc.reference_name,
        "docstatus",
    )

    if pi_docstatus == 2:
        frappe.throw("Cannot update quantities for a cancelled Purchase Invoice.")

    # Quantity validation
    total_qty = ok_qty + faulty_qty
    if total_qty <= 0:
        frappe.throw("Total quantity must be greater than zero.")

    # Optional: Prevent exceeding original qty
    if pi_item.qty and total_qty > flt(pi_item.qty):
        frappe.throw(
            f"OK Qty + Rejected Qty ({total_qty}) "
            f"cannot be greater than Invoice Qty ({pi_item.qty})."
        )

    # Update values
    frappe.db.set_value("Purchase Invoice", doc.reference_name, "custom_quality_inspection_by", doc.inspected_by)
    frappe.db.set_value("Purchase Invoice", doc.reference_name, "custom_quality_inspection_datetime", doc.creation)
    frappe.db.set_value("Purchase Invoice", doc.reference_name, "workflow_state", "Approved By Manager")
    frappe.db.set_value(
        "Purchase Invoice Item",
        pi_item.name,
        {
            "qty": ok_qty,
            "rejected_qty": faulty_qty,
        },
    )
