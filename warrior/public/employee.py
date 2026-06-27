import frappe


def set_employee_autoname(doc, method=None):
    if not doc.custom_emp_id:
        frappe.throw("Employee ID is required to create Employee")

    doc.name = doc.custom_emp_id.strip()

def ensure_sales_person(doc, method=None):
    """
    Auto-create Sales Person for Employee on create/save.
    Sales Person is linked via Sales Person.employee = Employee.name
    """
    if not doc.name:
        return

    # If already linked, do nothing
    sp = frappe.db.get_value("Sales Person", {"employee": doc.name}, "name")
    if sp:
        # Optional: keep Sales Person name in sync with employee_name
        emp_name = doc.employee_name or doc.name
        current = frappe.db.get_value("Sales Person", sp, "sales_person_name")
        if emp_name and current != emp_name:
            frappe.db.set_value("Sales Person", sp, "sales_person_name", emp_name, update_modified=False)
        return

    # --- Create Sales Person ---
    # NOTE: If your Sales Person tree requires parent_sales_person, set it below.
    emp_name = doc.employee_name or doc.name

    sp_doc = frappe.get_doc({
        "doctype": "Sales Person",
        "sales_person_name": emp_name,
        "employee": doc.name,
        "enabled": 1,
        # Uncomment if required in your setup:
        "parent_sales_person": "Sales Team",
        "is_group": 0
    })
    sp_doc.insert(ignore_permissions=True)
