import frappe
from frappe.utils import now,nowdate
from warrior.common import api_auth, api_response,get_employee_by_user, validate_employee_data,validate_method
from frappe.utils import flt,cint


import frappe
from frappe.desk.doctype.tag.tag import add_tag, remove_tag, get_tags


# -----------------------------
# Get list of all tags
# -----------------------------
@frappe.whitelist()
def get_all_tags():
    try:
        tags = frappe.get_all(
            "Tag",
            pluck="name",
            order_by="name asc"
        )

        return api_response(
            True,
           "Tags fetched successfully",
            tags
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_all_tags_api")
        return api_response(        
           False,
         "Failed to fetch tags"
        )   


# -----------------------------
# Add tag to a document
# -----------------------------
@frappe.whitelist()
def add_tag_to_document(tag, document_type, document_name):
    try:
        if not tag or not document_type or not document_name:
            return api_response(
                False,
                "Tag, Document Type and Document Name are required"
            )
        add_tag(tag, document_type, document_name)

        return api_response(        
            True,
          "Tag added successfully",
          {
                "tag": tag,
                "document_type": document_type,
                "document_name": document_name
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "add_tag_to_document_api")
        return api_response(
            False,
            "Failed to add tag"
        )


# -----------------------------
# Remove tag from document
# -----------------------------
@frappe.whitelist()
def remove_tag_from_document(tag, document_type, document_name):
    try:
        remove_tag(tag, document_type, document_name)

        return api_response(
            True,
            "Tag removed successfully"
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "remove_tag_from_document_api")
        return api_response(
            False,
            "Failed to remove tag"
        )


# -----------------------------
# Get tags of a document
# -----------------------------
@frappe.whitelist()
def get_document_tags(doctype, name):
    try:
        tags = get_tags(doctype, name)
        return api_response(
            True,
            "Document tags fetched successfully",
            tags
        )   

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_document_tags_api")
        return api_response(
            False,
            "Failed to fetch document tags"
        )


@frappe.whitelist()
def save_analyst_data(mobile_no, rating=None, rank=None, turnover=None):
    try:
        if not mobile_no:
            return api_response(False, "Mobile number is required")

        analyst_name = frappe.db.exists("Analyst Data", {"mobile_no": mobile_no})

        if analyst_name:
            doc = frappe.get_doc("Analyst Data", analyst_name)

            if rating is not None:
                doc.rating = rating
            if rank is not None:
                doc.rank = rank
            if turnover is not None:
                doc.turnover = flt(turnover)

            doc.save(ignore_permissions=True)
            message = "Analyst data updated successfully"

        else:
            doc = frappe.get_doc({
                "doctype": "Analyst Data",
                "mobile_no": mobile_no,
                "rating": rating,
                "rank": rank,
                "turnover": flt(turnover) if turnover else 0
            })
            doc.insert(ignore_permissions=True)
            message = "Analyst data created successfully"

        return api_response(
            True,
            message,
            {
                "name": doc.name,
                "mobile_no": doc.mobile_no,
                "rating": doc.rating,
                "rank": doc.rank,
                "turnover": doc.turnover
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Save Analyst Data Error")
        return api_response(False, "Failed to save analyst data")
    
@frappe.whitelist()
def get_analyst_data(mobile_no):
    try:
        if not mobile_no:
            return api_response(False, "Mobile number is required")

        analyst = frappe.db.get_value(
            "Analyst Data",
            {"mobile_no": mobile_no},
            ["name", "mobile_no", "rating", "rank", "turnover"],
            as_dict=True
        )

        if not analyst:
            return api_response(False, "Analyst data not found")

        return api_response(
            True,
            "Analyst data fetched successfully",
            analyst
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Get Analyst Data Error")
        return api_response(False, "Failed to fetch analyst data")
    
import frappe

@frappe.whitelist()
def get_shop_name_from_customer(customer):
    if not customer:
        return ""

    # Get customer details
    cust = frappe.db.get_value(
        "Customer",
        customer,
        ["customer_group", "custom_document_value"],
        as_dict=True
    )

    if not cust:
        return ""

    # Only for Dealer
    if cust.customer_group != "Dealer" or not cust.custom_document_value:
        return ""

    # Fetch shop name from Dealer Registration
    shop_name = frappe.db.get_value(
        "Delear Registration",
        cust.custom_document_value,
        "shop_name"
    )

    return shop_name or ""


       
import frappe

@frappe.whitelist()
def enqueue_bank_transfer_batches():
    frappe.enqueue(
        "warrior.api_utils.update_approved_amount_batch",
        queue="long",
        timeout=3600)        

def update_approved_amount_batch(batch_size=5000):
    start = 0

    while True:
        # 🔍 Fetch batch
        records = frappe.get_all(
            "Sales Invoice",
            filters={
                "custom_shop_name":["is","not set"],
                "customer_group":"Dealer"
            },
            fields=["name", "customer"],
            limit_start=start,
            limit_page_length=batch_size
        )

        if not records:
            print("✅ Done updating all records")
            break

        for r in records:
            shop_name=get_shop_name_from_customer(r.customer)
            frappe.db.set_value(
                "Sales Invoice",
                r.name,
                "custom_shop_name",
                shop_name,
                    update_modified=False
            )

        frappe.db.commit()  # 🔥 commit per batch
        print(f"✅ Updated batch starting at {start}")

        start += batch_size
        