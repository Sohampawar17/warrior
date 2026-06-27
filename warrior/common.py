import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.utils import cstr,pretty_date
import wrapt
import re
import json
from frappe.core.doctype.file.file import extract_images_from_html
from frappe.desk.form.document_follow import follow_document
# ------------------------------
# COMMON API AUTH
# ------------------------------
def api_auth():
    """Validate API KEY + SECRET (simple & strong)."""
    cfg = frappe.get_site_config()

    key = frappe.get_request_header("X-API-KEY")
    secret = frappe.get_request_header("X-API-SECRET")

    if not key or not secret:
        frappe.throw("Missing authentication headers")

    if key != cfg.get("shoption_api_key") or secret != cfg.get("shoption_api_secret"):
        frappe.throw("Unauthorized API Access")

    return True


# ------------------------------
# FORCE POST (optional but recommended)
# ------------------------------
def require_post():
    if frappe.request.method != "POST":
        frappe.throw("Method Not Allowed — Only POST allowed")


# ------------------------------
# SIMPLE FIELD VALIDATION (optional use)
# ------------------------------
def allowed_fields(input_data: dict, allowed_list: list):
    for key in input_data.keys():
        if key not in allowed_list:
            frappe.throw(f"Invalid field: {key}")

def validate_method(methods):
    @wrapt.decorator
    def wrapper(wrapped, instance, args, kwargs):
        if frappe.local.request.method not in methods:
            return gen_response(500, "Invalid Request Method")
        return wrapped(*args, **kwargs)

    return wrapper
# ------------------------------
# CLEAN UNIFIED RESPONSE FORMAT
# ------------------------------
def api_response(status=True, message="", data=None):
    return {
        "status": status,
        "message": message,
        "data": data or []
    }

# pagenation utility
def paginate(doctype, filters=None, fields=None, page=1, page_size=50, order_by="creation desc"):
    page = int(page)
    page_size = int(page_size)

    start = (page - 1) * page_size

    data = frappe.get_list(
        doctype,
        filters=filters,
        fields=fields,
        limit_start=start,
        limit_page_length=page_size,
        order_by=order_by
    )

    total = frappe.db.count(doctype, filters)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "data": data
    }

def gen_response(status, message, data=[]):
    frappe.response["http_status_code"] = status
    if status == 500:
        frappe.response["message"] = BeautifulSoup(str(message)).get_text()
    else:
        frappe.response["message"] = message
    frappe.response["data"] = data

def clean_html(raw_html):
    """Remove HTML tags for cleaner error messages."""
    return re.sub(r"<.*?>", "", raw_html)

def exception_handel(e):
    frappe.log_error(title="Mobile App Error", message=frappe.get_traceback())
    message = cstr(e)
    # Try to extract frappe's _server_messages if available
    if hasattr(e, "args") and e.args:
        try:
            data = e.args[0]
            if isinstance(data, dict) and "_server_messages" in data:
                server_messages = json.loads(data["_server_messages"])
                if server_messages:
                    # Pick the first message and clean HTML
                    message = clean_html(server_messages[0])
        except Exception:
            pass

    if hasattr(e, "http_status_code"):
        return gen_response(e.http_status_code, message)
    else:
        return gen_response(500, message)


def generate_key(user):
    user_details = frappe.get_doc("User", user)
    api_secret = api_key = ""
    if not user_details.api_key and not user_details.api_secret:
        api_secret = frappe.generate_hash(length=15)
        # if api key is not set generate api key
        api_key = frappe.generate_hash(length=15)
        user_details.api_key = api_key
        user_details.api_secret = api_secret
        user_details.save(ignore_permissions=True)
    else:
        api_secret = user_details.get_password("api_secret")
        api_key = user_details.get("api_key")
    return {"api_secret": api_secret, "api_key": api_key}


def ess_validate(methods):
   
    def wrapper(wrapped, instance, args, kwargs):
        if not frappe.local.request.method in methods:
            return gen_response(500, "Invalid Request Method")
        return wrapped(*args, **kwargs)

    return wrapper


def get_employee_by_user(user, fields=["name"]):
    if isinstance(fields, str):
        fields = [fields]
    emp_data = frappe.db.get_value(
        "Employee",
        {"user_id": user},
        fields,
        as_dict=1,
    )
    return emp_data

