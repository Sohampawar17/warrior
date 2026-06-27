


# import frappe
# from warrior.common import api_auth, require_post, api_response
# from frappe.utils.password import get_decrypted_password

# @frappe.whitelist(allow_guest=True)
# def login_user(user_id=None, password=None):
#     api_auth()
#     require_post()

#     if not user_id or not password:
#         return api_response(False, "user_id and password are required")

#     # Always start from Guest
#     frappe.set_user("Guest")

#     # ----------------------------------
#     # CHECK USER EXISTENCE
#     # ----------------------------------
#     if not frappe.db.exists("User", user_id):
#         return api_response(False, "User not found")

#     try:
#         # ----------------------------------
#         # AUTHENTICATE (FRAPPE STANDARD)
#         # ----------------------------------
#         frappe.local.login_manager.authenticate(user_id, password)
#         frappe.local.login_manager.post_login()

#         user = frappe.get_doc("User", user_id)
        
#         # ----------------------------------
#         # API KEY / SECRET
#         # ----------------------------------
#         if not user.api_key:
#             user.api_key = frappe.generate_hash(length=15)
#             user.api_secret = frappe.generate_hash(length=15)
#             user.save(ignore_permissions=True)

#         api_secret = get_decrypted_password(
#             "User", user.name, "api_secret", raise_exception=False
#         )

#         return api_response(
#             True,
#             "Login successful",
#             {
#                 "warrior_id" : user.name,
#                 "Warrior_name": user.full_name,
#                 "user_id": user.name,
#                 "username": user.username,
#                 "email": user.email,
#                 "roles": [r.role for r in user.roles],
#                 "session_id": frappe.session.sid,
#                 "key_details": {
#                     "api_key": user.api_key,
#                     "api_secret": api_secret
#                 }
#             }
#         )

#     except frappe.AuthenticationError:
#         return api_response(False, "Invalid password")

#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "Warrior Login Error")
#         return api_response(False, "Login failed, try again")


import frappe
from warrior.common import api_auth, require_post, api_response
from frappe.utils.password import get_decrypted_password

@frappe.whitelist(allow_guest=True)
def login_user(user_id=None, password=None):
    api_auth()
    require_post()

    if not user_id or not password:
        return api_response(False, "user_id and password are required")

    # Always start as Guest
    frappe.set_user("Guest")

    # ----------------------------------
    # RESOLVE USER (EMAIL / USERNAME)
    # ----------------------------------
    resolved_user = None

    # Case 1: email / exact user name
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

    try:
        # ----------------------------------
        # AUTHENTICATE (FRAPPE STANDARD)
        # ----------------------------------
        frappe.local.login_manager.authenticate(resolved_user, password)
        frappe.local.login_manager.post_login()

        user = frappe.get_doc("User", resolved_user)

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

        return api_response(
            True,
            "Login successful",
            {
                "user_id": user.name,
                "warrior_id": user.name,
                "Warrior_name": user.full_name,
                "username": user.username,
                "email": user.email,
                "enabled": user.enabled,
                "user_type": user.user_type,
                "roles": [r.role for r in user.roles],
                "key_details": {
                    "api_key": user.api_key,
                    "api_secret": api_secret
                }
            }
        )

    except frappe.AuthenticationError:
        return api_response(False, "Invalid password")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Warrior Login API Error")
        return api_response(False, "Login failed, try again")
