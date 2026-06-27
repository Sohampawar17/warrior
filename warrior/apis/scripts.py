import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote,getdate,flt,cint,fmt_money
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url,api_auth,require_post
import json


@frappe.whitelist()
def get_employees_for_full_and_final(doctype, txt, searchfield, start, page_len, filters):
    """
    Return employees:
    - Who have Employee Separation
    - Who DO NOT have Full and Final Statement submitted
    """

    return frappe.db.sql("""
        SELECT
            emp.name,
            emp.employee_name
        FROM `tabEmployee` emp
        INNER JOIN `tabEmployee Separation` sep
            ON sep.employee = emp.name
        LEFT JOIN `tabFull and Final Statement` fnf
            ON fnf.employee = emp.name
            AND fnf.docstatus = 1
        WHERE
            fnf.name IS NULL
            AND (emp.name LIKE %(txt)s OR emp.employee_name LIKE %(txt)s)
        ORDER BY emp.employee_name
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })


@frappe.whitelist(allow_guest=True)
def add_product_enquires():
    api_auth()
    require_post()
    frappe.set_user("Administrator")

    try:
        data = json.loads(frappe.request.data or "{}")

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return api_response(False, "Invalid payload. Expected object or list.")

        created_docs = []

        for item in data:
            doc = frappe.get_doc({
                "doctype": "Partnership Enquiries",
                "business_type": item.get("businessType"),
                "enterprise_name": item.get("enterpriseName"),
                "gst_number": item.get("gstNumber"),
                "company_website": item.get("companyWebsite"),
                "contact_person_role": item.get("contactPersonRole"),
                "full_name": item.get("fullName"),
                "mobile_number": item.get("mobileNumber"),
                "email_address": item.get("emailAddress"),
            })
            doc.insert(ignore_permissions=True)
            created_docs.append(doc.name)

        frappe.db.commit()

        return api_response(
            True,
            "Product Enquiry added successfully",
            {"names": created_docs}
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "add_product_enquires API Error")
        return api_response(False, f"Error adding Product Enquiry: {str(e)}")