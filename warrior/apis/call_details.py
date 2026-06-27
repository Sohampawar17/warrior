import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote,getdate,format_datetime, format_date
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url
from frappe.utils import flt,cint,fmt_money
import json
from frappe.utils.file_manager import save_file



@frappe.whitelist()
def get_call_detail_list(search=None,from_date=None, to_date=None, page=1, page_size=20):
    try:
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        filters = {"owner":frappe.session.user}

        # ✅ Date filter (posting_datetime)
        # from_date/to_date are expected as "YYYY-MM-DD"
        if from_date and to_date:
            filters["posting_datetime"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["posting_datetime"] = [">=", from_date]
        elif to_date:
            filters["posting_datetime"] = ["<=", to_date]
        or_filters = []
        if search:
            or_filters = [
                ["Call Detail Entry", "shop_name", "like", f"{search}%"],
                ["Call Detail Entry", "mobile_number", "like", f"{search}%"],
            ]

        data = frappe.get_list(
            "Call Detail Entry",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name",
                "shop_name",
                "mobile_number",
                "call_duration",
                "call_status",
                "posting_datetime",
                "customer",
                "call_type",
                "call_sub_type",
                "call_belongs_to"
            ],
            limit_start=start,
            limit_page_length=page_size,
            order_by="posting_datetime desc, modified desc",
        )
        for i in data:
            i["posting_datetime"]=format_datetime(i.posting_datetime, "dd-MM-yyyy hh:mm a")if i.posting_datetime else None
        
        total_records = frappe.db.count("Call Detail Entry", filters=filters)
        total_pages = (total_records + page_size - 1) // page_size

        return api_response(True, "Call Detail Entry List fetched successfully", {
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": data
        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_call_detail_list")
        return api_response(False, "Failed to fetch call details list", None)


def _attach_file(files, doc, fieldname):
    if fieldname in files:
        file = files.get(fieldname)

        saved = save_file(
            fname=file.filename,
            content=file.stream.read(),
            dt=doc.doctype,
            dn=doc.name,
            is_private=0
        )

        doc.set(fieldname, saved.file_url)


@frappe.whitelist()
def add_call_detail():
    try:
        body = frappe.form_dict
        files = frappe.request.files

        # Basic Validation
        if not body.get("mobile_number"):
            return api_response(False, "Mobile number is required")

        # Create new document
        doc = frappe.new_doc("Call Detail Entry")

        doc.call_status = body.get("call_status")
        doc.posting_datetime = now()
        doc.shop_name = body.get("shop_name")
        doc.mobile_number = body.get("mobile_number")
        doc.special_remark = body.get("special_remark")
        doc.call_next_date = body.get("call_next_date")
        doc.brand_present_in_shop = body.get("brand_present_in_shop")
        doc.opinion_about_credit = body.get("opinion_about_credit")
        doc.product_quality_and_rate = body.get("product_quality_and_rate")
        doc.call_duration = flt(body.get("call_duration"))
        doc.customer = body.get("customer")

        # First insert document
        doc.insert(ignore_permissions=True)

        # Attach file AFTER insert (name required)
        _attach_file(files, doc, "call_recording")

        # Save only if file attached
        if files:
            doc.save(ignore_permissions=True)

        return api_response(
            True,
            "Call Detail Entry created successfully",
            doc.name
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "add_call_detail")
        return api_response(False, "Failed to create Call Detail Entry")

@frappe.whitelist()
def call_details(call_id=None):
    try:
        if not call_id:
            return api_response(False, "Call Id is mandatory", None)

        call_id = call_id.strip()

        if not frappe.db.exists("Call Detail Entry", call_id):
            return api_response(False, "Call Detail Entry not found", None)

        doc = frappe.get_doc("Call Detail Entry", call_id)

        # Format Duration (seconds → HH:MM:SS)
        # Format Duration
        duration_seconds = doc.call_duration or 0
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        formatted_duration = f"{minutes}m {seconds}s"

        data = {
            "name": doc.name,
            "call_status": doc.call_status,
            "posting_datetime": format_datetime(doc.posting_datetime, "dd-MM-yyyy hh:mm a") 
                                if doc.posting_datetime else None,
            "call_next_date": format_date(doc.call_next_date, "dd-MM-yyyy") 
                                if doc.call_next_date else None,
            "shop_name": doc.shop_name,
            "mobile_number": doc.mobile_number,
            "special_remark": doc.special_remark,
            "brand_present_in_shop": doc.brand_present_in_shop,
            "opinion_about_credit": doc.opinion_about_credit,
            "product_quality_and_rate": doc.product_quality_and_rate,
            "call_duration_seconds": duration_seconds,
            "call_type":doc.call_type,
            "call_sub_type":doc.call_sub_type,
            "call_belongs_to":doc.call_belongs_to,
            "call_duration_formatted": formatted_duration,
            "call_recording": get_url(doc.call_recording),
            "customer":doc.customer
        }

        return api_response(True, "Call Detail fetched successfully", data)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "call_details")
        return api_response(False, "Failed to fetch Call Detail Entry", None)



# Call Details Webhook for LeadLens
import json
import hmac
import hashlib
import frappe
import secrets


def validate_signature(raw_payload, received_signature):

    if not received_signature:
        frappe.throw("Missing Signature")
    
    secret = frappe.conf.get("leadlens_webhook_secret_token")

    if not secret:
        frappe.throw("Webhook Secret Not Configured")

    generated_signature = hmac.new(
        secret.encode("utf-8"),
        raw_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(
        generated_signature,
        received_signature
    ):
        frappe.throw("Unauthorized Request")

    return True
from werkzeug.wrappers import Response

@frappe.whitelist(allow_guest=True)
@validate_method(["GET","POST"])
def call_details_webhook():
    try:
        raw_payload = frappe.request.get_data(as_text=True)
        received_signature = frappe.get_request_header(
            "X-LeadLens-Signature"
        )
        data = {
            "method": frappe.request.method,
            "url": frappe.request.url,
            "args": dict(frappe.request.args or {}),
            "form_dict": dict(frappe.form_dict or {}),
            "headers": dict(frappe.request.headers or {}),
            "data": frappe.request.get_data(as_text=True),
        }
                
        frappe.log_error(
            title="Call details response",
            message=frappe.as_json(data, indent=2)
        )
        if frappe.request.method == "GET":

            mode = frappe.form_dict.get("hub.mode")
            verify_token = frappe.form_dict.get("hub.verify_token")
            challenge = frappe.form_dict.get("hub.challenge")

            expected_token = frappe.conf.get("leadlens_webhook_secret")

            if mode == "subscribe" and verify_token == expected_token:
                return Response(
                    response=challenge,
                    status=200,
                    mimetype="text/plain"
                )

            return Response(
                response="Verification Failed",
                status=403,
                mimetype="text/plain"
            )
        validate_signature(
            raw_payload,
            received_signature
        )
        frappe.set_user("Administrator")
        payload = frappe.form_dict or json.loads(raw_payload)
        frappe.log_error(title="Payload data",message=str(payload))
        data = payload.get("data") or {}
        system_call_id = data.get("system_call_id")
        if not system_call_id:
            frappe.local.response.http_status_code = 400

            return api_response(
                False,
                "system_call_id missing"
            )

        log = frappe.get_doc({
            "doctype": "Call Webhook Log",
            "source": "LeadLens",
            "event": payload.get("event"),
            "system_call_id": system_call_id,
            "signature": received_signature,
            "payload": raw_payload,
            "processed": 0
        })

        log.insert(ignore_permissions=True)

        frappe.db.commit()

        frappe.enqueue(
            "warrior.apis.call_details.process_call_webhook",
            webhook_log=log.name,
            queue="short",
            timeout=300
        )

        return api_response(
            True,
            "Webhook Processed"
        )

    except frappe.ValidationError:

        frappe.local.response.http_status_code = 401

        return api_response(
            False,
            "Webhook Failed"
        )

    except Exception:

        frappe.db.rollback()

        frappe.log_error(
            frappe.get_traceback(),
            "LeadLens Webhook Error"
        )

        frappe.local.response.http_status_code = 500

        return api_response(
            False,
            "Webhook Failed"
        )

    finally:
        frappe.set_user("Administrator")

from frappe.utils import get_datetime


def process_call_webhook(webhook_log):

    try:
        log = frappe.get_doc("Call Webhook Log", webhook_log)
        payload = json.loads(log.payload)

        CALL_STATUS_MAPPING = {
            "Answered": "SUCCESS",
            "Missed Call": "UNANSWERED",
            "Dropped Call": "UNANSWERED",
            "Dialed": "UNANSWERED",
        }
        data = payload.get("data") or {}
        user = data.get("employee_id")
        # user = None
        # if emp_id:
        #     user = frappe.db.get_value(
        #         "Employee",
        #         emp_id,
        #         "user_id"
        #     )

        mobile_number = (
            str(data.get("phone_number") or "")
            .replace("+91", "")
            .replace("+", "")
            .strip()
        )
        is_customer =  bool(
                frappe.db.exists(
                    "Farmer Registration",
                    {
                        "mobile_number": mobile_number,
                        "docstatus": ["!=", 2]
                    }
                )
                or frappe.db.exists(
                    "Delear Registration",
                    {
                        "mobile_number": mobile_number,
                        "docstatus": ["!=", 2]
                    }
                )
            )
        call_belongs_to = "Customer" if is_customer else "Personal"
        customer = frappe.db.get_value(
            "Customer",
            {"mobile_no": mobile_number},
            ["name","customer_name"],as_dict=True
        )
        if user:
            frappe.set_user(user)
        doc = frappe.get_doc({
            "doctype": "Call Detail Entry",
            "mobile_number": mobile_number,
            "call_belongs_to": call_belongs_to,
          "customer": customer.get("name") if customer else None,
"shop_name": customer.get("customer_name") if customer else "N/A",
            "call_type": data.get("call_type"),
            "call_sub_type": data.get("call_status"),
            "call_status": CALL_STATUS_MAPPING.get(
                data.get("call_status"),
                "UNANSWERED"
            ),
            "call_duration": data.get("duration_seconds") or 0,
            "posting_datetime": get_datetime(
                    data.get("timestamp")
                ),
            "special_remark": (
                f"Call Type: {data.get('call_type')}\n"
                f"System Call ID: {data.get('system_call_id')}"
            )
        })
        doc.insert(ignore_permissions=True)
        frappe.db.set_value(
            "Call Webhook Log",
            webhook_log,
            {
                "processed": 1,
                "call_detail_entry": doc.name,
                "error_message": None
            },
            update_modified=False
        )
        frappe.db.commit()

    except Exception:
        frappe.db.rollback()
        frappe.db.set_value(
            "Call Webhook Log",
            webhook_log,
            {
                "processed": 0,
                "error_message": frappe.get_traceback()
            },
            update_modified=False
        )
        frappe.db.commit()
        frappe.log_error(
            frappe.get_traceback(),
            f"LeadLens Webhook Failed - {webhook_log}"
        )

    finally:
        frappe.set_user("Administrator")
