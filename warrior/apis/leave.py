import frappe
from frappe.utils import get_datetime, nowdate,flt,cint
from frappe.utils.file_manager import save_file
from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on
from warrior.common import api_auth, api_response,get_employee_by_user, validate_employee_data
from frappe.handler import upload_file



def attach_file(fieldname, doctype, docname):
    uploaded_file = frappe.request.files.get("image")
    if not uploaded_file:
        return None

    if not frappe.has_permission(doctype, "write", docname):
        frappe.throw("Not permitted")

    file_doc = save_file(
        fname=uploaded_file.filename,
        content=uploaded_file.stream.read(),
        dt=doctype,
        dn=docname,
        df=fieldname,
        is_private=0
    )

    return file_doc.file_url

@frappe.whitelist()
def update_leave_application(**kwargs):
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company"])
        if not len(emp_data) >= 1:
            return api_response(False, "Employee does not exists!")
        validate_employee_data(emp_data)

        leave_id = kwargs.get("name")
        if not leave_id:
            return api_response(False, "Leave ID is required!")

        if not frappe.db.exists("Leave Application", kwargs.get("name")):
            return api_response(False, "Leave application does not exists!")

        leave_application_doc = frappe.get_doc("Leave Application", leave_id)
        leave_application_doc.update(kwargs)
        km_photo = attach_file(
            fieldname="custom_image",
            doctype="Leave Application",
            docname=leave_application_doc.name
        )
        if km_photo:
            leave_application_doc.custom_image = km_photo
        leave_application_doc.save()
        return api_response(True, "Leave application successfully updated!")
    except Exception as e:
        return api_response(False, str(e))


@frappe.whitelist()
def make_leave_application(**kwargs):
    try:
        from hrms.hr.doctype.leave_application.leave_application import (
            get_leave_approver,
        )

        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return api_response(False, "Employee does not exists")
        validate_employee_data(emp_data)
        leave_application_doc = frappe.get_doc(
            dict(
                doctype="Leave Application",
                employee=emp_data.get("name"),
                company=emp_data.company,
                leave_approver=get_leave_approver(emp_data.name),
            )
        )
        leave_application_doc.update(kwargs)
        res = leave_application_doc.insert()

        km_photo = attach_file(
            fieldname="custom_image",
            doctype="Leave Application",
            docname=res.name
        )
        if km_photo:
            res.custom_image = km_photo

        res.save(ignore_permissions=True)
        frappe.db.commit()

        return api_response(True, "Leave Application Successfully Added", res)
    except Exception as e:
        return api_response(False, str(e))


@frappe.whitelist()
def get_leave_type():
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return api_response(False, "Employee does not exists!")
        leave_types = frappe.get_all(
            "Leave Type", filters={}, pluck="name"
        )
       
        return api_response(True, "Leave Type Get Successfully", leave_types)
    except Exception as e:
        return api_response(False, str(e))


@frappe.whitelist()
def get_leave_application(name):
    """
    Get Leave Application which is already applied. Get Leave Balance Report
    """
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        validate_employee_data(emp_data)

        if not frappe.db.exists(
            "Leave Application", {"name": name, "employee": emp_data.get("name")}
        ):
            return api_response(False, "Leave application does not exists!")

        leave_application_fields = [
            "name",
            "leave_type",
            "total_leave_days",
            "description",
            "status",
            "half_day",
            "from_date",
            "to_date",
            "posting_date",
            "docstatus",
            "half_day_date",
        ]

        leave_application = frappe.db.get_value(
            "Leave Application", name, leave_application_fields, as_dict=True
        )

        return api_response(True, "Leave data getting successfully", leave_application)
    except Exception as e:
        return api_response(False, str(e))


@frappe.whitelist()
def delete_leave_application(name):
    try:
        emp = get_employee_by_user(frappe.session.user)
        validate_employee_data(emp)

        if not frappe.db.exists(
            "Leave Application",
            {"name": name, "employee": emp.get("name")}
        ):
            return api_response(False, "Leave application not found")

        doc = frappe.get_doc("Leave Application", name)

        if doc.docstatus == 1:
            return api_response(False, "Submitted leave cannot be deleted")

        doc.delete()

        return api_response(True, "Leave deleted successfully")

    except Exception as e:
        return api_response(False, str(e))
    
@frappe.whitelist()
def get_leave_application_list(page=1, page_size=20):
    try:
        emp_data = get_employee_by_user(frappe.session.user)
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        leave_application_fields = [
            "name",
            "leave_type",
            "DATE_FORMAT(from_date, '%d-%m-%Y') as from_date",
            "DATE_FORMAT(to_date, '%d-%m-%Y') as to_date",
            "description",
            "status",
            "docstatus",
            "half_day",
            "half_day_date",
            "posting_date",
        ]
        upcoming_leaves = frappe.get_list(
            "Leave Application",
            filters={"employee": emp_data.get("name")},
            fields=leave_application_fields,
            limit_start=start,
            limit_page_length=page_size,
        )
        total_records = frappe.db.count("Leave Application", filters={"employee": emp_data.get("name")})
        total_pages = (total_records + page_size - 1) // page_size
        return api_response(True, "leave data getting successfully", {
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": upcoming_leaves
        })
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_leave_application_list")
        return api_response(False, str(e))