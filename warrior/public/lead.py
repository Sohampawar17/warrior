import frappe


def campaign_registration(doc, method):
    try:
        if not doc.mobile_no and not doc.campaign_name:
            return

        registration_doctype = (
            "Delear Registration" if doc.type == "Dealer"
            else "Farmer Registration"
        )

        # 🔥 Only mobile number check
        exists = frappe.db.exists(
            registration_doctype,
            {"mobile_number": doc.mobile_no}
        )

        if not exists:
            registration_doc = frappe.get_doc({
                "doctype": registration_doctype,
                "from_document": doc.name,
                "mobile_number": doc.mobile_no,
                "first_name": doc.lead_name if doc.type == "Farmer" else None,
                "shop_name": doc.lead_name if doc.type == "Dealer" else None,
                "is_completed": 0
            })

            registration_doc.insert(ignore_permissions=True)
            
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Campaign Registration Error"
        )