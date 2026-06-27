import frappe
from frappe.model.workflow import get_transitions, apply_workflow
from frappe.utils import cint, get_url_to_form
from warrior.common import (
    api_response,
    validate_method
)


# ============================================================
# 1️⃣ Get Active Workflow Document Types
# ============================================================
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_active_workflow_document(internal=False):
    try:
        workflows = frappe.get_all(
            "Workflow",
            filters={"is_active": 1},
            fields=["document_type"]
        )

        if internal:
            return workflows

        result = [{"document_type": "All"}]
        result.extend(workflows)

        return api_response(
            True,
            "Active Workflow document fetched successfully",
            result
        )

    except frappe.PermissionError:
        return api_response(False, "Not permitted to read Workflow")
    except Exception as e:
        return api_response(False, f"Failed to get workflows: {str(e)}")


# ============================================================
# 2️⃣ Get Workflow Documents (With Pagination)
# ============================================================
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_workflow_documents(start=0, page_length=10, document_type=None, internal=False):
    try:
        start = cint(start)
        page_length = cint(page_length)

        if document_type in [None, "", "All"]:
            workflows = get_active_workflow_document(internal=True)
            workflow_doctypes = [
                row.document_type
                for row in workflows
                if row.document_type
            ]
        else:
            workflow_doctypes = [document_type]

        all_documents = []

        for doctype in workflow_doctypes:

            workflow_documents = frappe.get_list(
                doctype,
                filters={"workflow_state": ["!=", ""]},
                fields=[
                    "name",
                    "workflow_state",
                    "modified",
                ],
                order_by="modified desc"
            )

            for row in workflow_documents:
                try:
                    doc = frappe.get_doc(doctype, row["name"])
                    transitions = get_transitions(doc)

                    # Only include documents with available actions
                    if transitions:
                        row["doctype"] = doctype
                        all_documents.append(row)

                except Exception:
                    continue

        total_count = len(all_documents)

        # Pagination slicing
        paginated_data = all_documents[start:start + page_length]

        if internal:
            return total_count

        return api_response(
            True,
            "Workflow documents fetched successfully",
            {
                "total": total_count,
                "data": paginated_data
            }
        )

    except frappe.PermissionError:
        return api_response(False, "Not permitted to read document")
    except Exception as e:
        return api_response(False, f"Failed to get workflows: {str(e)}")


# ============================================================
# 3️⃣ Get Available Workflow Actions
# ============================================================
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_actions(document_type, document_no):
    try:
        doc = frappe.get_doc(document_type, document_no)
        transitions = get_transitions(doc)

        actions = [row.get("action") for row in transitions]

        return api_response(
            True,
            "Document action list fetched successfully",
            actions
        )

    except frappe.PermissionError:
        return api_response(False, "Not permitted for action")
    except Exception as e:
        return api_response(False, f"Failed to get actions: {str(e)}")


# ============================================================
# 4️⃣ Update Workflow State
# ============================================================
@frappe.whitelist()
@validate_method(methods=["POST"])
def update_workflow_state(document_type, document_no, action):
    try:
        doc = frappe.get_doc(document_type, document_no)
        apply_workflow(doc, action)

        return api_response(
            True,
            "Workflow state updated successfully"
        )

    except frappe.PermissionError:
        return api_response(False, f"Not permitted to update {document_type}")
    except Exception as e:
        frappe.db.rollback()
        return api_response(False, f"Failed to update workflow: {str(e)}")


# ============================================================
# 5️⃣ Get ERP Link for Document
# ============================================================
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_erp_link_for_document(document_type, document_no):
    try:
        link = get_url_to_form(document_type, document_no)

        return api_response(
            True,
            "Document link fetched successfully",
            link
        )

    except Exception as e:
        return api_response(False, f"Failed to get ERP link: {str(e)}")


# ============================================================
# 6️⃣ Get Print PDF (Default Print Format)
# ============================================================
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_print(document_type, document_no):
    try:
        default_print_format = (
            frappe.db.get_value(
                "Property Setter",
                {
                    "property": "default_print_format",
                    "doc_type": document_type
                },
                "value"
            )
            or "Standard"
        )

        from frappe.utils.print_format import download_pdf

        return download_pdf(
            doctype=document_type,
            name=document_no,
            format=default_print_format
        )

    except Exception as e:
        return api_response(False, f"Failed to get print: {str(e)}")
