import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote,getdate,format_datetime, format_date
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url
from frappe.utils import flt,cint,fmt_money
import json
from warrior.apis.sales_order import map_order
from frappe.utils.file_manager import save_file

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
@validate_method(methods=["GET"])
def get_customer_list(search=None, page=1, page_size=20):
    try:
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        filters = {"customer_group":["in",["Dealer","Farmer"]],}
        or_filters = None
        if search:
            or_filters = [
                ["Customer", "mobile_no", "like", f"{search}%"],
                ["Customer", "customer_name", "like", f"{search}%"],
            ]
       
        customer_list = frappe.get_list(
            "Customer",
            fields=["name as customer_id", "customer_name", "mobile_no as mobile", "customer_group"],
            filters=filters,
            or_filters=or_filters,
            limit_start=start,
            limit_page_length=page_size,
            order_by="creation desc",
        )
        total = frappe.db.count("Customer", filters)
        total_pages = (total + page_size - 1) // page_size
        return api_response(True, "Customer list fetched successfully", {
             "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": customer_list })
    except frappe.PermissionError:
        return api_response(False, "Not permitted for customer", None)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_customer_list")
        return api_response(False, "Error fetching customer list", [])

@frappe.whitelist()
def get_orders(customer=None):
    try:
        filters = {
            "docstatus": ["!=",2],
            "customer_group": ["in", ["Dealer", "Farmer"]],
        }

        if customer:
            filters["customer"] = customer

        # 1️⃣ Get all Sales Orders
        sales_orders = frappe.get_list(
            "Sales Order",
            filters=filters,
            pluck="name"
        )

        if not sales_orders:
            return api_response(True, "Orders fetched", [])

        # 2️⃣ Get Sales Orders that already have Sales Team entries
        mapped_orders = frappe.get_all(
            "Sales Team",
            filters={
                "parent": ["in", sales_orders]
            },
            pluck="parent"
        )

        mapped_orders_set = set(mapped_orders)
    
        # 3️⃣ Filter orders that DO NOT have Sales Team
        unmapped_orders = [
            so for so in sales_orders
            if so not in mapped_orders_set
        ]

        return api_response(True, "Orders fetched", unmapped_orders)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_orders")
        return api_response(False, "Failed to fetch orders")

@frappe.whitelist()
def add_visit():
    try:
        body = frappe.form_dict
        files = frappe.request.files

        # ✅ Basic Validation
        if not body.get("customer"):
            return api_response(False, "Customer is required", None)

        if not body.get("mobile_number"):
            return api_response(False, "Mobile number is required", None)

        # -----------------------------
        # Map Order if provided (with error handling)
        # -----------------------------
        order_id = body.get("order_id")
        if order_id:
            result = map_order(order_id)
            if not result.get("status"):
                return result

        # ✅ Create Visit Doc
        doc = frappe.new_doc("Visit")

        # -----------------------------
        # Basic Fields
        # -----------------------------
        doc.customer = body.get("customer")
        doc.visit_date = nowdate()
        doc.visit_time = now()
        doc.mobile_number = body.get("mobile_number")
        doc.alternate_mobile_number = body.get("alternate_mobile_number")
        doc.order_id = order_id
        doc.next_order_date = body.get("next_order_date")
        doc.brands_available_in_shop = body.get("brands_available_in_shop")
        doc.most_selling_product_and_brand = body.get("most_selling_product_and_brand")
        doc.opinion_on_credit_system = body.get("opinion_on_credit_system")
        doc.thoughts_on_gbru_product_and_quality = body.get("thoughts_on_gbru_product_and_quality")
        doc.additional_remarks = body.get("additional_remarks")

        # -----------------------------
        # 📍 Location Fields
        # (Make sure these fieldnames exist in Visit doctype)
        # -----------------------------
        doc.loc_name = body.get("loc_name")
        doc.loc_street = body.get("loc_street")
        doc.loc_country_code = body.get("loc_country_code")
        doc.loc_country = body.get("loc_country")
        doc.loc_postal_code = body.get("loc_postal_code")
        doc.loc_administrative_area = body.get("loc_administrative_area")
        doc.loc_sub_administrative_area = body.get("loc_sub_administrative_area")
        doc.loc_locality = body.get("loc_locality")
        doc.loc_sub_locality = body.get("loc_sub_locality")
        doc.lattitude = body.get("lattitude")
        doc.longitude = body.get("longitude")

        # -----------------------------
        # Insert Document
        # -----------------------------
        doc.insert(ignore_permissions=True)
        return api_response(
            True,
            "Visit created successfully",
            doc.name
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "add_visit")
        return api_response(False, "Failed to create Visit", None)

