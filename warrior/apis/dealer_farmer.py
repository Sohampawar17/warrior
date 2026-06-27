import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote,getdate
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url,add_ess_comment
from frappe.utils import flt,cint,fmt_money
from erpnext.stock.get_item_details import get_item_details,get_item_tax_template
import json
# from frappe.desk.search import get_tags

@frappe.whitelist()
def dealer_farmer_status():
    try:
        tags = frappe.db.sql(
            """
            SELECT DISTINCT tl.tag
            FROM `tabTag Link` tl
            WHERE tl.document_type = 'Customer'
            """,
            as_dict=False
        )
        return api_response(True, "Dealer farmer status list fetched", {
            "status": ["Pending", "Active", "Inactive"],
            "order_type": ["Authorized", "Single Ordering", "Multiple Ordering"],
            "tags": [t[0] for t in tags]

        })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "dealer_farmer_status")
        return api_response(False, "Failed to fetch status list")
    
def get_customer_tags(customer_name):
    return frappe.get_all(
        "Tag Link",
        filters={
            "document_type": "Customer",
            "document_name": customer_name
        },
        pluck="tag"
    )
@frappe.whitelist()
def get_dealer_farmer_list(
    search=None,
    status=None,
    type=None,
    tags=None,
    view_brandambassador=False,
    state=None,
    districts=None,
    tehsils=None,
    page=1,
    page_size=20
):
    try:

        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        # -------------------------
        # Normalize Filters
        # -------------------------

        if isinstance(tags, str):
            tags = [
                t.strip()
                for t in tags.split(",")
                if t.strip()
            ]

        if isinstance(districts, str):
            districts = [
                d.strip()
                for d in districts.split(",")
                if d.strip()
            ]

        if isinstance(tehsils, str):
            tehsils = [
                t.strip()
                for t in tehsils.split(",")
                if t.strip()
            ]

        view_brandambassador = cint(view_brandambassador)

        status_map = {
            "Pending": 0,
            "Active": 1,
            "Inactive": 2
        }

        # -------------------------
        # Address Conditions
        # -------------------------

        # address_conditions = [
        #     """
        #     a.custom_tahshil IN (
        #         SELECT for_value
        #         FROM `tabUser Permission`
        #         WHERE user = %(user)s
        #         AND allow = 'Tahshil'
        #     )
        #     """,
        #     "a.disabled = 0"
        # ]
        address_conditions = [
            "a.disabled = 0"
        ]
        address_params = {}
        # address_params = {
        #     "user": frappe.session.user
        # }
        user_tahshils = frappe.db.get_all(
            "User Permission",
            filters={
                "user": frappe.session.user,
                "allow": "Tahshil"
            },
            pluck="for_value"
        )

        if user_tahshils:

            address_conditions.append("""
                a.custom_tahshil IN (
                    SELECT for_value
                    FROM `tabUser Permission`
                    WHERE user = %(user)s
                    AND allow = 'Tahshil'
                )
            """)

            address_params["user"] = frappe.session.user
        # -------------------------
        # State Filter
        # -------------------------

        if state:
            address_conditions.append(
                "a.state = %(state)s"
            )
            address_params["state"] = state

        # -------------------------
        # District Filter
        # -------------------------

        if districts:

            address_conditions.append(
                "a.custom_district IN %(districts)s"
            )

            address_params["districts"] = tuple(districts)

        # -------------------------
        # Tehsil Filter
        # -------------------------

        if tehsils:

            address_conditions.append(
                "a.custom_tahshil IN %(tehsils)s"
            )

            address_params["tehsils"] = tuple(tehsils)

        # -------------------------
        # Base Customer Query
        # -------------------------

        data = frappe.db.sql(f"""
            SELECT DISTINCT dl.link_name
            FROM `tabAddress` a
            JOIN `tabDynamic Link` dl
                ON dl.parent = a.name
                AND dl.link_doctype = 'Customer'
            WHERE {" AND ".join(address_conditions)}
        """, address_params)
        # -------------------------
        # Customer List
        # -------------------------
        customer_list = [
            d[0]
            for d in data
        ] if data else []
        # -------------------------
        # Base Filters
        # -------------------------

        filters = {
            "customer_group": ["in", ["Dealer", "Farmer"]],
            "custom_document_value": ["is", "set"],
            "custom_document_type": [
                "in",
                ["Delear Registration", "Farmer Registration"]
            ],
        }
        # -------------------------
        # Tag Filters
        # -------------------------
        if customer_list:
            filters["name"] = ["in", customer_list]
        if tags:

            tagged_customers = frappe.db.sql("""
                SELECT DISTINCT document_name
                FROM `tabTag Link`
                WHERE document_type = 'Customer'
                AND tag IN %(tags)s
            """, {
                "tags": tuple(tags)
            }, as_dict=True)

            tagged_customer_names = [
                row["document_name"]
                for row in tagged_customers
            ]

            if not tagged_customer_names:
                return api_response(
                    True,
                    "Dealer Farmer List fetched successfully",
                    {
                        "total": 0,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": 0,
                        "data": []
                    }
                )

            if customer_list:
                customer_list = list(
                    set(customer_list).intersection(
                        tagged_customer_names
                    )
                )
            else:
                customer_list = tagged_customer_names

        # -------------------------
        # Brand Ambassador Filter
        # -------------------------

        if view_brandambassador:

            brand_ambassador_customers = frappe.get_all(
                "Brand Ambassador",
                filters={
                    "active": 1
                },
                pluck="customer"
            )

            if not brand_ambassador_customers:

                return api_response(
                    True,
                    "Dealer Farmer List fetched successfully",
                    {
                        "total": 0,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": 0,
                        "data": []
                    }
                )

            if customer_list:

                customer_list = list(
                    set(customer_list).intersection(
                        brand_ambassador_customers
                    )
                )

            else:
                customer_list = brand_ambassador_customers

        # -------------------------
        # Final Customer Filter
        # -------------------------
        if customer_list:
            filters["name"] = ["in", customer_list]

        # -------------------------
        # Search Filters
        # -------------------------

        or_filters = []

        if search:

            or_filters = [
                ["Customer", "customer_name", "like", f"%{search}%"],
                ["Customer", "mobile_no", "like", f"%{search}%"],
            ]

        # -------------------------
        # Customers
        # -------------------------

        customers = frappe.get_list(
            "Customer",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name",
                "customer_name",
                "mobile_no",
                "customer_group",
                "custom_document_type",
                "custom_document_value",
            ],
            limit_start=start,
            limit_page_length=page_size,
            order_by="modified desc",
        )
        total_records = frappe.db.count(
            "Customer",
            filters=filters
        )

        total_pages = (
            total_records + page_size - 1
        ) // page_size

        if not customers:

            return api_response(
                True,
                "Dealer Farmer List fetched successfully",
                {
                    "total": total_records,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "data": []
                }
            )

        # -------------------------
        # Registration Docs
        # -------------------------

        dealer_docnames = [
            c["custom_document_value"]
            for c in customers
            if c["custom_document_type"] == "Delear Registration"
        ]

        farmer_docnames = [
            c["custom_document_value"]
            for c in customers
            if c["custom_document_type"] == "Farmer Registration"
        ]

        # -------------------------
        # Dealer Docs
        # -------------------------

        dealer_docs = {}

        if dealer_docnames:

            dealer_filters = {
                "name": ["in", dealer_docnames]
            }

            if status:
                dealer_filters["docstatus"] = status_map.get(status)

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

            dealer_docs = {
                r["name"]: r
                for r in rows
            }

        # -------------------------
        # Farmer Docs
        # -------------------------

        farmer_docs = {}

        if farmer_docnames:

            farmer_filters = {
                "name": ["in", farmer_docnames]
            }

            if status:
                farmer_filters["docstatus"] = status_map.get(status)

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

            farmer_docs = {
                r["name"]: r
                for r in rows
            }

        # -------------------------
        # Order Counts
        # -------------------------

        cust_names = [
            c["name"]
            for c in customers
        ]

        order_counts = {}

        if cust_names:

            rows = frappe.db.sql("""
                SELECT customer,
                       COUNT(name) AS cnt
                FROM `tabSales Order`
                WHERE docstatus != 2
                AND customer IN %(customers)s
                GROUP BY customer
            """, {
                "customers": tuple(cust_names)
            }, as_dict=True)

            order_counts = {
                r["customer"]: cint(r["cnt"])
                for r in rows
            }

        # -------------------------
        # Tags
        # -------------------------

        customer_tags = {}

        if cust_names:

            tag_rows = frappe.db.sql("""
                SELECT document_name AS customer,
                       tag
                FROM `tabTag Link`
                WHERE document_type = 'Customer'
                AND document_name IN %(customers)s
            """, {
                "customers": tuple(cust_names)
            }, as_dict=True)

            for r in tag_rows:
                customer_tags.setdefault(
                    r["customer"],
                    set()
                ).add(r["tag"])

        # -------------------------
        # Analyst Data
        # -------------------------

        analyst_map = {}

        mobiles = [
            c["mobile_no"]
            for c in customers
            if c.get("mobile_no")
        ]

        if mobiles:

            analysts = frappe.get_all(
                "Analyst Data",
                filters={
                    "mobile_no": ["in", mobiles]
                },
                fields=[
                    "mobile_no as mobile_number",
                    "rating",
                    "rank",
                    "turnover"
                ]
            )

            analyst_map = {
                a.mobile_number: a
                for a in analysts
            }

        # -------------------------
        # Helpers
        # -------------------------

        def derive_order_type(cnt):

            if cnt == 0:
                return "Authorized"

            if cnt == 1:
                return "Single Ordering"

            return "Multiple Ordering"

        def derive_status(docstatus):

            if docstatus == 1:
                return "Active"

            if docstatus == 2:
                return "Inactive"

            return "Pending"

        # -------------------------
        # Final Result
        # -------------------------

        result = []

        for c in customers:

            docname = c["custom_document_value"]

            doctype = c["custom_document_type"]

            doc = (
                dealer_docs.get(docname)
                if doctype == "Delear Registration"
                else farmer_docs.get(docname)
            )

            if not doc:
                continue

            cnt = order_counts.get(c["name"], 0)

            order_type = derive_order_type(cnt)

            if type and order_type != type:
                continue

            analyst = analyst_map.get(c["mobile_no"])

            turnover = flt(
                analyst.turnover
            ) if analyst else 0

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

            result.append({
                "name": doc["name"],
                "customer_id": c["name"],
                "customer_group": c["customer_group"],
                "rating": analyst.rating if analyst else 0,
                "rank": analyst.rank if analyst else 0,
                "turnover": turnover,
                "order_type": order_type,
                "order_count": cnt,
                "full_name": doc.get("party_name"),
                "active": derive_status(doc.get("docstatus")),
                "address": address,
                "tags": list(
                    customer_tags.get(c["name"], [])
                ),
                "shop_name": doc.get("shop_name") or "",
                "mobile_number": doc.get("mobile_number"),
                "brand_ambassador": frappe.db.get_value(
                    "Brand Ambassador",
                    {"customer": c["name"]},
                    "name"
                ) or ""
            })

        return api_response(
            True,
            "Dealer Farmer List fetched successfully",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": result
            }
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "get_dealer_farmer_list"
        )
        return api_response(
            False,
            "Failed to fetch list",
            None
        )
    
