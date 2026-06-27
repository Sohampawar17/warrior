import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url
from frappe.utils import flt,cint,fmt_money
from erpnext.stock.get_item_details import get_item_details,get_item_tax_template
import json

from frappe.utils import get_url
from urllib.parse import quote

@frappe.whitelist(allow_guest=True)
def build_pdf_download_url(doctype, name, print_format=None, letterhead=1, lang=None):
    base = get_url()

    # If print_format is given, ensure it's valid for this doctype
    if print_format:
        ok = frappe.db.exists("Print Format", {
            "name": print_format,
            "doc_type": doctype,
            "disabled": 0
        })
        if not ok:
            # fallback: remove print_format so Frappe uses standard/default
            print_format = None

    url = (
        f"{base}/api/method/frappe.utils.print_format.download_pdf"
        f"?doctype={doctype}"
        f"&name={name}"
        f"&no_letterhead={0 if letterhead else 1}"
        f"&download=1"
    )

    if print_format:
        url += f"&format={quote(print_format)}"

    if lang:
        url += f"&_lang={lang}"
    return url



@frappe.whitelist()
def get_quotation_list(search=None,customer=None,
status=None, from_date=None, to_date=None, page=1, page_size=20):
    try:
        filters = {
            "docstatus": ["!=", 2],
            # "order_type": "Shopping Cart"
            "shipping_address_name": ["is", "set"]
        }
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size
        or_filters = []

        if search:
            or_filters = [
                ["Quotation", "name", "like", f"%{search}%"],
                ["Quotation", "customer_name", "like", f"{search}%"],
                ["Quotation", "contact_mobile", "like", f"{search}%"],
            ]
        if status:
            filters["custom_quotation_status"] = status
        if customer:
            filters["quotation_to"]="Customer"
            filters["party_name"] = customer
        if not from_date:
            from_date=nowdate()
        if not to_date:
            to_date=nowdate()

        if from_date and to_date:
            filters["creation"] = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
        quotation_list=frappe.get_list("Quotation",filters=filters, or_filters=or_filters,fields=["name","customer_name","transaction_date","grand_total","custom_quotation_status as status","valid_till","owner as created_by"], limit_start=start,
            limit_page_length=page_size,order_by="creation desc")
        for i in quotation_list:
            i["created_by"] = frappe.db.get_value("User", i.created_by, "full_name")
            i["print_url"]=build_pdf_download_url("Quotation", i["name"], "Quotation Details", letterhead=1)

        total_records = frappe.db.count("Quotation", filters)
        total_pages = (total_records + page_size - 1) // page_size

        return api_response(True, "Quotation List fetched successfully", {
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": quotation_list
        })
    except Exception as e:
        return api_response(False, str(e), None)
    
@frappe.whitelist()
@validate_method(methods=["GET"])
def quotation_status():
    try:
        status_list = [
            "Draft",
            "Sent",
            "Scheduled",
            "Success",
            "Failure",
            "Converted To Order"
        ]

        return api_response(True, "Order status list fetched", status_list)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "order_status")
        return api_response(False, "Failed to fetch order status list")
    
