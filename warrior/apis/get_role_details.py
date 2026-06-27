import frappe
from warrior.common import api_auth, require_post, api_response

@frappe.whitelist(allow_guest=True)
def get_role_doctypes(role=None):
    api_auth()
    require_post()

    frappe.set_user("Guest")
    frappe.local.login_manager = None
    frappe.set_user("Administrator")

    # -------------------------------
    # BASIC VALIDATION
    # -------------------------------
    if not role:
        return api_response(False, "role is required")

    # -------------------------------
    # FETCH ROLE ACCESS DOC
    # -------------------------------
    role_access_name = frappe.get_value(
        "Role Access",
        {"role": role},
        "name"
    )

    if not role_access_name:
        return api_response(False, "No Role Access configuration found for this role")

    role_access_doc = frappe.get_doc("Role Access", role_access_name)

    # -------------------------------
    # EXTRACT DOCTYPE NAMES
    # -------------------------------
    doctypes = []

    if role_access_doc.doctype_access:
        for row in role_access_doc.doctype_access:
            if row.doctype_name:
                doctypes.append(row.doctype_name)

    # -------------------------------
    # RESPONSE
    # -------------------------------
    return api_response(
        True,
        "Role doctype access fetched successfully",
        {
            "role": role,
            "doctypes": doctypes
        }
    )