def format_address(address):
    # Fetch names from master tables
    tahsil_name = frappe.db.get_value(
        "Tahshil", address.get("custom_tahshil"), "name"
    ) if address.get("custom_tahshil") else None

    district_name = frappe.db.get_value(
        "District", address.get("custom_district"), "name"
    ) if address.get("custom_district") else None

    marketplace_name = frappe.db.get_value(
        "Marketplace", address.get("marketplace"), "name"
    ) if address.get("marketplace") else None

    return ", ".join(
        str(v)
        for v in [
            address.get("address_line1"),
            address.get("address_line2"),
            marketplace_name or address.get("city"),
            tahsil_name,
            district_name,
            address.get("state"),
            address.get("pincode"),
        ]
        if v
    )

from frappe.utils import get_url

def get_dealer_attachments(registration):
    ATTACHMENT_FIELDS = {
        "shop_front_photo": "Shop Front Photo",
        "visiting_card": "Visiting Card",
        "passbook_or_checkbook": "Passbook / Cheque Book",
        "gst_certificate": "GST Certificate",
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

from frappe.utils import get_datetime

def build_customer_activity(latest_orders, complaints, limit=20):
    activity = []

    # Sales Orders activity
    for o in latest_orders or []:
        activity.append({
            "activity": "Sales Order Created",
            "reference_type": "Sales Order",
            "reference_name": o.get("name"),
            "datetime": o.get("transaction_date"),
            "status": o.get("status"),
            "remarks":f"order booked of {o.get('grand_total')} on {o.get('transaction_date')}"
        })

    # Complaints activity
    for c in complaints or []:
        activity.append({
            "activity": "Complaint Raised",
            "reference_type": "Complaint",
            "reference_name": c.get("name"),
            "datetime": c.get("raised_on"),
            "status": c.get("status"),
             "remarks":f"we registered complaint for {c.get('subject')} on {c.get('raised_on')}"
        })

    # Sort by datetime (latest first)
    activity.sort(
        key=lambda x: get_datetime(x.get("datetime") or "1900-01-01"),
        reverse=True
    )

    return activity[:limit]

@frappe.whitelist()
def customer_target_performance(customer):
    target = frappe.db.get_value(
        "Sales Order",
        {"customer": customer, "docstatus": 1},
        "SUM(grand_total)"
    ) or 0

    achieved = frappe.db.get_value(
        "Sales Invoice",
        {"customer": customer, "docstatus": 1},
        "SUM(grand_total)"
    ) or 0

    pending = max(target - achieved, 0)
    percent = (achieved / target * 100) if target else 0

    return {
        "customer": customer,
        "target": target,
        "achieved": achieved,
        "pending": pending,
        "percent": round(percent, 2)
    }

@frappe.whitelist()
def customer_items_sales(customer):
    return frappe.db.sql(
        """
        SELECT
            sii.item_name,
            sii.item_group AS category,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1
          AND si.customer = %s
        GROUP BY sii.item_code
        ORDER BY amount DESC
        """,
        (customer,),
        as_dict=True
    )


@frappe.whitelist()
def get_dealer_farmer_details(name=None):
    try:
        reg_name = (name or "").strip()
        if not reg_name:
            return api_response(False, "name is required")

        # 1) Detect doctype
        if frappe.db.exists("Delear Registration", reg_name):
            reg_doctype = "Delear Registration"
        elif frappe.db.exists("Farmer Registration", reg_name):
            reg_doctype = "Farmer Registration"
        else:
            return api_response(False, "Registration not found")

        # 2) Fetch registration doc (pick needed fields)
        reg_fields_common = [
            "name", "party_name", "mobile_number", "email_id",
            "country", "state", "district", "tahshil", "marketplace",
            "pincode", "address_line_1", "address_line_2",
            "docstatus", "is_completed", "creation", "modified"
             
        ]
        reg_fields_dealer_extra = ["shop_name", "gst_no", "gst_verified", "register_type","shop_front_photo",
        "visiting_card",
        "passbook_or_checkbook",
        "gst_certificate",]
        reg_fields = reg_fields_common + (reg_fields_dealer_extra if reg_doctype == "Delear Registration" else [])

        registration = frappe.db.get_value(reg_doctype, reg_name, reg_fields, as_dict=True) or {}

        # 3) Linked customer (make it stricter by doctype too ✅)
        customer = frappe.db.get_value(
            "Customer",
            {"custom_document_value": reg_name, "custom_document_type": reg_doctype},
            [
                "name", "customer_name", "mobile_no", "customer_group", "disabled",
                "customer_primary_address"
            ],
            as_dict=True
        )

        # init defaults (avoid UnboundLocalError)
        primary_address = None
        order_count = 0
        latest_orders = []
        complaint_count = 0
        complaints = []
        static_from_date = "2025-04-01"
        # 5) Orders + Complaints
        if customer:
            cust_name = customer["name"]

            order_count = cint(frappe.db.count("Sales Order", {"customer": cust_name, "docstatus": ["!=", 2]}))
            latest_orders = frappe.get_all(
                "Sales Order",
                filters={"customer": cust_name, "docstatus": ["!=", 2],"transaction_date":[">=", static_from_date]},
                fields=["name", "transaction_date", "grand_total", "custom_dispatch_status as status", "delivery_date"],
                order_by="transaction_date desc, modified desc",
                limit_page_length=10
            )

            complaint_count = cint(frappe.db.count("Raise a Complaint", {"customer": cust_name}))
            complaints = frappe.get_all(
                "Raise a Complaint",
                filters={"customer": cust_name},
                fields=["name", "order_id", "complaint_type", "subject", "description", "raised_on", "status"],
                order_by="raised_on desc, modified desc",
                limit_page_length=10
            )

        # 6) Derived fields
        def derive_status(docstatus, customer_disabled=None):
            if customer_disabled:
                return "Inactive"
            if docstatus == 1:
                return "Active"
            if docstatus == 2:
                return "Inactive"
            return "Pending"

        def derive_order_type(cnt):
            if cnt == 1:
                return "Single Ordering"
            if cnt > 1:
                return "Multiple Ordering"
            return "Authorized"

        status = derive_status(registration.get("docstatus"), customer.get("disabled") if customer else None)
        order_type = derive_order_type(order_count)

        # handy locals (avoid repeating .get)
        customer_id=customer["name"]
        party_name = registration.get("party_name")
        mobile_number = registration.get("mobile_number")
        email_id = registration.get("email_id")
        shop_name = registration.get("shop_name")
        gst_no = registration.get("gst_no")
        activity_list = build_customer_activity(latest_orders, complaints, limit=20)
        analyst = frappe.db.get_value(
                "Analyst Data",
                {"mobile_no": customer.get("mobile_no")},
                ["mobile_no", "rating", "rank", "turnover"],
                as_dict=True
            )
        rating = analyst.rating if analyst else 0
        rank = analyst.rank if analyst else 0

        turnover = flt(analyst.turnover) if analyst else 0
        marketplace_name = frappe.db.get_value(
                "Marketplace",
                registration.get("marketplace"),
                "marketplace_name"
            ) if registration.get("marketplace") else ""

        tahsil_name = frappe.db.get_value(
            "Tahshil",
            registration.get("tahshil"),
            "tahshil"
        ) if registration.get("tahshil") else ""

        district_name = frappe.db.get_value(
            "District",
            registration.get("district"),
            "district_name"
        ) if registration.get("district") else ""

        address = ", ".join(
            str(v)
            for v in [
                registration.get("address_line_1"),
                marketplace_name,
                tahsil_name,
                district_name,
                registration.get("state"),
                registration.get("pincode"),
            ]
            if v
        )
        return api_response(True, "Details fetched", {
            "name": reg_name,
            "customer_id":customer_id,
            "document_type": reg_doctype,
            "status": status,
            "order_type": order_type,
            "order_count": order_count,
            # top-level fields (as you want)
            "party_name": party_name,
            "mobile_number": mobile_number,
            "email_id": email_id,
            "shop_name": shop_name,
            "gst_no": gst_no,
            "rating": rating,
            "rank": rank,
            "turnover": turnover,
            "attachments":get_dealer_attachments(registration) if reg_doctype == "Delear Registration" else [] ,
            "country": registration.get("country"),
            "state": registration.get("state"),
            "district": district_name,
            "tahshil": tahsil_name,
            "marketplace":marketplace_name,
            "pincode": registration.get("pincode"),
            "address_line_1": registration.get("address_line_1"),
            "address_line_2": registration.get("address_line_2"),
            "full_address": address,
            "business_performance":customer_target_performance(customer["name"]),
            "top_selling_products":customer_items_sales(customer["name"]),
            "tags": get_customer_tags(customer["name"]),
            "order_summery": {
                "order_count": order_count,
                "orders": latest_orders
            },
            "complaint_summery": {
                "complaint_count": complaint_count,
                "complaints": complaints
            },
            "activity": activity_list,

        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_dealer_farmer_details")
        return api_response(False, "Failed to fetch details", None)


# @frappe.whitelist()
# def business_dashboard(
#     search=None,
#     state=None,
#     district=None,
#     tehsil=None,
#     from_date=None,
#     to_date=None,
#     page=1,
#     page_length=20
# ):
#     try:
#         page = int(page or 1)
#         page_length = int(page_length or 20)
#         offset = (page - 1) * page_length

#         # -----------------------
#         # 1) Base Customer filters
#         # -----------------------
#         filters = {
#             "customer_group": ["in", ["Dealer"]],
#             "custom_document_value": ["is", "set"],
#             "custom_document_type": ["in", ["Delear Registration"]],
#         }

#         or_filters = []
#         if search:
#             or_filters = [
#                 ["Customer", "customer_name", "like", f"{search}%"],
#                 ["Customer", "mobile_no", "like", f"{search}%"],
#             ]

#         customers = frappe.get_list(
#             "Customer",
#             filters=filters,
#             or_filters=or_filters,
#             fields=[
#                 "name",
#                 "customer_name",
#                 "disabled",
#                 "customer_primary_address",
#                 "mobile_no",
#                 "custom_document_value",
#             ],
#             start=offset,
#             page_length=page_length,
#             order_by="modified desc",
#         )

#         total = frappe.db.count("Customer", filters=filters)
#         total_pages = (total + page_length - 1) // page_length

#         if not customers:
#             return api_response(True, "No dealers found", {
#                 "overview": {},
#                 "data": [],
#                 "total": total,
#                 "page": page,
#                 "page_size": page_length,
#                 "total_pages": total_pages,
#             })

#         customer_names = [c["name"] for c in customers]

#         # -----------------------
#         # 2) Address Map
#         # -----------------------
#         addr_names = tuple(
#             [c.get("customer_primary_address") for c in customers if c.get("customer_primary_address")]
#         ) or ("",)

#         addr_rows = frappe.db.sql(
#             """
#             SELECT
#                 name,
#                 city,
#                 county,
#                 custom_tahshil,
#                 state
#             FROM `tabAddress`
#             WHERE name IN %(addr_names)s
#             """,
#             {"addr_names": addr_names},
#             as_dict=True,
#         )
#         addr_map = {a["name"]: a for a in addr_rows}

#         # -----------------------
#         # 3) Date Conditions
#         # -----------------------
#         so_date_sql = ""
#         si_date_sql = ""
#         params = {"customers": tuple(customer_names)}

#         if from_date and to_date:
#             so_date_sql = " AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s"
#             si_date_sql = " AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
#             params["from_date"] = from_date
#             params["to_date"] = to_date
#         elif from_date:
#             so_date_sql = " AND so.transaction_date >= %(from_date)s"
#             si_date_sql = " AND si.posting_date >= %(from_date)s"
#             params["from_date"] = from_date
#         elif to_date:
#             so_date_sql = " AND so.transaction_date <= %(to_date)s"
#             si_date_sql = " AND si.posting_date <= %(to_date)s"
#             params["to_date"] = to_date

#         # -----------------------
#         # 4) Target Map (Apply Dealership)
#         # -----------------------
#         from_dt = getdate(from_date) if from_date else getdate(nowdate())
#         to_dt = getdate(to_date) if to_date else getdate(nowdate())

#         dealer_doc_map = {c["name"]: c.get("custom_document_value") for c in customers}
#         dealer_doc_values = [v for v in dealer_doc_map.values() if v]

#         target_rows = frappe.db.sql(
#             """
#             SELECT
#                 ad.dealer_id,
#                 SUM(ad.dealership_target) AS dealership_target
#             FROM `tabApply Dealership` ad
#             WHERE ad.docstatus = 1
#             AND ad.dealer_id IN %(dealers)s
#             AND (
#                     (ad.valid_from IS NULL OR DATE(ad.valid_from) <= %(to_dt)s)
#                 AND (ad.valid_to IS NULL OR DATE(ad.valid_to) >= %(from_dt)s)
#             )
#             GROUP BY ad.dealer_id
#             """,
#             {
#                 "dealers": tuple(dealer_doc_values) or ("",),
#                 "from_dt": from_dt,
#                 "to_dt": to_dt
#             },
#             as_dict=True,
#         )

#         target_map = {}
#         for r in target_rows:
#             did = r.get("dealer_id")
#             if did and did not in target_map:
#                 target_map[did] = flt(r.get("dealership_target") or 0)

#         # -----------------------
#         # 5) Keep only target > 0 dealers
#         # -----------------------
#         customers = [
#             c for c in customers
#             if flt(target_map.get(c.get("custom_document_value")) or 0) > 0
#         ]

#         if not customers:
#             return api_response(True, "No dealers with target found", {
#                 "overview": {},
#                 "data": [],
#                 "total": 0,
#                 "page": page,
#                 "page_size": page_length,
#                 "total_pages": 0,
#             })

#         customer_names = [c["name"] for c in customers]
#         params["customers"] = tuple(customer_names)

#         # -----------------------
#         # 6) Aggregation
#         # -----------------------
#         orders_map = dict(frappe.db.sql(
#             f"""
#             SELECT so.customer, SUM(so.grand_total)
#             FROM `tabSales Order` so
#             WHERE so.docstatus=1
#               AND so.customer IN %(customers)s
#               {so_date_sql}
#             GROUP BY so.customer
#             """,
#             params,
#             as_list=True
#         ))

#         invoice_map = dict(frappe.db.sql(
#             f"""
#             SELECT si.customer, SUM(si.grand_total)
#             FROM `tabSales Invoice` si
#             WHERE si.docstatus=1
#               AND si.customer IN %(customers)s
#               {si_date_sql}
#             GROUP BY si.customer
#             """,
#             params,
#             as_list=True
#         ))

#         collected_map = dict(frappe.db.sql(
#             f"""
#             SELECT customer, SUM(amount) FROM (
#                 SELECT so.customer, per.allocated_amount AS amount
#                 FROM `tabPayment Entry Reference` per
#                 JOIN `tabPayment Entry` pe ON pe.name=per.parent AND pe.docstatus=1
#                 JOIN `tabSales Order` so ON so.name=per.reference_name
#                 WHERE per.reference_doctype='Sales Order'
#                   AND so.customer IN %(customers)s
#                   {so_date_sql}

#                 UNION ALL

#                 SELECT si.customer, per.allocated_amount AS amount
#                 FROM `tabPayment Entry Reference` per
#                 JOIN `tabPayment Entry` pe ON pe.name=per.parent AND pe.docstatus=1
#                 JOIN `tabSales Invoice` si ON si.name=per.reference_name
#                 WHERE per.reference_doctype='Sales Invoice'
#                   AND si.customer IN %(customers)s
#                   {si_date_sql}
#             ) t
#             GROUP BY customer
#             """,
#             params,
#             as_list=True
#         ))

#         # -----------------------
#         # 7) Build Response
#         # -----------------------
#         dealers = []
#         total_target = total_orders = total_collected = total_invoiced = 0

#         for c in customers:
#             cust = c["name"]
#             addr = addr_map.get(c.get("customer_primary_address")) or {}

#             target = flt(target_map.get(c.get("custom_document_value")) or 0)
#             orders = flt(orders_map.get(cust) or 0)
#             collected = flt(collected_map.get(cust) or 0)
#             invoiced = flt(invoice_map.get(cust) or 0)
#             shortfall = max(target - invoiced, 0)

#             total_target += target
#             total_orders += orders
#             total_collected += collected
#             total_invoiced += invoiced

#             dealers.append({
#                 "customer": cust,
#                 "customer_name": c.get("customer_name"),
#                 "city": addr.get("city"),
#                 "district": addr.get("county"),
#                 "tehsil": addr.get("custom_tahshil"),
#                 "state": addr.get("state"),
#                 "mobile_no": c.get("mobile_no"),

#                 "target": round(target, 2),
#                 "amount": round(orders, 2),  # 🔥 added amount key
#                 "collected": round(collected, 2),
#                 "invoiced": round(invoiced, 2),
#                 "shortfall": round(shortfall, 2),

#                 "status": "BLOCKED" if c.get("disabled") else "ACTIVE",
#             })

#         return api_response(True, "Haq Ka Business dashboard fetched", {
#             "overview": {
#                 "total_target": round(total_target, 2),
#                 "order_amount": round(total_orders, 2),
#                 "collected": round(total_collected, 2),
#                 "invoiced": round(total_invoiced, 2),
#                 "shortfall": round(total_orders - total_collected, 2),
#                 "eligible_dealers": len(customers),
#             },
#             "data": dealers,
#             "total": total,
#             "page": page,
#             "page_size": page_length,
#             "total_pages": total_pages,
#         })

#     except Exception:
#         frappe.log_error(frappe.get_traceback(), "Haq Ka Business Dashboard API Error")
#         return api_response(False, "Failed to fetch dashboard")

import frappe
from frappe.utils import flt, getdate, nowdate

@frappe.whitelist()
def business_dashboard(
    search=None,
    state=None,
    district=None,
    tehsil=None,
    from_date=None,
    to_date=None,
    page=1,
    page_length=20
):
    try:
        page = int(page or 1)
        page_length = int(page_length or 20)
        offset = (page - 1) * page_length

        # -----------------------
        # 1) Base Customer filters
        # -----------------------
        data = frappe.db.sql("""
            SELECT DISTINCT dl.link_name
            FROM `tabAddress` a
            JOIN `tabDynamic Link` dl 
                ON dl.parent = a.name
                AND dl.link_doctype = 'Customer'
            WHERE a.custom_tahshil IN (
                SELECT for_value
                FROM `tabUser Permission`
                WHERE user = %s
                AND allow = 'Tahshil'
            )
            AND a.disabled = 0
        """, (frappe.session.user,))
        filters = {
            "customer_group": ["in", ["Dealer"]],
            "custom_document_value": ["is", "set"],
            "custom_document_type": ["in", ["Delear Registration"]]
        }
        customers_list=[]
        if data:
            customers_list = [d[0] for d in data]
            filters["name"]=["in",customers_list]

        or_filters = []
        if search:
            or_filters = [
                ["Customer", "customer_name", "like", f"{search}%"],
                ["Customer", "mobile_no", "like", f"{search}%"],
            ]

        customers = frappe.get_list(
            "Customer",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name",
                "customer_name",
                "disabled",
                "customer_primary_address",
                "mobile_no",
                "custom_document_value",
            ],
            start=offset,
            page_length=page_length,
            order_by="modified desc",
        )

        total = frappe.db.count("Customer", filters=filters)
        total_pages = (total + page_length - 1) // page_length

        if not customers:
            return api_response(True, "No dealers found", {
                "overview": {},
                "data": [],
                "total": total,
                "page": page,
                "page_size": page_length,
                "total_pages": total_pages,
            })

        # -----------------------
        # 2) Address Map
        # -----------------------
        addr_names = tuple(
            [c.get("customer_primary_address") for c in customers if c.get("customer_primary_address")]
        ) or ("",)

        addr_rows = frappe.db.sql(
            """
            SELECT
                name,
                city,
                county,
                custom_tahshil,
                state
            FROM `tabAddress`
            WHERE name IN %(addr_names)s
            """,
            {"addr_names": addr_names},
            as_dict=True,
        )
        addr_map = {a["name"]: a for a in addr_rows}

        # -----------------------
        # 2.1) Area filter (state/district/tehsil)
        # -----------------------
        if state or district or tehsil:
            filtered = []
            for c in customers:
                addr = addr_map.get(c.get("customer_primary_address")) or {}
                if state and addr.get("state") != state:
                    continue
                if district and addr.get("county") != district:
                    continue
                if tehsil and addr.get("custom_tahshil") != tehsil:
                    continue
                filtered.append(c)

            customers = filtered
            if not customers:
                return api_response(True, "No dealers found for area filters", {
                    "overview": {},
                    "data": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_length,
                    "total_pages": 0,
                })

        customer_names = [c["name"] for c in customers]

        # -----------------------
        # 3) Date Conditions
        # -----------------------
        so_date_sql = ""
        si_date_sql = ""
        params = {"customers": tuple(customer_names)}

        if from_date and to_date:
            so_date_sql = " AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s"
            si_date_sql = " AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
            params["from_date"] = from_date
            params["to_date"] = to_date
        elif from_date:
            so_date_sql = " AND so.transaction_date >= %(from_date)s"
            si_date_sql = " AND si.posting_date >= %(from_date)s"
            params["from_date"] = from_date
        elif to_date:
            so_date_sql = " AND so.transaction_date <= %(to_date)s"
            si_date_sql = " AND si.posting_date <= %(to_date)s"
            params["to_date"] = to_date

        from_dt = getdate(from_date) if from_date else getdate(nowdate())
        to_dt = getdate(to_date) if to_date else getdate(nowdate())
        if from_dt and to_dt and from_dt > to_dt:
            from_dt, to_dt = to_dt, from_dt

        # -----------------------
        # 4) ✅ PRO-RATED Target Map (Apply Dealership)
        #    dealership_target * overlap_days / total_validity_days
        # -----------------------
        dealer_doc_values = [c.get("custom_document_value") for c in customers if c.get("custom_document_value")]

        target_map = {}
        if dealer_doc_values:
            ad_rows = frappe.db.sql(
                """
                SELECT
                    ad.dealer_id,
                    ad.dealership_target,
                    DATE(ad.valid_from) AS valid_from,
                    DATE(ad.valid_to) AS valid_to
                FROM `tabApply Dealership` ad
                WHERE ad.docstatus = 1
                  AND ad.dealer_id IN %(dealers)s
                  AND ad.valid_from IS NOT NULL
                  AND ad.valid_to IS NOT NULL
                  AND DATE(ad.valid_from) <= %(to_dt)s
                  AND DATE(ad.valid_to) >= %(from_dt)s
                """,
                {
                    "dealers": tuple(dealer_doc_values) or ("",),
                    "from_dt": from_dt,
                    "to_dt": to_dt,
                },
                as_dict=True,
            )

            for r in ad_rows:
                did = r.get("dealer_id")
                doc_target = flt(r.get("dealership_target") or 0)
                vf = getdate(r.get("valid_from"))
                vt = getdate(r.get("valid_to"))

                if not did or doc_target <= 0 or not vf or not vt or vt < vf:
                    continue

                overlap_start = max(vf, from_dt)
                overlap_end = min(vt, to_dt)
                if overlap_end < overlap_start:
                    continue

                overlap_days = (overlap_end - overlap_start).days + 1
                total_days = (vt - vf).days + 1

                prorated = doc_target * (overlap_days / total_days)
                target_map[did] = flt(target_map.get(did) or 0) + prorated

        # -----------------------
        # 5) Keep only target > 0 dealers
        # -----------------------
        customers = [
            c for c in customers
            if flt(target_map.get(c.get("custom_document_value")) or 0) > 0
        ]
        analyst_map={}
        mobiles = [c["mobile_no"] for c in customers if c.get("mobile_no")]
        if mobiles:
            analyst_rows = frappe.get_all(
                "Analyst Data",
                filters={"mobile_no": ["in", mobiles]},
                fields=["mobile_no", "rating", "rank", "turnover"]
            )

            analyst_map = {a.mobile_no: a for a in analyst_rows}

        if not customers:
            return api_response(True, "No dealers with target found", {
                "overview": {},
                "data": [],
                "total": 0,
                "page": page,
                "page_size": page_length,
                "total_pages": 0,
            })

        customer_names = [c["name"] for c in customers]
        params["customers"] = tuple(customer_names)

        # -----------------------
        # 6) Aggregation
        # -----------------------
        orders_map = dict(frappe.db.sql(
            f"""
            SELECT so.customer, SUM(so.grand_total)
            FROM `tabSales Order` so
            WHERE so.docstatus=1
              AND so.customer IN %(customers)s
              {so_date_sql}
            GROUP BY so.customer
            """,
            params,
            as_list=True
        ))

        invoice_map = dict(frappe.db.sql(
            f"""
            SELECT si.customer, SUM(si.grand_total)
            FROM `tabSales Invoice` si
            WHERE si.docstatus=1
              AND si.customer IN %(customers)s
              {si_date_sql}
            GROUP BY si.customer
            """,
            params,
            as_list=True
        ))

        collected_map = dict(frappe.db.sql(
            f"""
            SELECT customer, SUM(amount) FROM (
                SELECT so.customer, per.allocated_amount AS amount
                FROM `tabPayment Entry Reference` per
                JOIN `tabPayment Entry` pe ON pe.name=per.parent AND pe.docstatus=1
                JOIN `tabSales Order` so ON so.name=per.reference_name
                WHERE per.reference_doctype='Sales Order'
                  AND so.customer IN %(customers)s
                  {so_date_sql}

                UNION ALL

                SELECT si.customer, per.allocated_amount AS amount
                FROM `tabPayment Entry Reference` per
                JOIN `tabPayment Entry` pe ON pe.name=per.parent AND pe.docstatus=1
                JOIN `tabSales Invoice` si ON si.name=per.reference_name
                WHERE per.reference_doctype='Sales Invoice'
                  AND si.customer IN %(customers)s
                  {si_date_sql}
            ) t
            GROUP BY customer
            """,
            params,
            as_list=True
        ))

        # -----------------------
        # 7) Build Response
        # -----------------------
        dealers = []
        total_target = total_orders = total_collected = total_invoiced = 0
        
        for c in customers:
            cust = c["name"]
            addr = addr_map.get(c.get("customer_primary_address")) or {}

            did = c.get("custom_document_value")
            target = flt(target_map.get(did) or 0)
            orders = flt(orders_map.get(cust) or 0)
            collected = flt(collected_map.get(cust) or 0)
            invoiced = flt(invoice_map.get(cust) or 0)

            # target vs invoiced shortfall (as you used)
            shortfall = max(target - invoiced, 0)

            total_target += target
            total_orders += orders
            total_collected += collected
            total_invoiced += invoiced
            analyst = analyst_map.get(c.get("mobile_no"))
            turnover = flt(analyst.turnover) if analyst else 0
            dealers.append({
                "customer": cust,
                "customer_name": c.get("customer_name"),
                "city": addr.get("city"),
                "district": addr.get("county"),
                "tehsil": addr.get("custom_tahshil"),
                "state": addr.get("state"),
                "mobile_no": c.get("mobile_no"),
                "rating":analyst.rating if analyst else 0,
                "rank":analyst.rank if analyst else 0,
                "turnover": turnover,
                "target": round(target, 2),
                "amount": round(orders, 2),
                "collected": round(collected, 2),
                "invoiced": round(invoiced, 2),
                "shortfall": round(shortfall, 2),

                "status": "BLOCKED" if c.get("disabled") else "ACTIVE",
            })

        return api_response(True, "Haq Ka Business dashboard fetched", {
            "overview": {
                "total_target": round(total_target, 2),
                "order_amount": round(total_orders, 2),
                "collected": round(total_collected, 2),
                "invoiced": round(total_invoiced, 2),

                # orders vs collected shortfall (as you used)
                "shortfall": round(total_orders - total_collected, 2),
                "eligible_dealers": len(customers),
            },
            "data": dealers,
            "total": total,
            "page": page,
            "page_size": page_length,
            "total_pages": total_pages,
        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Haq Ka Business Dashboard API Error")
        return api_response(False, "Failed to fetch dashboard")




def r2(x):
    return round(flt(x or 0), 2)

def build_address_text(addr):
    if not addr:
        return ""
    parts = [
        addr.get("address_line1"),
        addr.get("address_line2"),
        addr.get("city"),
        addr.get("custom_tahshil"),
        addr.get("county"),
        addr.get("state"),
        addr.get("pincode"),
    ]
    return ", ".join([p for p in parts if p])

@frappe.whitelist()
def dealer_details(customer, from_date=None, to_date=None):
    try:
        if not customer:
            return api_response(False, "customer is required")

        # ----------------------------
        # Customer basic details
        # ----------------------------
        cust = frappe.db.get_value(
            "Customer",
            customer,
            ["customer_name", "mobile_no", "disabled", "customer_primary_address", "custom_document_value"],
            as_dict=True
        )
        if not cust:
            return api_response(False, "Customer not found")

        addr = {}
        if cust.get("customer_primary_address"):
            addr = frappe.db.get_value(
                "Address",
                cust["customer_primary_address"],
                [
                    "address_line1", "address_line2", "city",
                    "county", "state", "pincode", "custom_tahshil"
                ],
                as_dict=True
            ) or {}

        customer_status = "BLOCKED" if cust.get("disabled") else "ACTIVE"

        # ----------------------------
        # Date filters (SO & SI)
        # ----------------------------
        params = {"customer": customer}

        so_date_sql = ""
        si_date_sql = ""
        if from_date and to_date:
            so_date_sql = " AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s"
            si_date_sql = " AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
            params["from_date"] = from_date
            params["to_date"] = to_date
        elif from_date:
            so_date_sql = " AND so.transaction_date >= %(from_date)s"
            si_date_sql = " AND si.posting_date >= %(from_date)s"
            params["from_date"] = from_date
        elif to_date:
            so_date_sql = " AND so.transaction_date <= %(to_date)s"
            si_date_sql = " AND si.posting_date <= %(to_date)s"
            params["to_date"] = to_date

        # ----------------------------
        # ✅ Target (Apply Dealership) based on from/to overlap
        # Apply Dealership.dealer_id == Customer.custom_document_value
        # ----------------------------
        dealer_id = cust.get("custom_document_value")

        from_dt = getdate(from_date) if from_date else getdate(nowdate())
        to_dt = getdate(to_date) if to_date else getdate(nowdate())

        target_amount = 0.0
        if dealer_id:
            ad_rows = frappe.db.sql(
                """
                SELECT
                    ad.dealership_target,
                    DATE(ad.valid_from) AS valid_from,
                    DATE(ad.valid_to) AS valid_to
                FROM `tabApply Dealership` ad
                WHERE ad.docstatus = 1
                AND ad.dealer_id = %(dealer_id)s
                AND ad.valid_from IS NOT NULL
                AND ad.valid_to IS NOT NULL
                AND DATE(ad.valid_from) <= %(to_dt)s
                AND DATE(ad.valid_to) >= %(from_dt)s
                """,
                {
                    "dealer_id": dealer_id,
                    "from_dt": from_dt,
                    "to_dt": to_dt
                },
                as_dict=True
            )

            for row in ad_rows:
                dealership_target = flt(row.get("dealership_target") or 0)
                valid_from = getdate(row.get("valid_from"))
                valid_to = getdate(row.get("valid_to"))

                if not valid_from or not valid_to or valid_to < valid_from:
                    continue

                # Calculate overlap period
                overlap_start = max(valid_from, from_dt)
                overlap_end = min(valid_to, to_dt)

                if overlap_end < overlap_start:
                    continue

                overlap_days = (overlap_end - overlap_start).days + 1
                total_valid_days = (valid_to - valid_from).days + 1

                prorated_target = dealership_target * (overlap_days / total_valid_days)
                target_amount += prorated_target

        # ----------------------------
        # A) Orders list (NO qty now)
        # ----------------------------
        orders = frappe.db.sql(
            f"""
            SELECT
                so.name AS sales_order,
                so.transaction_date AS order_date,
                so.delivery_date AS due_date,
                so.grand_total AS order_amount,
                CAST(IFNULL(SUM(soi.qty), 0) AS UNSIGNED) AS order_qty
            FROM `tabSales Order` so
            LEFT JOIN `tabSales Order Item` soi ON soi.parent = so.name
            WHERE so.docstatus=1
            AND so.customer=%(customer)s
            {so_date_sql}
            GROUP BY so.name
            ORDER BY so.transaction_date DESC, so.name DESC
            """,
            params,
            as_dict=True
        )


        so_names = [o["sales_order"] for o in orders]
        if not so_names:
            return api_response(True, "No orders found", {
                "customer": {
                    "customer": customer,
                    "customer_name": cust.get("customer_name"),
                    "mobile_no": cust.get("mobile_no"),
                    "status": customer_status,
                    "primary_address": build_address_text(addr),
                    "address": addr,
                    "dealer_id": dealer_id,
                },
                "cards": {
                    "target": r2(target_amount),
                    "amount": 0,
                    "received": 0,
                    "invoice_amount": 0,
                    "shortfall": 0,
                    "invoice_count": 0
                },
                "summary": {
                    "target": r2(target_amount),
                    "total_orders_placed": 0,
                    "amount": 0,
                    "invoiced_generated": 0,
                    "payment_received": 0,
                    "total_shortfall": 0
                },
                "orders": []
            })

        so_tuple = tuple(so_names)

        # ----------------------------
        # B) Product summary (items)
        # ----------------------------
        items_rows = frappe.db.sql(
            """
            SELECT parent AS sales_order, item_name, CAST(qty AS UNSIGNED) AS qty
            FROM `tabSales Order Item`
            WHERE parent IN %(so_names)s
            ORDER BY idx ASC
            """,
            {"so_names": so_tuple},
            as_dict=True
        )
        items_map = {}
        for it in items_rows:
            items_map.setdefault(it["sales_order"], []).append({
                "item_name": it["item_name"],
                "qty": int(it["qty"] or 0)  # item qty is still useful for product summary
            })

        # ----------------------------
        # C) Assignments (ToDo)
        # ----------------------------
        todo_rows = frappe.db.sql(
            """
            SELECT reference_name AS sales_order,
                   GROUP_CONCAT(DISTINCT allocated_to SEPARATOR ', ') AS assigned_to
            FROM `tabToDo`
            WHERE reference_type='Sales Order'
              AND reference_name IN %(so_names)s
              AND status='Open'
            GROUP BY reference_name
            """,
            {"so_names": so_tuple},
            as_dict=True
        )
        assigned_map = {r["sales_order"]: (r.get("assigned_to") or "") for r in todo_rows}

        # ----------------------------
        # D) Invoiced per Sales Order + invoice count
        # ----------------------------
        inv_rows = frappe.db.sql(
            f"""
            SELECT
                sii.sales_order,
                SUM(si.grand_total) AS invoiced_amount,
                COUNT(DISTINCT si.name) AS invoice_count
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus=1
            WHERE sii.sales_order IN %(so_names)s
              {si_date_sql}
            GROUP BY sii.sales_order
            """,
            {**params, "so_names": so_tuple},
            as_dict=True
        )
        invoiced_map = {r["sales_order"]: flt(r["invoiced_amount"]) for r in inv_rows}
        inv_count_map = {r["sales_order"]: int(r["invoice_count"] or 0) for r in inv_rows}
        total_invoice_count = sum(inv_count_map.values())

        # ----------------------------
        # E) Payments history (SO advances + Invoice payments mapped back to SO)
        # ----------------------------
        so_pay_hist = frappe.db.sql(
            """
            SELECT
                per.reference_name AS sales_order,
                pe.name AS payment_entry,
                pe.posting_date,
                per.allocated_amount AS amount
            FROM `tabPayment Entry Reference` per
            JOIN `tabPayment Entry` pe
              ON pe.name = per.parent AND pe.docstatus=1 AND pe.party_type='Customer'
            WHERE per.reference_doctype='Sales Order'
              AND per.reference_name IN %(so_names)s
            ORDER BY pe.posting_date DESC
            """,
            {"so_names": so_tuple},
            as_dict=True
        )

        si_pay_hist = frappe.db.sql(
            f"""
            SELECT
                x.sales_order,
                pe.name AS payment_entry,
                pe.posting_date,
                per.allocated_amount AS amount
            FROM (
                SELECT DISTINCT sii.sales_order, sii.parent AS sales_invoice
                FROM `tabSales Invoice Item` sii
                WHERE sii.sales_order IN %(so_names)s
            ) x
            JOIN `tabPayment Entry Reference` per
              ON per.reference_doctype='Sales Invoice' AND per.reference_name=x.sales_invoice
            JOIN `tabPayment Entry` pe
              ON pe.name=per.parent AND pe.docstatus=1 AND pe.party_type='Customer'
            JOIN `tabSales Invoice` si
              ON si.name=x.sales_invoice AND si.docstatus=1
            WHERE 1=1
              {si_date_sql}
            ORDER BY pe.posting_date DESC
            """,
            {**params, "so_names": so_tuple},
            as_dict=True
        )

        payment_hist_map = {}
        for row in (so_pay_hist + si_pay_hist):
            so = row["sales_order"]
            payment_hist_map.setdefault(so, []).append({
                "payment_entry": row["payment_entry"],
                "posting_date": row["posting_date"],
                "amount": r2(row["amount"]),
            })

        paid_map = {}
        last_pay_map = {}
        for so, rows in payment_hist_map.items():
            paid_map[so] = r2(sum(flt(x["amount"]) for x in rows))
            dates = [x["posting_date"] for x in rows if x.get("posting_date")]
            last_pay_map[so] = max(dates) if dates else None

        # ----------------------------
        # F) Build order breakdown + totals (NO qty now)
        # ----------------------------
        today = getdate(nowdate())

        total_amount = 0.0
        total_invoiced = 0.0
        total_paid = 0.0
        total_qty = 0
        breakdown = []
        for o in orders:
            so = o["sales_order"]
            amount = flt(o["order_amount"])
            qty = int(o["order_qty"] or 0)
            paid = flt(paid_map.get(so) or 0)
            pending = max(amount - paid, 0)

            if paid <= 0:
                pay_status = "UNPAID"
            elif pending <= 0:
                pay_status = "FULLY PAID"
            else:
                pay_status = "PARTIALLY PAID"

            due_date = o.get("due_date")
            overdue_days = 0
            if due_date and pending > 0:
                dd = getdate(due_date)
                if dd and dd < today:
                    overdue_days = (today - dd).days

            inv_amt = flt(invoiced_map.get(so) or 0)
            invoice_count = int(inv_count_map.get(so) or 0)
            total_qty += qty
            total_amount += amount
            total_invoiced += inv_amt
            total_paid += paid

            breakdown.append({
                "sales_order": so,
                "order_date": o["order_date"],
                "qty": qty, 
                # ✅ renamed for your new keys
                "amount": r2(amount),
                "paid": r2(paid),
                "pending": r2(pending),
                "current_status": pay_status,
                "pending_details": {
                    "due_date": due_date,
                    "overdue_days": int(overdue_days),
                },
                "product_summary": items_map.get(so, []),
                "payment_history": payment_hist_map.get(so, []),
                "billing_information": {
                    "invoice_generated": True if invoice_count > 0 else False,
                    "invoice_amount": r2(inv_amt),
                    "invoice_count": invoice_count,
                },
                "assigned_to": assigned_map.get(so) or "",

                "last_payment_on": last_pay_map.get(so),
            })
        target_amount=r2(target_amount)
        total_invoiced=r2(total_invoiced)
        total_shortfall = max(target_amount - total_invoiced, 0)
                # =====================================================
        # Additional Operational Details
        # =====================================================

        # Last Visit Date
        last_visit = frappe.db.sql(
            """
            SELECT MAX(visit_date)
            FROM `tabVisit`
            WHERE customer = %(customer)s
            """,
            {"customer": customer},
        )[0][0]

        # Marketplace
        marketplace = addr.get("city")  # change if stored elsewhere
        # -------------------------------------------------
        # Deposit Amount (Sum of all approved dealership deposits)
        # -------------------------------------------------
        deposit_rows = frappe.get_all(
            "Apply Dealership",
            filters={
                "dealer_id": dealer_id,
                "docstatus": 1
            },
            fields=["deposit_amount", "name"]
        )

        deposit_amount = sum(
            flt(row.get("deposit_amount")) for row in deposit_rows
        ) if deposit_rows else 0.0
        dealerships = [row.get("name") for row in deposit_rows]

        # -------------------------------------------------
        # Deposit Transaction Details (Latest Approval)
        # -------------------------------------------------
        deposit_transaction=frappe.get_all(
            "Deposit Amount Payment Approal",
            filters={
                "view_dealership": ["in",dealerships],
                "docstatus": 1
            },
            fields=["bank_transaction_id", "name as deposit_transaction","approval_date","approval_amount"],
            order_by="approval_date desc"
        )

        result = {
            "customer": {
                "customer": customer,
                "customer_name": cust.get("customer_name"),
                "mobile_no": cust.get("mobile_no"),
                "status": customer_status,
                "primary_address": build_address_text(addr),
                "address": addr,
                "dealer_id": dealer_id,
            },
            "cards": {
                "target": r2(target_amount),
                "amount": r2(total_amount),
                "received": r2(total_paid),
                "invoice_amount": r2(total_invoiced),
                "shortfall": r2(total_shortfall),
                "invoice_count": int(total_invoice_count)
            },
            "summary": {
                "target": r2(target_amount),
                "total_orders_placed": len(orders),
                "total_order_quantity": total_qty,
                "amount": r2(total_amount),
                "invoiced_generated": r2(total_invoiced),
                "payment_received": r2(total_paid),
                "total_shortfall": r2(total_shortfall)
            },
            "orders": breakdown,
            "operations": {
            "last_visit_date": last_visit,
            "marketplace": marketplace,
            "deposit_amount": r2(deposit_amount),
            "deposit_transaction": deposit_transaction
        }
            

        }
        analyst = frappe.db.get_value(
                "Analyst Data",
                {"mobile_no": cust.get("mobile_no")},
                ["mobile_no", "rating", "rank", "turnover"],
                as_dict=True
            )
        result["rating"] = analyst.rating if analyst else 0
        result["rank"] = analyst.rank if analyst else 0

        turnover = flt(analyst.turnover) if analyst else 0
        result["turnover"] = turnover
        return api_response(True, "Dealer details fetched", result)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Haq Ka Business Dealer Details API Error")
        return api_response(False, "Failed to fetch dealer details")


import frappe
from frappe.utils import cint
from warrior.apis.manager.hr_approval import check_workflow_exists, get_action
from frappe.model.workflow import get_transitions, get_workflow_name,apply_workflow

@frappe.whitelist()
def get_brand_request(search=None, page=1, page_size=20):
    try:
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        # ---------------------------------------------------------
        # Get Customers Based On User Tahshil Permission
        # ---------------------------------------------------------
        data = frappe.db.sql("""
            SELECT DISTINCT dl.link_name
            FROM `tabAddress` a
            INNER JOIN `tabDynamic Link` dl
                ON dl.parent = a.name
                AND dl.link_doctype = 'Customer'
            WHERE a.custom_tahshil IN (
                SELECT for_value
                FROM `tabUser Permission`
                WHERE user = %s
                AND allow = 'Tahshil'
            )
            AND IFNULL(a.disabled, 0) = 0
        """, (frappe.session.user,), as_dict=True)

        customers_list = [d.link_name for d in data] if data else []

        if not customers_list:
            return api_response(
                True,
                "No Brand Requests Found",
                {
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                    "data": []
                }
            )

        # ---------------------------------------------------------
        # Customer Filters
        # ---------------------------------------------------------
        filters = {
            "name": ["in", customers_list],
            "customer_group": ["in", ["Dealer"]],
            "custom_document_value": ["is", "set"],
            "custom_document_type": ["in", ["Delear Registration"]]
        }

        or_filters = []

        if search:
            or_filters = [
                ["Customer", "customer_name", "like", f"%{search}%"],
                ["Customer", "mobile_no", "like", f"%{search}%"]
            ]

        # ---------------------------------------------------------
        # Get Customers
        # ---------------------------------------------------------
        customers = frappe.get_list(
            "Customer",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name",
                "customer_name",
                "disabled",
                "customer_primary_address",
                "mobile_no",
                "custom_document_value"
            ],
            order_by="modified desc"
        )

        customer_names = [c.name for c in customers]

        if not customer_names:
            return api_response(
                True,
                "No Brand Requests Found",
                {
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                    "data": []
                }
            )

        # ---------------------------------------------------------
        # Get Portal Users
        # ---------------------------------------------------------
        users = frappe.get_all(
            "Portal User",
            filters={"parent": ["in", customer_names]},
            fields=["user"]
        )

        user_list = [u.user for u in users if u.user]

        if not user_list:
            return api_response(
                True,
                "No Brand Requests Found",
                {
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0,
                    "data": []
                }
            )

        # ---------------------------------------------------------
        # Total Count
        # ---------------------------------------------------------
        total_records = frappe.db.count(
            "Brand Access",
            filters={
                "docstatus": ["!=", 2],
                "user": ["in", user_list]
            }
        )

        total_pages = (
            (total_records + page_size - 1) // page_size
            if page_size else 1
        )

        # ---------------------------------------------------------
        # Get Brand Requests
        # ---------------------------------------------------------
        brand_requests = frappe.get_all(
            "Brand Access",
            filters={
                "docstatus": ["!=", 2],
                "user": ["in", user_list]
            },
            fields=[
                "name",
                "workflow_state as status",
                "user",
                "user_name",
                "full_name",
                "mobile_number",
                "price_list",
                "monthly_revenue",
                "creation"
            ],
            order_by="creation desc",
            limit_start=start,
            limit_page_length=page_size
        )

        return api_response(
            True,
            "Brand requests fetched",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": brand_requests
            }
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Get Brand Request API Error"
        )

        return api_response(
            False,
            "Failed to fetch brand requests"
        )
        
@frappe.whitelist()
def get_brand_request_details(brand_request_name):
    try:
        if not brand_request_name:
            return api_response(
                False,
                "Brand request name is required"
            )

        brand_request = frappe.get_doc("Brand Access", brand_request_name)
        is_workflow = check_workflow_exists("Leave Application")
        if is_workflow:
            data["status"] = expense.get("workflow_state")
            data["workflow_active"] = "1"
        else:
            data["workflow_active"] = "0"
        data["action"] = get_action(expense)
        if not brand_request:
            return api_response(
                False,
                "Brand request not found"
            )

        return api_response(
            True,
            "Brand request details fetched",
            {
                "name": brand_request.name,
                "status": brand_request.workflow_state,
                "user": brand_request.user,
                "user_name": brand_request.user_name,
                "full_name": brand_request.full_name,
                "mobile_number": brand_request.mobile_number,
                "price_list": brand_request.price_list,
                "monthly_revenue": brand_request.monthly_revenue,
                "creation": brand_request.creation
            }
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Get Brand Request Details API Error"
        )

        return api_response(
            False,
            "Failed to fetch brand request details"
        )

       
       
@frappe.whitelist()
def get_brand_request_details(brand_request_name):
    try:
        if not brand_request_name:
            return api_response(
                False,
                "Brand request name is required"
            )

        brand_request = frappe.get_doc(
            "Brand Access",
            brand_request_name
        )

        if not brand_request:
            return api_response(
                False,
                "Brand request not found"
            )

        # ---------------------------------------------------------
        # Workflow Details
        # ---------------------------------------------------------
        workflow_active = "0"
        status = brand_request.workflow_state or ""
        action = []

        is_workflow = check_workflow_exists("Brand Access")

        if is_workflow:
            workflow_active = "1"
            action = get_action(brand_request)

        # ---------------------------------------------------------
        # Get Customer From Portel User
        # ---------------------------------------------------------
        customer = frappe.db.get_value(
            "Portal User",
            {"user": brand_request.user},
            "parent"
        )

        return api_response(
            True,
            "Brand request details fetched",
            {
                "name": brand_request.name,
                "status": status,
                "workflow_active": workflow_active,
                "action": action,
                "user": brand_request.user,
                "user_name": brand_request.user_name,
                "full_name": brand_request.full_name,
                "mobile_number": brand_request.mobile_number,
                "price_list": brand_request.price_list,
                "monthly_revenue": brand_request.monthly_revenue,
                "customer": customer,
                "creation": brand_request.creation
            }
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Get Brand Request Details API Error"
        )

        return api_response(
            False,
            "Failed to fetch brand request details"
        )
        
@frappe.whitelist()
def update_brand_request_status(name, action):
    try:

        doc = frappe.get_doc("Brand Access", name)
        apply_workflow(doc, action)
        return api_response(True, "Workflow State Updated Successfully")
    except frappe.PermissionError:
        return api_response(False, f"Not permitted for update action {action}")
    except Exception as e:
        frappe.db.rollback()
        return api_response(False, f"exception {str(e)}")
    
    

@frappe.whitelist()
def create_brand_ambassador(customer):
    """
    Create Brand Ambassador
    Warrior -> From Session User
    Joining Date -> Current Date
    """

    try:

        # --------------------------
        # Validate Customer
        # --------------------------

        if not customer:
            frappe.throw("Customer is required")

        if not frappe.db.exists("Customer", customer):
            frappe.throw("Customer does not exist")

        # --------------------------
        # Check Existing Brand Ambassador
        # --------------------------

        existing = frappe.db.exists(
            "Brand Ambassador",
            {
                "customer": customer
            }
        )

        if existing:
            return {
                "status": False,
                "message": "Brand Ambassador already exists",
                "brand_ambassador": existing
            }

        # --------------------------
        # Session User
        # --------------------------

        warrior = frappe.session.user

        # --------------------------
        # Create Brand Ambassador
        # --------------------------

        doc = frappe.new_doc("Brand Ambassador")

        doc.customer = customer
        doc.warrior = warrior
        doc.joining_date = nowdate()
        doc.active = 1

        doc.insert(ignore_permissions=True)

        frappe.db.commit()

        # --------------------------
        # Success Response
        # --------------------------

        return {
            "status": True,
            "message": "Brand Ambassador created successfully",
            "data": {
                "name": doc.name,
                "customer": doc.customer,
                "joining_date": doc.joining_date,
                "warrior": doc.warrior,
                "active": doc.active
            }
        }

    except Exception as e:

        frappe.log_error(
            frappe.get_traceback(),
            "Create Brand Ambassador API Error"
        )

        return {
            "status": False,
            "message": str(e)
        }
 
@frappe.whitelist()
@validate_method(methods=["POST"])
def add_customer_remark(customer=None, remark=None):

    try:

        # -------------------------
        # VALIDATIONS
        # -------------------------
        if not customer:
            return api_response(False, "Customer is required")

        if not remark:
            return api_response(False, "Remark is required")

        # -------------------------
        # CHECK CUSTOMER EXISTS
        # -------------------------
        if not frappe.db.exists("Customer", customer):
            return api_response(False, "Customer not found")

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
            reference_doctype="Customer",
            reference_name=customer,
            content=remark,
            comment_email=frappe.session.user,
            comment_by=comment_by,
        )

        return api_response(
            True,
            "Customer remark added successfully"
        )

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "add_customer_remark_error"
        )
        return api_response(
            False,
            "Failed to add customer remark"
        )

import math
import frappe
from frappe.utils import cint, pretty_date
from bs4 import BeautifulSoup

@frappe.whitelist()
@validate_method(methods=["GET", "POST"])
def get_customer_remarks(
    customer=None,
    page=1,
    page_size=20
):

    try:

        # -------------------------
        # VALIDATION
        # -------------------------

        if not customer:
            return api_response(False, "Customer is required")

        # -------------------------
        # CHECK CUSTOMER EXISTS
        # -------------------------

        if not frappe.db.exists("Customer", customer):
            return api_response(False, "Customer not found")

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
            ["Comment", "reference_doctype", "=", "Customer"],
            ["Comment", "reference_name", "=", customer],
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
            row['name'] = " ".join((row.get('comment_by') or "").split())
            row["user_image"] =  get_url(user_image) if user_image else ""

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
            "Customer remarks fetched successfully",
            {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "data": remarks
            }
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(),"get_customer_remarks_error")
        return api_response(False,"Failed to fetch customer remarks")