@frappe.whitelist()
def get_quotation_details(quotation_id):
    try:
        if not quotation_id:
            return api_response(False, "Quotation ID is required")

        quotation = frappe.get_doc("Quotation", quotation_id)
        if not quotation:
            return api_response(False, "Quotation not found")

        result={}
        result["customer_name"]=quotation.customer_name
        result["customer"]=quotation.party_name
        result["customer_group"]=quotation.customer_group
        result["created_by"]=frappe.db.get_value("User",quotation.owner,"full_name") or ""
        result["maketplace"]=frappe.db.get_value("Address",quotation.shipping_address,"city") or ""
        result["transaction_date"]=quotation.transaction_date
        result["valid_till"]=quotation.valid_till
        result["net_total"]=sum((item.price_list_rate or item.rate or 0) * (item.qty or 0) or 0 for item in quotation.items)
        result["total_taxes_and_charges"]=quotation.total_taxes_and_charges
        result["grand_total"]=quotation.grand_total
        result["discount_amount"]=sum(d.discount_amount or 0 for d in quotation.items)
        result["status"]=quotation.custom_quotation_status
        result["address"]=quotation.shipping_address
        result["remark"]=quotation.terms
        result["items"]=[]
        for item in quotation.items:
            net_amount = item.amount or 0
            igst_rate = item.igst_rate or 0
            cgst_rate = item.cgst_rate or 0
            sgst_rate = item.sgst_rate or 0
            gst_rate = igst_rate + cgst_rate + sgst_rate
            igst_amt = item.igst_amount or 0
            cgst_amt = item.cgst_amount or 0
            sgst_amt = item.sgst_amount or 0
            amount = net_amount + igst_amt + cgst_amt + sgst_amt
            rate_incl_gst = round(
                item.rate * (1 + gst_rate / 100),
                2
            )
            result["items"].append({
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "image": frappe.db.get_value("Item", item.item_code, "custom_image_1"),
                "qty": item.qty,
                "uom": item.uom,
                "gst_rate": gst_rate,
                "rate": item.rate,
                "actual_rate":item.price_list_rate or item.rate,
                "rate_incl_gst": rate_incl_gst,
                "discount_percentage":item.discount_percentage,
                "amount": round(amount, 2)
            })
        result["contact_mobile"]=quotation.contact_mobile
        result["gst_in"]=quotation.billing_address_gstin
        return api_response(True, "Quotation details fetched successfully", result)

    except Exception as e:

        return api_response(False, str(e), None)