def get_attachments(registration):
    ATTACHMENT_FIELDS = {
        "shop_front_image": "Shop Front Photo",
        "shop_back_image": "Shop back Photo",
        "shop_left_image": "Shop Left Photo",
        "shop_right_image": "Shop Right Photo",
    }

    attachments = []

    for field, label in ATTACHMENT_FIELDS.items():
        file_url = registration.get(field)
        if file_url:
            attachments.append({
                "label": label,
                "file_url": get_url(file_url),   # ✅ FULL URL
            })

    return attachments

@frappe.whitelist()
def add_customer_attachment():
    try:
        body = frappe.form_dict
        files = frappe.request.files
        customer=body.get("customer")
        if not body.get("customer"):
            return api_response(False, "Customer is required", None)

        if not frappe.db.exists("Customer", customer):
            return api_response(False, "Invalid Customer", None)

        doc = frappe.get_doc("Customer", customer)
        _attach_file(files, doc, "custom_shop_left_image")
        _attach_file(files, doc, "custom_shop_right_image")
        _attach_file(files, doc, "custom_shop_front_image")
        _attach_file(files, doc, "custom_shop_back_image")
        if files:
            doc.save(ignore_permissions=True)
        return api_response(True, "customer attachments add successfully")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_customer_attachment")
        return api_response(False, "Failed to add customer attachments", None)


@frappe.whitelist()
def get_customer_attachment(customer):
    try:
        if not customer:
            return api_response(False, "Customer is required", None)

        if not frappe.db.exists("Customer", customer):
            return api_response(False, "Invalid Customer", None)

        doc = frappe.get_doc("Customer", customer)

        attachments = [
            {
                "image_type": "front",
                "file_url": get_url(doc.custom_shop_front_image) if doc.custom_shop_front_image else None,
                "customer_id": customer
            },
            {
                "image_type": "back",
                "file_url": get_url(doc.custom_shop_back_image) if doc.custom_shop_back_image else None,
                "customer_id": customer
            },
            {
                "image_type": "left",
                "file_url": get_url(doc.custom_shop_left_image) if doc.custom_shop_left_image else None,
                "customer_id": customer
            },
            {
                "image_type": "right",
                "file_url": get_url(doc.custom_shop_right_image) if doc.custom_shop_right_image else None,
                "customer_id": customer
            }
        ]

        return api_response(True, "Data Fetched successfully", attachments)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_customer_attachment")
        return api_response(False, "Failed to fetch customer attachments", None)

