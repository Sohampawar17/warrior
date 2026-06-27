import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote,getdate,flt,cint,fmt_money
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url,add_ess_comment
import json
from shoption_api.otp.api import create_registration_form

import frappe
from frappe.utils import cint, flt, fmt_money

@frappe.whitelist()
@validate_method(["GET"])
def lead_list(page=1, page_size=20, status=None, search=None):
    try:
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        user = frappe.session.user

        # -----------------------------------
        # Filters
        # -----------------------------------
        assigned_leads = frappe.get_all(
            "ToDo",
            filters={
                "allocated_to": user,
                "reference_type": "Lead",
                "status":"Open"
            },
            pluck="reference_name"
        )

        filters = {
            "name": ["in", assigned_leads]
        }

        if status:
            filters["custom_lead_stage"] = status

        or_filters = []
        s = (search or "").strip()

        if s:
            or_filters = [
                ["Lead", "lead_name", "like", f"%{s}%"],
                ["Lead", "mobile_no", "like", f"%{s}%"],
            ]

        fields = [
            "name",
            "lead_name",
            "mobile_no",
            "source",
            "company_name",
            "city",
            "city as marketplace",
            "type",
            "campaign_name",
            "custom_lead_stage as status",
            "creation",
        ]

        leads = frappe.get_list(
            "Lead",
            filters=filters,
            or_filters=or_filters,
            fields=fields,
            order_by="creation desc",
            limit_start=start,
            limit_page_length=page_size,
        )

        lead_names = [d["name"] for d in leads]
        mobiles = [d["mobile_no"] for d in leads if d.get("mobile_no")]
        dealer_docs = {}
        if mobiles:
            dealer_filters = {"mobile_number": ["in", mobiles]}
            if status:
                dealer_filters["docstatus"] = 1
            rows = frappe.get_all(
                "Delear Registration",
                filters=dealer_filters,
                fields=[
                    "name",
                    "party_name",
                    "mobile_number",
                    "address_line_1",
                    "marketplace",
                    "tahshil",
                    "district",
                    "state",
                    "pincode",
                    "docstatus",
                    "shop_name"
                ],
            )
            dealer_docs = {r["mobile_number"]: r for r in rows}

        farmer_docs = {}
        if mobiles:
            farmer_filters = {"name": ["in", mobiles]}
            if status:
                farmer_filters["docstatus"] = 1

            rows = frappe.get_all(
                "Farmer Registration",
                filters=farmer_filters,
                fields=[
                    "name",
                    "party_name",
                    "mobile_number",
                    "address_line_1",
                    "marketplace",
                    "tahshil",
                    "district",
                    "state",
                    "pincode",
                    "docstatus"
                ],
            )
            farmer_docs = {r["mobile_number"]: r for r in rows}
        # -----------------------------------
        # Fetch Tags
        # -----------------------------------
        # -----------------------------------
        # Fetch Analyst Data (single query)
        # -----------------------------------
        analyst_map = {}

        if mobiles:
            analyst_rows = frappe.get_all(
                "Analyst Data",
                filters={"mobile_no": ["in", mobiles]},
                fields=["mobile_no", "rating", "rank", "turnover"]
            )

            analyst_map = {a.mobile_no: a for a in analyst_rows}

        # -----------------------------------
        # Attach Tags + Analyst Data
        # -----------------------------------
        for d in leads:
            mobile = d.get("mobile_no")
            customer_id = frappe.db.get_value("Customer", {"mobile_no": mobile}, "name")
            analyst = analyst_map.get(mobile)
            doc = dealer_docs.get(mobile) if d["type"] == "Dealer" else farmer_docs.get(mobile)
            doc = doc or {}   # ✅ FIX
            d["rating"] = analyst.rating if analyst else 0
            d["rank"] = analyst.rank if analyst else 0
            marketplace_name = frappe.db.get_value(
                "Marketplace",
                doc.get("marketplace"),
                "marketplace_name"
            ) if doc.get("marketplace") else ""
            tahsil_name = frappe.db.get_value(
                "Tahshil",
                doc.get("tahshil"),
                "tahshil"
            ) if doc.get("tahshil") else ""
            district_name = frappe.db.get_value(
                "District",
                doc.get("district"),
                "district_name"
            ) if doc.get("district") else ""
            address = ", ".join(
                str(v)
                for v in [
                    doc.get("address_line_1"),
                    marketplace_name,
                    tahsil_name,
                    district_name,
                    doc.get("state"),
                    doc.get("pincode"),
                ]
                if v
            )

            d["turnover"] = flt(analyst.turnover) if analyst else 0
            d["company_name"] = doc.get("shop_name") or ""
            d["address"] = address
            d["is_completed"] = doc.get("docstatus") == 1
            campaign = d.get("campaign_name")
            if isinstance(campaign, list):
                campaign = campaign[0] if campaign else None

            d["campaign_name"] = frappe.db.get_value(
                "Campaign",
                campaign,
                "description"
            ) or None

            d["tags"] = frappe.get_all(
                "Tag Link",
                filters={
                    "document_type": "Customer",
                    "document_name": customer_id
                },
                pluck="tag"
            )

            d["customer_id"] = customer_id or None
        # -----------------------------------
        # Correct Total Count
        # -----------------------------------
        total = frappe.db.count(
            "Lead",
            filters=filters )

        total_pages = (total + page_size - 1) // page_size

        return api_response(
            True,
            "Lead list fetched successfully",
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": leads
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Fetch Lead Error")
        return api_response(False, "Failed to fetch Lead list")
    

import json
import frappe

def normalize_phone(p):
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else d

def append_qna(lead_doc, data):
    qna_list = data.get("qna") or []
    if isinstance(qna_list, list) and qna_list:
        for row in qna_list:
            q = (row.get("questions") or "").strip()
            a = (row.get("answers") or "").strip()
            if q:
                lead_doc.append("custom_lead_questions_and_answers", {
                    "questions": q,
                    "answers": a,
                })
    else:
        for i in range(1, 11):
            q = (data.get(f"Q{i}") or "").strip()
            a = (data.get(f"Answer {i}") or "").strip()
            if q:
                lead_doc.append("custom_lead_questions_and_answers", {
                    "questions": q,
                    "answers": a,
                })

def append_columns(lead_doc, data):
    col_list = data.get("columns") or []
    if isinstance(col_list, list) and col_list:
        for row in col_list:
            col = (row.get("columns") or "").strip()
            val = (row.get("value") or "").strip()
            if col and val:
                lead_doc.append("custom_campaign_columns", {
                    "columns": col,
                    "value": val,
                })
    else:
        for i in range(1, 11):
            val = (data.get(f"Column {i}") or "").strip()
            if val:
                lead_doc.append("custom_campaign_columns", {
                    "columns": f"Column {i}",
                    "value": val,
                })

@frappe.whitelist()
@validate_method(["POST"])
def add_lead():
    try:
        data = json.loads(frappe.request.data or "{}")
        user = frappe.session.user

        lead_name = (data.get("lead_name") or "").strip()
        mobile_no = normalize_phone(data.get("mobile_no"))
        email_id = (data.get("email_id") or "").strip()
        source = (data.get("source") or "").strip()
        company_name = (data.get("company_name") or "").strip()
        city = (data.get("city") or "").strip()
        state = (data.get("state") or "").strip()
        campaign_name = (data.get("campaign_name") or "").strip()
        lead_type = data.get("lead_type")

        if not lead_name:
            return api_response(False, "lead_name is required")
        if not mobile_no:
            return api_response(False, "mobile_no is required")
        if lead_type not in ["Farmer", "Dealer"]:
            return api_response(False, "lead_type must be 'Farmer' or 'Dealer'")

        # ✅ duplicate check based on unique key
        existing = frappe.db.get_value("Lead", {"mobile_no": mobile_no}, "name")
        if existing:
            return api_response(False, "Lead already exists with this mobile number", {"existing_lead": existing})

        lead_doc = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": lead_name,
            "email_id": email_id,
            "mobile_no": mobile_no,
            "source": source,
            "type": lead_type,  # change fieldname if needed
            "company_name": company_name,
            "city": city,
            "state": state,
            # "custom_lead_stage": "New",
            "campaign_name": campaign_name,
        })

        append_qna(lead_doc, data)
        append_columns(lead_doc, data)

        lead_doc.insert(ignore_permissions=True)

        frappe.desk.form.assign_to.add({
            "assign_to": [user],
            "doctype": "Lead",
            "name": lead_doc.name,
        })

        frappe.db.commit()
        return api_response(True, "Lead created successfully", {"name": lead_doc.name})

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Add Lead Error")
        return api_response(False, "Failed to create Lead")   


