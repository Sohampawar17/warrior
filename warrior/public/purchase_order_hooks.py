import frappe

@frappe.whitelist()
def get_supplier_transporters(supplier):
    return frappe.get_all(
        "suppliers_transporter",
        filters={
            "parent": supplier,
            "parenttype": "Supplier"
        },
        pluck="transporter"
    )

def validate_transporter(doc,method):
    allowed = get_supplier_transporters(doc.supplier)

    if doc.custom_transporter and doc.custom_transporter not in allowed:
        frappe.throw(f"Invalid transporter for selected supplier ({allowed})")
def fetch_notation(doc, method):
    if not doc.payment_schedule:
        return

    payment_terms = {row.payment_term for row in doc.payment_schedule if row.payment_term}

    if not payment_terms:
        return

    term_map = frappe.get_all(
        "Payment Term",
        filters={"name": ["in", list(payment_terms)]},
        fields=["name", "custom_notation"]
    )

    term_dict = {d.name: d.custom_notation or "" for d in term_map}

    for row in doc.payment_schedule:
        row.db_set("custom_notation", term_dict.get(row.payment_term, ""), update_modified=False)
            
def before_workflow_action(doc, method):
    action = doc.workflow_state
    # frappe.throw(str(action))
    missing = []
    if action == "Inwarded":
        frappe.throw(
            "This Purchase Order is pending for inwarding. "
            "Please click on the <b>Create -> Purchase Invoice (GRN)</b> button "
            "and create the document in Draft state."
        )
    if action == "Pending For Seller Dispatch":
        
        if not doc.order_confirmation_no:
            missing.append("PI No")
        if not doc.order_confirmation_date:
            missing.append("PI Date")
        if not doc.custom_pi_copy:
            missing.append("PI Copy")
    elif action == "Pending For Inward":

        if not doc.custom_transporter_charges:
            missing.append("Transporter Charges")
        if not doc.custom_no_of_box:
            missing.append("Boxes")
        if not doc.custom_transporter:
            missing.append("Transporter")
        if not doc.custom_invoice_number:
            missing.append("Invoice Number")
        if not doc.custom_fulfill_type:
            missing.append("fulfill Type")
        if not doc.custom_transport_slip:
            missing.append("Transporter Slip")
        if not doc.custom_invoice_copy:
            missing.append("Invoice Copy")
    if missing:
        frappe.throw(
            "Please fill mandatory fields: " + ", ".join(missing)
        )
    # pass
    

