import json
import frappe
from frappe.model.workflow import get_transitions, get_workflow_name,apply_workflow
from frappe.utils import fmt_money,flt,get_url,cint

from warrior.common import (api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_attachments)

def get_action(doc, doc_data=None):
    from frappe.model.workflow import get_transitions

    if not frappe.db.exists(
        "Workflow", dict(document_type=doc.get("doctype"), is_active=1)
    ):
        if doc_data:
            doc_data["workflow_state"] = doc.get("status")
        return []
    try:
        transitions = get_transitions(doc)
    except Exception:
        return []
    actions = []
    for row in transitions:
        actions.append(row.get("action"))
    return actions


def check_workflow_exists(doctype):
    doc_workflow = frappe.get_all(
        "Workflow",
        filters={"document_type": doctype, "is_active": 1},
        fields=["workflow_state_field"],
    )
    if doc_workflow:
        return doc_workflow[0].workflow_state_field
    else:
        return False


@frappe.whitelist()
@validate_method(methods=["POST"])
def update_workflow_state(reference_doctype, reference_name, action):
    try:
        from frappe.model.workflow import apply_workflow

        doc = frappe.get_doc(reference_doctype, reference_name)
        apply_workflow(doc, action)
        return api_response(True, "Workflow State Updated Successfully")
    except frappe.PermissionError:
        return api_response(False, f"Not permitted for update {reference_doctype}")
    except Exception as e:
        frappe.db.rollback()
        return api_response(False, f"exception {str(e)}")

@frappe.whitelist()
def get_workflow(doctype: str) -> dict:
    workflow = get_workflow_name(doctype)
    if not workflow:
        return frappe._dict()
    return frappe.get_doc("Workflow", workflow)


@frappe.whitelist()
@validate_method(methods=["GET"])
def get_team_leave_application(page=1, page_size=20):

    try:

        workflow = check_workflow_exists("Leave Application")

        emp_data = get_employee_by_user(
            frappe.session.user
        )

        # -------------------------
        # PAGINATION
        # -------------------------

        page = cint(page or 1)
        page_size = cint(page_size or 20)

        if page < 1:
            page = 1

        if page_size < 1:
            page_size = 20

        start = (page - 1) * page_size

        # -------------------------
        # FILTERS
        # -------------------------

        filters = [
            ["employee", "!=", emp_data.name],
            ["leave_approver", "=", frappe.session.user],
        ]

        # =====================================================
        # WITHOUT WORKFLOW
        # =====================================================

        if not workflow:

            filters.extend([
                ["docstatus", "=", 0],
                ["status", "=", "Open"],
            ])

            # -------------------------
            # TOTAL COUNT
            # -------------------------

            total_records = frappe.db.count(
                "Leave Application",
                filters=filters
            )

            total_pages = (
                (total_records + page_size - 1) // page_size
                if total_records else 0
            )

            # -------------------------
            # FETCH DATA
            # -------------------------

            leave_applications = frappe.get_list(
                "Leave Application",
                filters=filters,
                fields=[
                    "employee_name",
                    "name",
                    "posting_date",
                    "from_date",
                    "to_date",
                    "leave_type",
                    "employee",
                    "total_leave_days",
                    "description",
                    "status",
                    "'0' as workflow_active",
                ],
                order_by="posting_date desc",
                start=start,
                page_length=page_size,
            )

            return api_response(
                True,
                "Leave Application Get Successfully",
                {
                    "total": total_records,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "data": leave_applications
                }
            )

        # =====================================================
        # WITH WORKFLOW
        # =====================================================

        filters.extend([
            ["docstatus", "!=", 2],
            ["workflow_state", "is", "set"]
        ])

        leave_applications = frappe.get_list(
            "Leave Application",
            filters=filters,
            fields=[
                "employee_name",
                "name",
                "posting_date",
                "from_date",
                "to_date",
                "leave_type",
                "employee",
                "total_leave_days",
                "description",
                "workflow_state as status",
                "'1' as workflow_active",
            ],
            order_by="posting_date desc",
        )

        # -------------------------
        # FILTER ONLY ACTIONABLE
        # -------------------------

        actual_leave_applications = []

        for doc in leave_applications:

            if doc.get("status"):

                transitions = get_transitions(
                    frappe.get_doc(
                        "Leave Application",
                        doc["name"]
                    )
                )

                if transitions:
                    actual_leave_applications.append(doc)

        # -------------------------
        # TOTAL COUNT
        # -------------------------

        total_records = len(actual_leave_applications)

        total_pages = (
            (total_records + page_size - 1) // page_size
            if total_records else 0
        )

        # -------------------------
        # PAGINATED DATA
        # -------------------------

        paginated_data = actual_leave_applications[
            start:start + page_size
        ]

        # -------------------------
        # RESPONSE
        # -------------------------

        return api_response(
            True,
            "Team Leave Application Get Successfully",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": paginated_data
            }
        )

    except Exception as e:

        return api_response(
            False,
            f"exception {str(e)}"
        )
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_leave_application_details(leave_id):
    try:
        if not frappe.has_permission("Leave Application", "read"):
            raise frappe.PermissionError
        is_workflow = check_workflow_exists("Leave Application")
        leave_doc = json.loads(frappe.get_doc("Leave Application", leave_id).as_json())
        if is_workflow:
            leave_doc["status"] = leave_doc.get("workflow_state")
            leave_doc["workflow_active"] = "1"
        else:
            leave_doc["workflow_active"] = "0"
        leave_doc["action"] = get_action(leave_doc)
        leave_doc["custom_image"]=get_url(leave_doc["custom_image"]) if leave_doc.get("custom_image") else None
        
        return api_response(True, "Leave Application detail get successfully.", leave_doc)
    except frappe.PermissionError:
        return api_response(False, "Not permitted for Leave Application")
    except Exception as e:
        return api_response(False, f"exception {str(e)}")