@frappe.whitelist(allow_guest=True)
@validate_method(["POST"])
def add_b2c_auto_lead():
    try:
        api_auth()
        data = json.loads(frappe.request.data or "{}")
        frappe.set_user("Administrator")        
        lead_name = (data.get("lead_name") or "").strip()
        mobile_no = normalize_phone(data.get("mobile_no"))
        campaign_name = (data.get("campaign_name") or "").strip()
        lead_type = "Farmer"  # default to Farmer if not provided

        if not lead_name:
            return api_response(False, "lead_name is required")
        if not mobile_no:
            return api_response(False, "mobile_no is required")
        if lead_type not in ["Farmer", "Dealer"]:
            return api_response(False, "lead_type must be 'Farmer' or 'Dealer'")
        if not campaign_name:
            return api_response(False, "campaign_name is required")
            # ✅ duplicate check based on unique key
        existing = frappe.db.get_value("Lead", {"mobile_no": mobile_no,"campaign_name": campaign_name,"type": lead_type}, "name")
        if existing:
            return api_response(False, "Lead already exists with this mobile number and campaign", {"existing_lead": existing})

        lead_doc = frappe.get_doc({
            "doctype": "Lead",
            "lead_name": lead_name,
            "mobile_no": mobile_no,
            "type": lead_type,  # change fieldname if needed
            "campaign_name": campaign_name,
        })
        lead_doc.insert(ignore_permissions=True)

        if lead_doc.name:
            create_registration_form(lead_type, lead_doc.name,mobile_no,lead_name)
        frappe.db.commit()
        return api_response(True, "Lead created successfully", {"lead_id": lead_doc.name,
                                                                "lead_name": lead_name,
                                                                "mobile_no": mobile_no,
                                                                "lead_type": lead_type,
                                                                "campaign_name": campaign_name})

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Add Lead Error")
        return api_response(False, "Failed to create Lead")   