@frappe.whitelist()
def visit_details(visit_id=None):
    try:
        if not visit_id:
            return api_response(False, "visit id is mandatory.", None)

        if not frappe.db.exists("Visit", visit_id):
            return api_response(False, "Invalid Visit ID", None)

        doc = frappe.get_doc("Visit", visit_id)

        data = {
            "name": doc.name,
            "customer": doc.customer,
            "customer_name": doc.customer_name,
            "visit_date": doc.visit_date,
            "visit_time": doc.visit_time,
            "mobile_number": doc.mobile_number,
            "alternate_mobile_number": doc.alternate_mobile_number,
            "marketplace": doc.marketplace,
            "order_id": doc.order_id,
            "attachments": get_attachments(doc) or [],
            "next_order_date": doc.next_order_date,
            "brands_available_in_shop": doc.brands_available_in_shop,
            "most_selling_product_and_brand": doc.most_selling_product_and_brand,
            "opinion_on_credit_system": doc.opinion_on_credit_system,
            "thoughts_on_gbru_product_and_quality": doc.thoughts_on_gbru_product_and_quality,
            "additional_remarks": doc.additional_remarks,

            # 📍 Location Fields
            "loc_name": doc.loc_name,
            "loc_street": doc.loc_street,
            "loc_country_code": doc.loc_country_code,
            "loc_country": doc.loc_country,
            "loc_postal_code": doc.loc_postal_code,
            "loc_administrative_area": doc.loc_administrative_area,
            "loc_sub_administrative_area": doc.loc_sub_administrative_area,
            "loc_locality": doc.loc_locality,
            "loc_sub_locality": doc.loc_sub_locality,
            "lattitude": doc.lattitude,
            "longitude": doc.longitude,
        }

        return api_response(True, "Visit Details fetched successfully", data)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "visit_details")
        return api_response(False, "Failed to get Visit Details", None)


@frappe.whitelist()
def visit_list(page=1, page_size=20, search=None, from_date=None, to_date=None):
    try:
        page = int(page)
        page_size = int(page_size)
        start = (page - 1) * page_size

        filters = {"owner":frappe.session.user}
        # ✅ Date Filters
        if from_date and to_date:
            filters["visit_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["visit_date"] = [">=", from_date]
        elif to_date:
            filters["visit_date"] = ["<=", to_date]

        # ✅ Search Filters
        or_filters = []
        if search:
            search = search.strip()
            or_filters = [
                ["Visit", "customer_name", "like", f"%{search}%"],
                ["Visit", "mobile_number", "like", f"%{search}%"],
            ]

        # ✅ Total Count (Correct with search)
        total_records = frappe.get_all(
            "Visit",
            filters=filters,
            or_filters=or_filters,
            fields=["name"]
        )
        total_records = len(total_records)

        # ✅ Fetch Paginated Data
        visits = frappe.get_all(
            "Visit",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name",
                "customer_name",
                "visit_date",
                "visit_time",
                "mobile_number",
                "marketplace",
                "creation"
            ],
            order_by="creation desc",
            start=start,
            page_length=page_size
        )

        # ✅ Collect mobile numbers for registration check
        mobile_numbers = [v.mobile_number for v in visits if v.mobile_number]

        # Dealer registrations
        dealer_docs = frappe.get_all(
            "Delear Registration",
            filters={"mobile_number": ["in", mobile_numbers]},
            fields=["mobile_number", "docstatus"]
        )

        # Farmer registrations
        farmer_docs = frappe.get_all(
            "Farmer Registration",
            filters={"mobile_number": ["in", mobile_numbers]},
            fields=["mobile_number", "docstatus"]
        )

        dealer_map = {d.mobile_number: d.docstatus for d in dealer_docs}
        farmer_map = {f.mobile_number: f.docstatus for f in farmer_docs}

        # ✅ Format Data
        data = []

        for v in visits:

            # Registration status check
            docstatus = dealer_map.get(v.mobile_number) or farmer_map.get(v.mobile_number)

            # Combine date + time safely
            visit_datetime = None
            if v.visit_date and v.visit_time:
                visit_datetime = f"{v.visit_date} {v.visit_time}"
            marketplace=frappe.db.get_value(
				"Marketplace",
				 v.marketplace,
				"marketplace_name"
			) or ""
            data.append({
                "name": v.name,
                "customer_name": v.customer_name,
                "visit_datetime": format_datetime(visit_datetime, "dd-MM-yyyy hh:mm a") if visit_datetime else "",
                "mobile_number": v.mobile_number,
                "marketplace": marketplace,
                "status": "Completed",
                "profile_status": "Registered" if docstatus == 1 else "Unregistered"
            })

        total_pages = (total_records + page_size - 1) // page_size

        return api_response(
            True,
            "Visit list fetched successfully",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": data
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "visit_list")
        return api_response(False, "Failed to fetch Visit list", None)
