import frappe
from warrior.common import api_auth, require_post, api_response
from frappe.utils.password import get_decrypted_password

@frappe.whitelist(allow_guest=True)
def get_user_details(user_id=None):
    api_auth()
    require_post()

    # frappe.set_user("Administrator")
    frappe.set_user("Guest")
    frappe.local.login_manager = None
    
    if not user_id:
        return api_response(False, "user_id is required")


    # ----------------------------------
    # CHECK USER EXISTENCE
    # ----------------------------------
    if not frappe.db.exists("User", user_id):
        return api_response(False, "User not found")

    user = frappe.get_doc("User", user_id)

    # ----------------------------------
    # API KEY / SECRET
    # ----------------------------------
    if not user.api_key:
        user.api_key = frappe.generate_hash(length=15)
        user.api_secret = frappe.generate_hash(length=15)
        user.save(ignore_permissions=True)

    api_secret = get_decrypted_password(
        "User", user.name, "api_secret", raise_exception=False
    )
    
    # ----------------------------------
    # FETCH DEFAULT ROLE FROM EMPLOYEE
    # ----------------------------------
    default_role = frappe.get_value(
        "Employee",
        {"user_id": user.name},
        "custom_default_role"
    )

    # ----------------------------------
    # RETURN USER DETAILS
    # ----------------------------------
    return api_response(
        True,
        "User details fetched successfully",
        {
            "user_id": user.name,
            "full_name": user.full_name,
            "username": user.username,
            "email": user.email,
            "enabled": user.enabled,
            "user_type": user.user_type,
            "default_role": default_role,  
            "roles": [r.role for r in user.roles],
            "key_details": {
                "api_key": user.api_key,
                "api_secret": api_secret
            }
        }
    )


import frappe
from warrior.common import api_auth, require_post, api_response

@frappe.whitelist(allow_guest=True)
def get_user_roles(user_id=None):
    api_auth()
    require_post()

    # Always work as Guest
    frappe.set_user("Guest")

    if not user_id:
        return api_response(False, "user_id is required")

    # ----------------------------------
    # RESOLVE USER (email OR username)
    # ----------------------------------
    resolved_user = None

    # Case 1: email / name
    if frappe.db.exists("User", user_id):
        resolved_user = user_id
    else:
        # Case 2: username
        user = frappe.get_all(
            "User",
            filters={"username": user_id},
            pluck="name",
            limit=1
        )
        if user:
            resolved_user = user[0]

    if not resolved_user:
        return api_response(False, "User not found")

    # ----------------------------------
    # FETCH ROLES
    # ----------------------------------
    user_doc = frappe.get_doc("User", resolved_user)

    roles = [r.role for r in user_doc.roles] if user_doc.roles else []

    return api_response(
        True,
        "User roles fetched successfully",
        {
            "user_id": user_doc.name,
            "username": user_doc.username,
            "email": user_doc.email,
            "roles": roles
        }
    )