@frappe.whitelist()
@validate_method(["GET"])
def lead_status():
    try:
        status_list = frappe.get_all("Lead Stages", pluck="name",order_by="creation asc")
        return api_response(True, "Lead status list fetched", status_list)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "lead_status")
        return api_response(False, "Failed to fetch lead status list")
    
@frappe.whitelist()
@validate_method(["GET"])
def lead_source():
    try:
        source_list = frappe.get_all(
            "Lead Source",
            filters={"name": ["!=", "Existing Customer"]},
            pluck="name",
            order_by="name asc"
        )
        return api_response(True, "Lead source list fetched", source_list)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "lead_source")
        return api_response(False, "Failed to fetch lead source list")


@frappe.whitelist()
@validate_method(["GET"])
def campaign_list():
    try:
        campaign=frappe.get_all("Campaign Warriors", filters={"parenttype": "Campaign","warrior": frappe.session.user}, pluck="parent")
        campaign_list = frappe.get_all("Campaign", filters={"name": ["in", campaign]},  fields=["name as id","campaign_name","description","custom_campaign_for as type"],order_by="creation asc")
        return api_response(True, "Campaign list fetched", campaign_list)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "campaign_list")
        return api_response(False, "Failed to fetch campaign list")

@frappe.whitelist()
@validate_method(["GET"])
def lead_details(name=None):
    try:
        lead_name = name or ""
        lead_name = lead_name.strip()
        if not lead_name:
            return api_response(False, "Provide 'name'")

        if not frappe.db.exists("Lead", lead_name):
            return api_response(False, "Lead not found")

        lead_doc = frappe.get_doc("Lead", lead_name)
        user = frappe.session.user
        # -----------------------
        # ✅ CHECK ASSIGNMENT
        # -----------------------
        is_assigned = frappe.db.exists(
            "ToDo",
            {
                "reference_type": "Lead",
                "reference_name": lead_doc.name,
                "allocated_to": user,
                "status": "Open"
            }
        )

        if not is_assigned:
            return api_response(False, "You are not assigned to this Lead")
        doctype = "Delear Registration" if lead_doc.type == "Dealer" else "Farmer Registration"
        address = frappe.db.get_value(
            doctype,
            {"mobile_number": lead_doc.mobile_no},
            ["marketplace", "tahshil", "district", "state", "country", "pincode","email_id"],
            as_dict=True
        )

        # -----------------------
        # ✅ Fetch display names
        # -----------------------

        marketplace_name = (
            frappe.db.get_value("Marketplace", address.marketplace, "marketplace_name")
            if address and address.marketplace else None
        )

        tahsil_name = (
            frappe.db.get_value("Tahshil", address.tahshil, "tahshil")
            if address and address.tahshil else None
        )

        district_name = (
            frappe.db.get_value("District", address.district, "district_name")
            if address and address.district else None
        )

        # -----------------------
        # ✅ Main Lead Details
        # -----------------------

        lead_data = {
            "name": lead_doc.name,
            "lead_name": lead_doc.lead_name,
            "email_id": lead_doc.email_id if lead_doc.email_id else address.email_id,
            "mobile_no": lead_doc.mobile_no,
            "source": lead_doc.source,
            "lead_type": lead_doc.type,
            "company_name": lead_doc.company_name,
            "campaign_name":frappe.db.get_value(
                "Campaign",
                lead_doc.campaign_name,
                "description"
            ) or None,
            "status": lead_doc.custom_lead_stage,
            "lead_city": lead_doc.city if lead_doc.city else (marketplace_name if address else None),
            "lead_state": lead_doc.state if lead_doc.state else (address.state if address else None),
            "marketplace": marketplace_name if address else None,
            "tahshil": tahsil_name if address else None,
            "district": district_name if address else None,
            "state": address.state if address else None,
            "country": address.country if address else None,
            "pincode": str(address.pincode) if address else None,
            "creation": lead_doc.creation,
            "owner": lead_doc.owner,
        }
        analyst = frappe.db.get_value(
                "Analyst Data",
                {"mobile_no": lead_doc.mobile_no},
                ["mobile_no", "rating", "rank", "turnover"],
                as_dict=True
            )
        lead_data["rating"] = analyst.rating if analyst else 0
        lead_data["rank"] = analyst.rank if analyst else 0

        turnover = flt(analyst.turnover) if analyst else 0
        lead_data["turnover"] = turnover
        # -----------------------
        # ✅ Q/A Child Table
        # -----------------------
        qna_list = []
        for row in lead_doc.custom_lead_questions_and_answers:
            qna_list.append({
                "questions": row.questions,
                "answers": row.answers
            })

        # -----------------------
        # ✅ Campaign Columns
        # -----------------------
        columns_list = []
        for row in lead_doc.custom_campaign_columns:
            columns_list.append({
                "columns": row.columns,
                "value": row.value
            })

        # -----------------------
        # ✅ Assigned Users
        # -----------------------
        assigned_users = frappe.db.get_all(
            "ToDo",
            filters={
                "reference_type": "Lead",
                "reference_name": lead_doc.name,
                "status": "Open"
            },
            pluck="owner"
        )

        return api_response(True, "Lead details fetched successfully", {
            **lead_data,
            "qna": qna_list,
            "columns": columns_list,
            "assigned_users": assigned_users
        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Lead Details Error")
        return api_response(False, "Failed to fetch Lead details")
import frappe
import json
from frappe.utils import cint

import frappe

@frappe.whitelist()
@validate_method(["POST"])
def update_status():
    try:
        data = frappe.request.get_json() or {}

        lead_name = (data.get("name") or "").strip()
        new_status = (data.get("status") or "").strip()

        if not lead_name:
            return api_response(False, "Provide 'name'")

        if not new_status:
            return api_response(False, "Provide 'status'")

        if not frappe.db.exists("Lead", lead_name):
            return api_response(False, "Lead not found")

        frappe.db.set_value(
            "Lead",
            lead_name,
            "custom_lead_stage",
            new_status,
            update_modified=True
        )

        return api_response(
            True,
            "Lead status updated successfully",
            {
                "name": lead_name,
                "new_status": new_status
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Update Lead Status Error")
        return api_response(False, "Failed to update Lead status") 

@frappe.whitelist()
def update_lead():
    try:
        data = json.loads(frappe.request.data or "{}")
        user = frappe.session.user

        lead_name_in = (data.get("name") or "").strip()
        mobile_no = normalize_phone(data.get("mobile_no"))
        replace_child_tables = int(data.get("replace_child_tables") or 0)

        if not data.get("name"):
                return api_response(False, "name is required to identify the Lead to update")
        if not lead_name_in and not mobile_no:
            return api_response(False, "Provide 'name' or 'mobile_no' to update lead")

        # ✅ find lead
        if lead_name_in:
            if not frappe.db.exists("Lead", lead_name_in):
                return api_response(False, "Lead not found", {"name": lead_name_in})
            lead_doc = frappe.get_doc("Lead", lead_name_in)
        else:
            existing = frappe.db.get_value("Lead", {"mobile_no": mobile_no}, "name")
            if not existing:
                return api_response(False, "Lead not found with this mobile number", {"mobile_no": mobile_no})
            lead_doc = frappe.get_doc("Lead", existing)

        # ✅ validate lead_type if provided
        lead_type = data.get("lead_type")
        if lead_type and lead_type not in ["Farmer", "Dealer"]:
            return api_response(False, "lead_type must be 'Farmer' or 'Dealer'")

        # ✅ update fields only if provided
        if data.get("lead_name"): lead_doc.lead_name = (data.get("lead_name") or "").strip()
        if data.get("email_id"): lead_doc.email_id = (data.get("email_id") or "").strip()
        if data.get("source"): lead_doc.source = (data.get("source") or "").strip()
        if lead_type: lead_doc.type = lead_type  # change fieldname if needed
        if data.get("company_name"): lead_doc.company_name = (data.get("company_name") or "").strip()
        if data.get("city"): lead_doc.city = (data.get("city") or "").strip()
        if data.get("state"): lead_doc.state = (data.get("state") or "").strip()
        if data.get("campaign_name"): lead_doc.campaign_name = (data.get("campaign_name") or "").strip()

        # ✅ mobile update (be careful: unique)
        if data.get("new_mobile_no"):
            new_mobile = normalize_phone(data.get("new_mobile_no"))
            if not new_mobile:
                return api_response(False, "new_mobile_no is invalid")

            dup = frappe.db.get_value("Lead", {"mobile_no": new_mobile}, "name")
            if dup and dup != lead_doc.name:
                return api_response(False, "Another Lead already has this mobile number", {"existing_lead": dup})

            lead_doc.mobile_no = new_mobile

        # ✅ child tables handling
        if replace_child_tables:
            lead_doc.set("custom_lead_questions_and_answers", [])
            lead_doc.set("custom_campaign_columns", [])

        append_qna(lead_doc, data)
        append_columns(lead_doc, data)

        lead_doc.save(ignore_permissions=True)

        # ✅ assign current user (optional)
        frappe.desk.form.assign_to.add({
            "assign_to": [user],
            "doctype": "Lead",
            "name": lead_doc.name,
        })

        frappe.db.commit()
        return api_response(True, "Lead updated successfully", {"name": lead_doc.name})

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Lead Error")
        return api_response(False, "Failed to update Lead")
    
    
    
@frappe.whitelist()
def lead_remark():
    try:
        data = json.loads(frappe.request.data or "{}")
        user = frappe.session.user

        lead_name = (data.get("name") or "").strip()
        remark = (data.get("remark") or "").strip()

        if not lead_name:
            return api_response(False, "Provide 'name'")

        if not remark:
            return api_response(False, "Provide 'remark'")

        if not frappe.db.exists("Lead", lead_name):
            return api_response(False, "Lead not found")

        lead_doc = frappe.get_doc("Lead", lead_name)
        lead_doc.append("lead_remarks", {
            "remarks": remark,
            "remark_by": user
        })
        lead_doc.save(ignore_permissions=True)

        return api_response(
            True,
            "Remark added to Lead successfully",
            {
                "name": lead_name,
                "remark": remark
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Add Lead Remark Error")
        return api_response(False, "Failed to add remark to Lead")
    
@frappe.whitelist()
@validate_method(methods=["POST"])
def add_lead_remark(lead_name=None, remark=None):

    try:

        # -------------------------
        # VALIDATIONS
        # -------------------------
        if not lead_name:
            return api_response(False, "Lead Name is required")

        if not remark:
            return api_response(False, "Remark is required")

        # -------------------------
        # CHECK LEAD EXISTS
        # -------------------------
        if not frappe.db.exists("Lead", lead_name):
            return api_response(False, "Lead not found")

        # -------------------------
        # GET USER DETAILS
        # -------------------------
        comment_by = frappe.db.get_value(
            "User",
            frappe.session.user,
            "full_name"
        )

        # -------------------------
        # ADD COMMENT
        # -------------------------
        add_ess_comment(
            reference_doctype="Lead",
            reference_name=lead_name,
            content=remark,
            comment_email=frappe.session.user,
            comment_by=comment_by,
        )

        return api_response(
            True,
            "Lead remark added successfully"
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "add_lead_remark_error"
        )

        return api_response(
            False,
            "Failed to add lead remark"
        )
import math
import frappe
from frappe.utils import cint, pretty_date
from bs4 import BeautifulSoup

def clean_text(value):
    if not value:
        return ""

    # Remove extra spaces
    value = " ".join(str(value).split())

    # Convert to proper title case
    return value.title()

@frappe.whitelist()
@validate_method(methods=["GET", "POST"])
def get_lead_remarks(
    lead_name=None,
    page=1,
    page_size=20
):

    try:

        # -------------------------
        # VALIDATION
        # -------------------------

        if not lead_name:
            return api_response(False, "Lead Name is required")

        # -------------------------
        # CHECK LEAD     EXISTS
        # -------------------------

        if not frappe.db.exists("Lead", lead_name):
            return api_response(False, "Lead not found")

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
            ["Comment", "reference_doctype", "=", "Lead"],
            ["Comment", "reference_name", "=", lead_name],
            ["Comment", "comment_type", "=", "Comment"],
        ]

        # -------------------------
        # TOTAL COUNT
        # -------------------------

        total_records = frappe.db.count(
            "Comment",
            filters=filters
        )

        total_pages = math.ceil(
            total_records / page_size
        ) if page_size else 1

        # -------------------------
        # FETCH REMARKS
        # -------------------------

        remarks = frappe.get_all(
            "Comment",
            filters=filters,
            fields=[
                "name",
                "content as comment",
                "comment_by",
                "comment_email",
                "creation",
            ],
            order_by="creation desc",
            start=start,
            page_length=page_size
        )

        # -------------------------
        # FORMAT RESPONSE
        # -------------------------

        for row in remarks:

            user_image = frappe.db.get_value(
                "User",
                row.comment_email,
                "user_image",
                cache=True
            )
            row['comment_by'] = clean_text(row.get('comment_by'))
            row['name'] = clean_text(row.get('comment_by'))
            row["user_image"] = get_url(user_image) if user_image else ""

            row["commented"] = pretty_date(
                row.creation
            )
            raw_comment = row.comment or ""

            row["comment"] = BeautifulSoup(
                raw_comment,
                "html.parser"
            ).get_text(
                separator=" ",
                strip=True
            )

            row["created_time"] = (
                row.creation.strftime("%I:%M %p")
            )

            row["created_date"] = (
                row.creation.strftime("%d-%m-%Y")
            )

        # -------------------------
        # RESPONSE
        # -------------------------

        return api_response(
            True,
            "Lead remarks fetched successfully",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": remarks
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(),"get_lead_remarks_error")
        return api_response(False,"Failed to fetch lead remarks")