@frappe.whitelist()
@validate_method(methods=["GET"])
def get_team_expenses(page=1, page_size=20):

    try:

        workflow = check_workflow_exists("Expense Claim")

        emp_data = get_employee_by_user(
            frappe.session.user
        )

        global_defaults = get_global_defaults()

        # -------------------------
        # PAGINATION
        # -------------------------

        page = cint(page or 1)
        page_size = cint(page_size or 20)

        if page < 1:
            page = 1

        if page_size < 1:
            page_size = 20

        start = (page - 1) * page_size

        # -------------------------
        # FILTERS
        # -------------------------

        filters = [
            ["employee", "!=", emp_data.name],
            ["expense_approver", "=", frappe.session.user],
        ]

        # =====================================================
        # WITHOUT WORKFLOW
        # =====================================================

        if not workflow:

            filters.extend([
                ["docstatus", "=", 0],
                ["status", "=", "Draft"],
                
            ])

            fields = [
                "`tabExpense Claim`.name",
                "`tabExpense Claim`.employee",
                "`tabExpense Claim`.employee_name",
                "`tabExpense Claim`.approval_status",
                "`tabExpense Claim`.expense_approver",
                "`tabExpense Claim`.total_claimed_amount",
                "`tabExpense Claim`.posting_date",
                "`tabExpense Claim`.company",
                "`tabExpense Claim Detail`.expense_type",
                "`tabExpense Claim Detail`.name as expense_detail_name",
                "count(`tabExpense Claim Detail`.expense_type) as total_expenses",
            ]

            # -------------------------
            # TOTAL COUNT
            # -------------------------

            total_records = frappe.db.count(
                "Expense Claim",
                filters=filters
            )

            total_pages = (
                (total_records + page_size - 1) // page_size
                if total_records else 0
            )

            # -------------------------
            # FETCH DATA
            # -------------------------

            claims = frappe.get_list(
                "Expense Claim",
                fields=fields,
                filters=filters,
                order_by="`tabExpense Claim`.posting_date desc",
                group_by="`tabExpense Claim`.name",
                start=start,
                page_length=page_size,
            )

            for claim in claims:

                claim["total_claimed_amount"] = fmt_money(
                    claim["total_claimed_amount"],
                    currency=global_defaults.get(
                        "default_currency"
                    ),
                )

            return api_response(
                True,
                "Team Expense Claim Get Successfully",
                {
                    "total": total_records,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "data": claims
                }
            )

        # =====================================================
        # WITH WORKFLOW
        # =====================================================

        filters.extend([
            ["docstatus", "!=", 2],
            ["workflow_state", "is", "set"]
        ])

        fields = [
            "`tabExpense Claim`.name",
            "`tabExpense Claim`.employee",
            "`tabExpense Claim`.employee_name",
            "`tabExpense Claim`.workflow_state as approval_status",
            "`tabExpense Claim`.expense_approver",
            "`tabExpense Claim`.total_claimed_amount",
            "`tabExpense Claim`.posting_date",
            "`tabExpense Claim`.company",
            "`tabExpense Claim Detail`.expense_type",
            "`tabExpense Claim Detail`.name as expense_detail_name",
            "count(`tabExpense Claim Detail`.expense_type) as total_expenses",
        ]

        claims = frappe.get_list(
            "Expense Claim",
            fields=fields,
            filters=filters,
            order_by="`tabExpense Claim`.posting_date desc",
            group_by="`tabExpense Claim`.name",
        )

        # -------------------------
        # FILTER ACTIONABLE CLAIMS
        # -------------------------

        updated_expense_claim_list = []

        for doc in claims:

            if doc.get("approval_status"):

                transitions = get_transitions(
                    frappe.get_doc(
                        "Expense Claim",
                        doc["name"]
                    )
                )

                if transitions:

                    doc["total_claimed_amount"] = fmt_money(
                        doc["total_claimed_amount"],
                        currency=global_defaults.get(
                            "default_currency"
                        ),
                    )

                    updated_expense_claim_list.append(doc)

        # -------------------------
        # TOTAL COUNT
        # -------------------------

        total_records = len(
            updated_expense_claim_list
        )

        total_pages = (
            (total_records + page_size - 1) // page_size
            if total_records else 0
        )

        # -------------------------
        # PAGINATED DATA
        # -------------------------

        paginated_data = updated_expense_claim_list[
            start:start + page_size
        ]

        # -------------------------
        # RESPONSE
        # -------------------------

        return api_response(
            True,
            "Team Expense Claim Get Successfully",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": paginated_data
            }
        )

    except Exception as e:

        return api_response(
            False,
            f"exception {str(e)}"
        )