@frappe.whitelist()
def get_item_list(search=None, brand=None, customer=None, page=1, page_size=20):
    try:
        if not brand:
            return api_response(False, "Brand is required")
        if not customer:
            return api_response(False, "Customer is required")

        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size
        company = get_global_defaults().get("company")
        customer_group = frappe.get_cached_value("Customer", customer, "customer_group")

        # ✅ price list once (NOT per item)
        price_list = frappe.db.get_value(
            "Price List",
            {
                "custom_customer_group": customer_group,
                "custom_brand": brand,
                "enabled": 1,
                "selling": 1
            },
            "name"
        ) or fallback_price_list

        # -----------------------------
        # Filters + search
        # -----------------------------
        filters = {
            "disabled": 0,
            "is_sales_item": 1,
            "has_variants": 0,
            "brand": brand
        }

        or_filters = None
        if search:
            or_filters = [
                ["Item", "item_code", "like", f"%{search}%"],
                ["Item", "item_name", "like", f"%{search}%"],
                ["Item", "name", "like", f"%{search}%"],
            ]

        # -----------------------------
        # Items page
        # -----------------------------
        item_list = frappe.get_list(
            "Item",
            filters=filters,
            or_filters=or_filters,
            fields=["name","item_code", "item_name", "custom_image_1", "stock_uom"],
            limit_start=start,
            limit_page_length=page_size,
            order_by="creation desc"
        )
        total_records = frappe.db.count("Item", filters)

        if not item_list:
            return api_response(True, "No records found", {
                "total": total_records,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_records + page_size - 1) // page_size,
                "data": []
            })

        item_codes = [d.item_code for d in item_list if d.item_code]

        # -----------------------------
        # Bulk rates (Item Price)
        # -----------------------------
        rate_rows = frappe.db.sql("""
            SELECT item_code, MAX(price_list_rate) AS rate
            FROM `tabItem Price`
            WHERE selling = 1
              AND price_list = %(price_list)s
              AND item_code IN %(items)s
            GROUP BY item_code
        """, {"price_list": price_list, "items": tuple(item_codes)}, as_dict=True)

        rate_map = {r.item_code: float(r.rate or 0) for r in rate_rows}

        # -----------------------------
        # Bulk GST (Item Tax Template)
        # -----------------------------
        # item_tax_template is already on Item; fetch gst_rate for templates used in this page
        item_tax_rows = frappe.get_all(
            "Item Tax",
            filters={"parent": ["in", item_codes]},
            fields=["parent", "item_tax_template"]
        )

        item_tax_map = {
            r.parent: r.item_tax_template for r in item_tax_rows
        }
        # -----------------------------
        # Response build
        # -----------------------------
        data = []
        for it in item_list:
            base_rate = rate_map.get(it.item_code, 0.0)
            item_tax_template = item_tax_map.get(it.item_code)
            gst_rate =frappe.db.get_value("Item Tax Template",item_tax_template,"gst_rate")or 0
            rate_incl = round(base_rate * (1 + (gst_rate / 100.0)), 2)

            data.append({
                "item_code": it.item_code,
                "item_name": it.item_name,
                "image": it.custom_image_1,
                "uom": it.stock_uom,
                "discount_percentage":0,
                "actual_rate":base_rate,
                "rate": base_rate,
                "gst_rate": gst_rate,
                "rate_incl_gst": rate_incl,
                "price_list": price_list
            })

        total_pages = (total_records + page_size - 1) // page_size

        return api_response(True, "Item List fetched successfully", {
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": data
        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_item_list")
        return api_response(False, "Error fetching item list", None)


@frappe.whitelist()
def get_brands(search=None, page=1, page_size=20):
    try:
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        start = (page - 1) * page_size

        filters = {
             "brand": ["is", "set"]
        }
        if search:
            filters["brand"] = ["like", f"%{search}%"]


        rows = frappe.get_list(
            "Brand",
            filters=filters,
            fields=["name as brand_id", "brand", "custom_brand_id", "custom_image_path as image"],
            limit_start=start,
            limit_page_length=page_size,
            order_by= "brand asc"
        )

        data = [{
            "brand_id": r.get("brand_id"),
            "brand_name": r.get("brand"),
            "custom_brand_id": r.get("custom_brand_id") or None,
            "image": r.get("image") or None
        } for r in rows]

        total = frappe.db.count("Brand", filters)
        total_pages = (total + page_size - 1) // page_size

        return api_response(True, "Brand list fetched", {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": data
        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_brands")
        return api_response(False, "Error fetching brand list", [])

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

def get_order_details_with_currency(sales_order_doc, currency):
    order_response_dict = {}
    for response_fields in [
        "total_taxes_and_charges",
        "net_total",
        "discount_amount",
        "grand_total",
        "total",
    ]:
        order_response_dict[response_fields] = sales_order_doc.get(response_fields)
    return order_response_dict

@frappe.whitelist()
@validate_method(methods=["POST"])
def prepare_quotation_totals(*args, **kwargs):
    try:
        data = kwargs
        if not data.get("customer"):
            return api_response(False, "Customer is required.", None)
        if not data.get("items") or len(data.get("items")) == 0:
            return api_response(False, "At least one item is required.", None)
        if not data.get("valid_till"):
            data["valid_till"] = nowdate()
        # total_discount = 0
        for item in data.get("items"):
            item["valid_till"] = data.get("valid_till")

        global_defaults = get_global_defaults()
        sales_order_doc = frappe.get_doc(
            doctype="Quotation", company=global_defaults.get("default_company")
        )
        sales_order_doc.update(data)
        # sales_order_doc.discount_amount = total_discount
        sales_order_doc.apply_discount_on = "Grand Total"
        sales_order_doc.run_method("set_missing_values")
        sales_order_doc.run_method("calculate_taxes_and_totals")
        sales_order_doc = json.loads(sales_order_doc.as_json())
        return api_response(
            True,
            "Quotation details get successfully",
            get_order_details_with_currency(
                sales_order_doc, global_defaults.get("default_currency")
            ),
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "prepare_quotation_totals")
        return api_response(False, "Error preparing quotation totals", [])
    
@frappe.whitelist()
@validate_method(methods=["POST"])
def create_quotation(*args, **kwargs):
    try:
        data = kwargs
        if not data.get("customer"):
            return api_response(False, "Customer is required.", None)
        if not data.get("items") or len(data.get("items")) == 0:
            return api_response(False, "At least one item is required.", None)
        data["terms"]=data.get("remark") or "Terms and Conditions not provided by customer."
        data["quotation_to"] = "Customer"
        data["party_name"]=data.get("customer")
        data["order_type"]="Shopping Cart"
        if not data.get("valid_till"):
            validity_days = cint(frappe.db.get_single_value("CRM Settings", "default_valid_till") or 0)
            data["valid_till"] = add_days(nowdate(), validity_days)

        # total_discount = 0
        for item in data.get("items"):
            item["valid_till"] = data.get("valid_till")
            customer_group = frappe.get_cached_value("Customer", data.get("customer"), "customer_group")
            brand=frappe.get_cached_value("Item", item.get("item_code"), "brand")
            # Get original price from Price List
            price_list_name = item.get("price_list") or frappe.db.get_value(
            "Price List",
            {
                "custom_customer_group": customer_group,
                "custom_brand": brand,
                "enabled": 1,
                "selling": 1
            },
            "name")
          # fallback
            price_list_rate = frappe.db.get_value(
                "Item Price",
                {
                    "item_code": item.get("item_code"),
                    "uom": item.get("uom"),
                    "price_list": price_list_name,
                    "selling": 1
                },
                "price_list_rate"
            )

            item["price_list_rate"] = flt(price_list_rate)

            # Apply discount if provided
            if item.get("discount_percentage"):
                discount = flt(item.get("discount_percentage"))
                item["rate"] = flt(price_list_rate) * (1 - discount / 100)
            else:
                item["rate"] = flt(price_list_rate)

            # Ensure ERPNext does not override your rates
            item["ignore_pricing_rule"] = 1



        global_defaults = get_global_defaults()
        sales_order_doc = frappe.get_doc(
            doctype="Quotation", company=global_defaults.get("default_company")
        )
        sales_order_doc.update(data)
        sales_order_doc.flags.ignore_permissions = True
        sales_order_doc.run_method("set_missing_values")
        sales_order_doc.run_method("set_price_list_and_item_details")
        sales_order_doc.run_method("calculate_taxes_and_totals")
        sales_order_doc.insert()
        return api_response(
            True,
            "Quotation created successfully",
           get_print_url("Quotation",sales_order_doc.get("name"),"Quotation Details"),
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_quotation")
        return api_response(False, "Error creating quotation", [])    

@frappe.whitelist()
@validate_method(methods=["PUT"])
def update_quotation(*args, **kwargs):
    try:
        data = frappe._dict(kwargs)

        if not data.get("quotation_id"):
            return api_response(False, "Quotation ID is required.", None)
        if not data.get("customer"):
            return api_response(False, "Customer is required.", None)
        if not data.get("items"):
            return api_response(False, "At least one item is required.", None)

        # normalize
        data["terms"] = data.get("remark") or "Terms and Conditions not provided by customer."
        data["quotation_to"] = "Customer"
        data["name"] = data.get("quotation_id")
        data["party_name"] = data.get("customer")
        data["order_type"] = "Shopping Cart"

        # valid_till from CRM Settings
        if not data.get("valid_till"):
            validity_days = cint(frappe.db.get_single_value("CRM Settings", "default_valid_till") or 0)
            data["valid_till"] = add_days(nowdate(), validity_days)


        # optional: item-level copy (Quotation Item does NOT normally have valid_till)
        # keep only if you have a custom field on item row
        for item in data.get("items") or []:
            if isinstance(item, dict):
                # Set valid till
                item["valid_till"] = data.get("valid_till")
                customer_group = frappe.get_cached_value(
                    "Customer",
                    data.get("customer"),
                    "customer_group"
                )
                # Item brand
                brand = frappe.get_cached_value(
                    "Item",
                    item.get("item_code"),
                    "brand"
                )
                # Get original price from Price List
                price_list_name = item.get("price_list") or frappe.db.get_value(
                    "Price List",
                    {
                        "custom_customer_group": customer_group,
                        "custom_brand": brand,
                        "enabled": 1,
                        "selling": 1
                    },
                    "name")
                price_list_rate = frappe.db.get_value(
                    "Item Price",
                    {
                        "item_code": item.get("item_code"),
                        "uom": item.get("uom"),
                        "price_list": price_list_name,
                        "selling": 1
                    },
                    "price_list_rate"
                )
                item["price_list_rate"] = flt(price_list_rate)

                # Apply discount if provided
                if item.get("discount_percentage"):
                    discount = flt(item.get("discount_percentage"))
                    item["rate"] = flt(price_list_rate) * (1 - discount / 100)
                else:
                    item["rate"] = flt(price_list_rate)

                # Ensure ERPNext does not override your rates
                item["ignore_pricing_rule"] = 1

        defaults = get_global_defaults() or {}
        company = defaults.get("default_company")

        # Load latest doc
        doc = frappe.get_doc("Quotation", data.get("quotation_id"))

        # Make sure company is set if needed
        if company and not doc.company:
            doc.company = company

        # Apply changes
        doc.update(data)
        doc.flags.ignore_permissions = True
        doc.run_method("set_missing_values")
        doc.run_method("calculate_taxes_and_totals")

        # Handle concurrent update: retry once
        try:
            doc.save()
        except frappe.TimestampMismatchError:
            doc.reload()              # get latest version from DB
            doc.update(data)
            doc.flags.ignore_permissions = True# apply again
            doc.run_method("set_missing_values")
            doc.run_method("calculate_taxes_and_totals")
            doc.save()

        return api_response(True, "Quotation updated successfully", doc.name)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "update_quotation")
        return api_response(False, "Error updating quotation", [])

ALLOWED_STATUSES = [
    "Draft",
    "Sent",
    "Scheduled",
    "Success",
    "Failure",
    "Converted To Order",
]

@frappe.whitelist()
@validate_method(methods=["POST"])
def update_quotation_status(quotation_id=None, status=None):
    try:
        quotation_id = (quotation_id or "").strip()
        status = (status or "").strip()

        if not quotation_id:
            return api_response(False, "Quotation id is required.")

        if not status:
            return api_response(False, "Status is required.")

        if status not in ALLOWED_STATUSES:
            return api_response(
                False,
                f'Status must be one of: {", ".join(ALLOWED_STATUSES)}'
            )

        # ✅ Check quotation exists
        if not frappe.db.exists("Quotation", quotation_id):
            return api_response(False, "Invalid quotation id.")

        # ✅ Optional safety: prevent updating cancelled quotation
        docstatus = frappe.db.get_value("Quotation", quotation_id, "docstatus")
        if docstatus == 2:
            return api_response(False, "Cannot update status for a cancelled quotation.")

        # ✅ Optional: if already converted, block further changes
        current_status = frappe.db.get_value("Quotation", quotation_id, "custom_quotation_status")
        if current_status == "Converted To Order" and status != "Converted To Order":
            return api_response(False, "Quotation is already converted. Status cannot be changed.")

        frappe.db.set_value(
            "Quotation",
            quotation_id,
            "custom_quotation_status",
            status,
            update_modified=False
        )

        return api_response(True, f"Status updated for {quotation_id} to {status}.", {
            "quotation_id": quotation_id,
            "status": status
        })

    except Exception:
        frappe.log_error(frappe.get_traceback(), "update_quotation_status")
        return api_response(False, "Error updating quotation.")

@frappe.whitelist()
def download_pdf(doctype, name, format=None, doc=None, no_letterhead=0):
    from frappe.utils.pdf import get_pdf

    html = frappe.get_print(doctype, name, format, doc=doc, no_letterhead=no_letterhead)
    frappe.local.response.filename = "{name}.pdf".format(
        name=name.replace(" ", "-").replace("/", "-")
    )
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "download"

@frappe.whitelist()
def download_quotation_pdf(id):
    try:
        frappe.set_user("Administrator")  # Ensure we have permissions to read all necessary data
        sales_invoice_doc = frappe.get_doc("Quotation", id)
        default_print_format = (
            frappe.db.get_value(
                "Property Setter",
                dict(property="default_print_format", doc_type=sales_invoice_doc.doctype),
                "value",
            )
            or "Standard"
        )
        download_pdf(
            sales_invoice_doc.doctype,
            sales_invoice_doc.name,
            default_print_format,
            sales_invoice_doc,
        )
    except Exception as e:
        return api_response(False, f"Error generating PDF: {str(e)}")