def role_profile(user):
    try:
            role = frappe.db.get_value("User",frappe.session.user,"role_profile_name")
            return role
    except Exception as e:
        frappe.log_error(f"Error in role_profile function: {e}")
        return None  # Return None or a default value to indicate the


def validate_employee_data(employee_data):
    if not employee_data.get("company"):
        return api_response(False, "Company not set in employee doctype. Contact HR manager for set company")


def get_ess_settings():
    return frappe.get_doc(
        "Employee Self Service Settings", "Employee Self Service Settings"
    )


def get_global_defaults():
    return frappe.get_doc("Global Defaults", "Global Defaults")

@frappe.whitelist(allow_guest=True)
def download_pdf(doctype, name, format=None, doc=None, no_letterhead=0, key=None):
    from frappe.utils.pdf import get_pdf

    # allow public access only when a valid share key is provided
    if key:
        frappe.local.form_dict.key = key

    html = frappe.get_print(doctype, name, format, doc=doc, no_letterhead=no_letterhead)
    frappe.local.response.filename = "{name}.pdf".format(
        name=name.replace(" ", "-").replace("/", "-")
    )
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "download"

@frappe.whitelist(allow_guest=True)
def get_print_url(doctype, name, format=None, no_letterhead=0, key=None):
    from frappe.utils import get_url, quote
    
    return (
        f"{get_url()}/printview?doctype={quote(doctype)}"
        f"&name={quote(name)}&format={quote(format or 'Standard')}"
        f"&no_letterhead={int(no_letterhead)}&key={quote(key or '')}"
    )

def remove_default_fields(data):
    # Example usage:
    # remove_default_fields(
    #     json.loads(
    #         frappe.get_doc("Address", "name").as_json()
    #     )
    # )
    for row in [
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "doctype",
        "links",
    ]:
        if data.get(row):
            del data[row]
    return data


def prepare_json_data(key_list, data):
    return_data = {}
    for key in data:
        if key in key_list:
            return_data[key] = data.get(key)
    return return_data

import frappe
from frappe.utils import get_url

def get_attachments(document_type, document):

    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": document_type,
            "attached_to_name": document
        },
        fields=["file_url", "file_name"],
    )

    base_url = get_url()

    for f in files:
        if f.file_url:
            f.file_url = get_url(f.file_url)

    return files

@frappe.whitelist()
def add_comment(reference_doctype=None, reference_name=None, content=None):
    try:
        comment_by = frappe.db.get_value(
            "User", frappe.session.user, "full_name", as_dict=1
        )
        add_ess_comment(
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            content=content,
            comment_email=frappe.session.user,
            comment_by=comment_by.get("full_name"),
        )
        return "Comment added successfully"

    except Exception as e:
        return "Error adding comment: " + str(e)


@frappe.whitelist()
def get_comments(reference_doctype=None, reference_name=None):
    """
    reference_doctype: doctype
    reference_name: docname
    """
    try:
        filters = [
            ["Comment", "reference_doctype", "=", f"{reference_doctype}"],
            ["Comment", "reference_name", "=", f"{reference_name}"],
            ["Comment", "comment_type", "=", "Comment"],
        ]
        comments = frappe.get_all(
            "Comment",
            filters=filters,
            fields=[
                "content as comment",
                "comment_by",
                "creation",
                "comment_email",
            ],
        )

        for comment in comments:
            user_image = frappe.get_value(
                "User", comment.comment_email, "user_image", cache=True
            )
            comment["user_image"] = get_url(user_image) if user_image else None
            comment["commented"] = pretty_date(comment["creation"])
            comment["creation"] = comment["creation"].strftime("%I:%M %p")

        return comments

    except Exception as e:
        return "Error fetching comments: " + str(e)

def add_ess_comment(
    reference_doctype, reference_name, content, comment_email, comment_by
):
    """allow any logged user to post a comment"""
    doc = frappe.get_doc(
        doctype="Comment",
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        comment_email=comment_email,
        comment_type="Comment",
        comment_by=comment_by,
    )
    reference_doc = frappe.get_doc(reference_doctype, reference_name)
    doc.content = extract_images_from_html(reference_doc, content, is_private=True)
    doc.insert(ignore_permissions=True)

    follow_document(doc.reference_doctype, doc.reference_name, frappe.session.user)
    return doc.as_dict()