@frappe.whitelist()
@validate_method(methods=["GET"])
def get_team_expense_details(expense_id):
    try:
        if not expense_id:
            return api_response(False, "Expense ID is required")

        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company", "expense_approver"]
        )

        if not emp_data:
            return api_response(False, "Employee does not exist")

        if isinstance(emp_data, list):
            emp_data = emp_data[0] if emp_data else None

        if not emp_data:
            return api_response(False, "Employee does not exist")

        if not frappe.db.exists("Expense Claim", expense_id):
            return api_response(False, f"Expense Claim {expense_id} not found")
        is_workflow = check_workflow_exists("Leave Application")

        expense = frappe.get_doc("Expense Claim", expense_id)
        global_defaults = get_global_defaults()
        currency = global_defaults.get("default_currency")

        detail = frappe.db.get_value(
            "Expense Claim Detail",
            {"parent": expense.name},
            ["expense_type", "description", "expense_date", "amount"],
            as_dict=True,
        )

        data = {
            "name": expense.name,
            "employee": expense.employee,
            "employee_name": expense.employee_name,
            "department": expense.department,
            "posting_date": expense.posting_date,
            "approval_status": expense.approval_status,
            "workflow_state": expense.get("workflow_state"),
            "expense_approver": expense.expense_approver,
            "expense_approver_name": frappe.db.get_value(
                "User", expense.expense_approver, "full_name"
            ) if expense.expense_approver else None,
            "docstatus": expense.docstatus,
            "expense_type": detail.expense_type if detail else None,
            "expense_description": detail.description if detail else None,
            "expense_date": detail.expense_date if detail and detail.expense_date else None,
            "amount": float(detail.amount) if detail and detail.amount else 0.0,
            "total_claimed_amount": expense.total_claimed_amount,
            "total_sanctioned_amount": expense.total_sanctioned_amount,
            "attachments": get_attachments("Expense Claim", expense_id),
        }
        if is_workflow:
            data["status"] = expense.get("workflow_state")
            data["workflow_active"] = "1"
        else:
            data["workflow_active"] = "0"
        data["action"] = get_action(expense)
        return api_response(True, "Expense detail get successfully.", data)

    except frappe.PermissionError:
        return api_response(False, "Not permitted for Expense")
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Error in get_team_expense_details"
        )
        return api_response(False, f"exception {str(e)}")

@frappe.whitelist()
@validate_method(methods=["POST"])
def update_status(document, document_no, status, expenses=None):
    try:
        status_field_map = {
            "Leave Application": "status",
            "Expense Claim": "approval_status",
        }
        status_field = status_field_map.get(document)

        if not status_field:
            return gen_response(400, f"Unsupported document type: {document}")

        doc = frappe.get_doc(document, document_no)

        if not doc.has_permlevel_access_to(status_field, permission_type="write"):
            field_label = status_field.replace("_", " ").title()
            return gen_response(
                403,
                f"You do not have permission to update the '{field_label}' field in this {document}.",
            )

        doc.set(status_field, status)

        if document == "Expense Claim" and expenses:
            for expense in expenses:
                for row in doc.expenses:
                    if row.get("name") == expense.get("name"):
                        row.sanctioned_amount = expense.get("sanctioned_amount")

        doc.submit()

        return api_response(
            True, f"{document} '{document_no}' status updated to '{status}'."
        )

    except frappe.PermissionError:
        return api_response(
            False,
            f"You are not permitted to perform this action on {document} '{document_no}'.",
        )

    except frappe.DoesNotExistError:
        return api_response(False, f"{document} '{document_no}' not found.")

    except Exception as e:
        return api_response(False, f"exception {str(e)}")
    
    
@frappe.whitelist()
def update_leave_status(name, action):
    try:

        doc = frappe.get_doc("Leave Application", name)
        apply_workflow(doc, action)
        return api_response(True, "Workflow State Updated Successfully")
    except frappe.PermissionError:
        return api_response(False, f"Not permitted for update {document_type}")
    except Exception as e:
        frappe.db.rollback()
        return api_response(False, f"exception {str(e)}")
    
@frappe.whitelist()
def update_expense_status(name, action, sanctioned_amount=None):
    try:
        from frappe.model.workflow import apply_workflow
        from frappe.utils import flt

        if not name:
            return api_response(False, "Expense Claim ID is required")

        if not action:
            return api_response(False, "Action is required")

        doc = frappe.get_doc("Expense Claim", name)

        # Set sanctioned amount if passed
        if sanctioned_amount is not None and str(sanctioned_amount).strip() != "":
            sanctioned_amount = flt(sanctioned_amount)

            if sanctioned_amount < 0:
                return api_response(False, "Sanctioned amount cannot be negative")

            if sanctioned_amount > flt(doc.total_claimed_amount):
                return api_response(False, "Sanctioned amount cannot be greater than claimed amount")

            # Parent field
            doc.total_sanctioned_amount = sanctioned_amount

            # Child table field update
            for row in doc.expenses:
                row.sanctioned_amount = sanctioned_amount
                # if custom field, use:
                # row.custom_sanctioned_amount = sanctioned_amount

        doc.save(ignore_permissions=True)
        doc = apply_workflow(doc, action)

        return api_response(
            True,
            "Workflow State Updated Successfully",
            {
                "name": doc.name,
                "approval_status": doc.get("approval_status"),
                "workflow_state": doc.get("workflow_state"),
                "total_sanctioned_amount": doc.get("total_sanctioned_amount")
            },
        )

    except frappe.PermissionError:
        return api_response(False, "Not permitted to update Expense Claim")

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Expense Status Update Error"
        )
        return api_response(False, f"Exception: {str(e)}")
    
# @frappe.whitelist()
# def update_workflow_state(document_type, document_no, action):
#     try:
#         from frappe.model.workflow import apply_workflow

#         doc = frappe.get_doc(document_type, document_no)
#         apply_workflow(doc, action)
#         return api_response(True, "Workflow State Updated Successfully")
#     except frappe.PermissionError:
#         return api_response(False, f"Not permitted for update {document_type}")
#     except Exception as e:
#         frappe.db.rollback()
#         return api_response(False, f"exception {str(e)}")