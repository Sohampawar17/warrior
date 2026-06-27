import frappe
from frappe.utils import random_string, nowdate, flt
from warrior.public.sales_order import update_dispatch_status_for_sales_order

DISPATCH_STATUS_INVOICED = "Invoiced"
DISPATCH_STATUS_PRINT_STICKERS = "Print Stickers"
DISPATCH_STATUS_PACKING_OK = "Packing OK"
DISPATCH_STATUS_OUTWARD = "Outward"
DISPATCH_STATUS_UPLOAD_LR = "Upload LR Main"
DISPATCH_STATUS_DISPATCHED = "Dispatched"
DISPATCH_STATUS_DELIVERED = "Delivered"


def _normalize_text(value):
    return (value or "").strip().lower()


def _should_use_stickers(si):
    return (
        _normalize_text(getattr(si, "customer_group", None)) == "farmer"
        and _normalize_text(getattr(si, "transporter_name", None)) == "indian post"
    )


def _can_update_dispatch_status(doc):
    return frappe.get_meta(doc.doctype).has_field("custom_dispatch_status")


def _set_dispatch_status(doc, status, update_modified=False):
    if not status or not _can_update_dispatch_status(doc):
        return
    if doc.get("custom_dispatch_status") == status:
        return
    doc.db_set("custom_dispatch_status", status, update_modified=update_modified)


def _get_print_qty_field():
    meta = frappe.get_meta("Sales Invoice Item")
    if meta.has_field("custom_print_qty"):
        return "custom_print_qty"
    if meta.has_field("custom_remaining_print_qty"):
        return "custom_remaining_print_qty"
    return None

def _update_print_qty_fields(sales_invoice_item, printed_qty):
    meta = frappe.get_meta("Sales Invoice Item")
    if meta.has_field("custom_remaining_print_qty"):
        frappe.db.set_value(
            "Sales Invoice Item",
            sales_invoice_item,
            "custom_remaining_print_qty",
            printed_qty,
            update_modified=False,
        )
    if meta.has_field("custom_print_qty"):
        frappe.db.set_value(
            "Sales Invoice Item",
            sales_invoice_item,
            "custom_print_qty",
            printed_qty,
            update_modified=False,
        )


def recompute_sticker_print_status(sales_invoice):
    if not sales_invoice:
        return
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1 or not _should_use_stickers(si):
        return
    if si.get("custom_dispatch_status") == DISPATCH_STATUS_DELIVERED:
        return

    printed_rows = frappe.db.sql(
        """
        SELECT ti.sales_invoice_item AS sales_invoice_item, SUM(ti.qty) AS printed_qty
        FROM `tabIndian Post Tracking Log` log
        JOIN `tabTracking Id Against Item` ti ON ti.parent = log.name
        WHERE log.reference_type = 'Sales Invoice'
          AND log.reference_name = %s
          AND IFNULL(log.is_cancelled, 0) = 0
        GROUP BY ti.sales_invoice_item
        """,
        sales_invoice,
        as_dict=True,
    )
    printed_map = {r.sales_invoice_item: flt(r.printed_qty) for r in printed_rows}
    print_qty_field = _get_print_qty_field()

    all_printed = True
    has_items = False
    for item in si.items or []:
        has_items = True
        printed_qty = flt(printed_map.get(item.name, 0))
        _update_print_qty_fields(item.name, printed_qty)
        if flt(item.qty or 0) > printed_qty:
            all_printed = False

    if not has_items:
        return

    if all_printed:
        _set_dispatch_status(si, DISPATCH_STATUS_PACKING_OK)
    else:
        _set_dispatch_status(si, DISPATCH_STATUS_PRINT_STICKERS)


def set_sticker_string_on_submit(doc, method=None):
    for row in doc.items or []:
        if row.get("custom_sticker_string"):
            continue
        row.custom_sticker_string = random_string(12).upper()


def set_dispatch_status_on_submit(doc, method=None):
    if doc.docstatus != 1:
        return

    status = (
        DISPATCH_STATUS_PRINT_STICKERS
        if _should_use_stickers(doc)
        else DISPATCH_STATUS_PACKING_OK
    )

    if (
        doc.custom_is_van_invoice
    ):
        status = DISPATCH_STATUS_DISPATCHED

    _set_dispatch_status(doc, status)
    _update_sales_orders_from_sales_invoice(doc)


def _create_packing_ok_slip_if_missing(si):
    existing = frappe.db.get_value("Packing OK Slip", {"sales_invoice": si.name}, "name")
    if existing:
        return existing

    pko = frappe.new_doc("Packing OK Slip")
    pko.sales_invoice = si.name
    pko.customer = si.customer
    pko.customer_name = si.customer_name or si.customer
    pko.invoice_amount = si.grand_total
    pko.mobile_no = (
        getattr(si, "contact_mobile", None)
        or getattr(si, "customer_mobile", None)
        or frappe.db.get_value("Customer", si.customer, "mobile_no")
    )
    state = frappe.db.get_value("Address", si.customer_address, "state") if si.customer_address else None
    if state:
        pko.state = state
    pko.transporter = si.transporter
    pko.transporter_name = si.transporter_name or si.transporter

    pko.insert(ignore_permissions=True)
    pko.submit()
    
    return pko.name
import frappe
import json

@frappe.whitelist()
def get_no_of_boxes(invoices):

    if isinstance(invoices, str):
        invoices = json.loads(invoices)

    if not invoices:
        return {
            "total_boxes": 0,
            "invoices": []
        }

    result = []

    total = 0

    for inv in invoices:
        boxes = frappe.db.get_value(
            "Packing OK Slip",
            {"sales_invoice": inv, "docstatus": 1},
            "no_of_boxes"
        ) or 0

        total += boxes

        si = frappe.get_doc("Sales Invoice", inv)

        result.append({
            "invoice": inv,
            "customer": si.customer,
            "boxes": boxes
        })

    return {
        "total_boxes": total,
        "invoices": result
    }
import frappe
import json

@frappe.whitelist()
def create_outward(values):

    if isinstance(values, str):
        values = json.loads(values)
    invoices = values.get("invoices", [])

    outward = frappe.new_doc("Outward")
    outward.material_handover = values.get("material_handover")
    outward.photo = values.get("photo")
    outward.no_of_boxes = values.get("total_boxes")

    for inv_name in invoices:
        # 3. append invoice
        outward.append("outward_invoices", {
            "sales_invoice": inv_name,
            "select": 1
        })
    outward.insert(ignore_permissions=True)
    outward.submit()

    return outward.name
@frappe.whitelist()
def create_outward_from_sales_invoice(sales_invoice):
    if not sales_invoice:
        frappe.throw("sales_invoice is required")
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be submitted")
    outward_name = _create_outward_if_missing(si)
    set_pending_for_delivery(si.name)
    return {"name": outward_name}


def set_pending_for_delivery(sales_invoice):
    if not sales_invoice:
        return
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        return
    if si.get("custom_dispatch_status") in (DISPATCH_STATUS_DELIVERED, DISPATCH_STATUS_DISPATCHED):
        return
    _set_dispatch_status(si, DISPATCH_STATUS_OUTWARD)


def set_dispatched(sales_invoice):
    if not sales_invoice:
        return
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        return
    if si.get("custom_dispatch_status") == DISPATCH_STATUS_DELIVERED:
        return
    _set_dispatch_status(si, DISPATCH_STATUS_DISPATCHED)


@frappe.whitelist()
def mark_sales_invoice_delivered(sales_invoice):
    if not sales_invoice:
        frappe.throw("sales_invoice is required")
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be submitted")
    _set_dispatch_status(si, DISPATCH_STATUS_DELIVERED)
    _update_sales_orders_from_sales_invoice(si)
    return {"status": DISPATCH_STATUS_DELIVERED}


def set_delivered_from_shipment(doc, method=None):
    sales_invoice = doc.get("custom_sales_invoice")
    if not sales_invoice:
        return
    try:
        mark_sales_invoice_delivered(sales_invoice)
    except Exception:
        frappe.log_error(
            title="Shipment submit: Failed to mark Sales Invoice delivered",
            message=f"Shipment: {doc.name}\nSales Invoice: {sales_invoice}\n\n{frappe.get_traceback()}",
        )


def update_sales_orders_from_shipment(doc, method=None):
    sales_invoice = doc.get("custom_sales_invoice")
    if not sales_invoice:
        return
    try:
        si = frappe.get_doc("Sales Invoice", sales_invoice)
        _set_dispatch_status(si, DISPATCH_STATUS_DISPATCHED)
        _update_sales_orders_from_sales_invoice(si)
    except Exception:
        frappe.log_error(
            title="Shipment: Failed to update Sales Order dispatch status",
            message=f"Shipment: {doc.name}\nSales Invoice: {sales_invoice}\n\n{frappe.get_traceback()}",
        )


def _cancel_and_delete(doctype, name):
    docstatus = frappe.db.get_value(doctype, name, "docstatus")
    if docstatus is None:
        return
    if docstatus == 1:
        doc = frappe.get_doc(doctype, name)
        doc.cancel()
    frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)


def cancel_related_docs_on_cancel(doc, method=None):
    if not doc or doc.doctype != "Sales Invoice":
        return

    if doc.get("items"):
        for item in doc.items:
            frappe.db.set_value(
                "Sales Invoice Item",
                item.name,
                "custom_remaining_print_qty",
                0,
                update_modified=False,
            )

    shipment_names = frappe.get_all(
        "Shipment",
        filters={"custom_sales_invoice": doc.name},
        pluck="name",
    )
    for name in shipment_names:
        _cancel_and_delete("Shipment", name)

    lr_names = frappe.get_all(
        "Upload LR Main",
        filters={"sales_invoice": doc.name},
        pluck="name",
    )
    for name in lr_names:
        _cancel_and_delete("Upload LR Main", name)

    log_names = frappe.get_all(
        "Indian Post Tracking Log",
        filters={"reference_type": "Sales Invoice", "reference_name": doc.name},
        pluck="name",
    )
    for name in log_names:
        _cancel_and_delete("Indian Post Tracking Log", name)

    _set_dispatch_status(doc, DISPATCH_STATUS_INVOICED, update_modified=False)
    _update_sales_orders_from_sales_invoice(doc)


def _update_sales_orders_from_sales_invoice(si):
    if not si:
        return
    sales_orders = {row.get("sales_order") for row in (si.items or []) if row.get("sales_order")}
    for sales_order_name in sales_orders:
        update_dispatch_status_for_sales_order(sales_order_name)


def validate_sales_invoice_workflow_transition(doc, method=None):
    if not doc or doc.doctype != "Sales Invoice":
        return
    if doc.is_new():
        return
    current_state = doc.get("workflow_state")
    if not current_state:
        return
    previous_state = doc.get_db_value("workflow_state")
    if not previous_state or previous_state == current_state:
        return

    transition_checks = {
        ("Invoiced", "Packing Ok"): _require_packing_ok_slip,
        ("Packing Ok", "Outward"): _require_outward,
        ("Outward", "LR Upload"): _require_lr_upload,
        ("LR Upload", "Dispatched"): _require_shipment,
        ("Dispatched", "Delivered"): _require_shipment_submitted,
    }

    check = transition_checks.get((previous_state, current_state))
    if check:
        check(doc)


def _require_packing_ok_slip(si):
    existing = frappe.db.get_value("Packing OK Slip", {"sales_invoice": si.name}, "name")
    if not existing:
        frappe.throw("Please create Packing OK Slip before moving to Packing Ok.")


def _require_outward(si):
    existing = frappe.db.get_value(
        "Outward Invoices",
        {"sales_invoice": si.name},
        "parent",
    )
    if not existing:
        frappe.throw("Please create Outward before moving to Outward.")


def _require_lr_upload(si):
    existing = frappe.db.get_value("Upload LR Main", {"sales_invoice": si.name}, "name")
    if not existing:
        frappe.throw("Please create Upload LR Main before moving to LR Upload.")


def _require_shipment(si):
    existing = frappe.db.get_value("Shipment", {"custom_sales_invoice": si.name}, "name")
    if not existing:
        frappe.throw("Please create Shipment before moving to Dispatched.")


def _require_shipment_submitted(si):
    existing = frappe.db.get_value(
        "Shipment",
        {"custom_sales_invoice": si.name, "docstatus": 1},
        "name",
    )
    if not existing:
        frappe.throw("Please submit Shipment before moving to Delivered.")

@frappe.whitelist()
def make_shipment_from_sales_invoice(sales_invoice: str):
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be Submitted.")

    shipment = frappe.new_doc("Shipment")
    meta = frappe.get_meta("Shipment")

    shipment.pickup_company = si.company
    shipment.delivery_customer = si.customer
    shipment.pickup_date = nowdate()
    shipment.value_of_goods = si.grand_total
    shipment.delivery_contact_name = si.contact_person
    shipment.pickup_contact_person = frappe.db.get_value("Portal User",{"parent":si.customer}, "user")
    shipment.pickup_address_name = si.company_address
    shipment.delivery_address_name = si.shipping_address_name
    shipment.custom_sales_invoice = si.name
    shipment.custom_sales_order = si.custom_sales_order
    # total weight from SI items
    total_weight = 0.0
    for it in (si.items or []):
        total_weight += flt(it.get("total_weight"))  # change if custom field

    if total_weight <= 0:
        total_weight = 1.0

    # Parcel table (1 row)
    if meta.has_field("shipment_parcel"):
        shipment.append("shipment_parcel", {"count": 1, "weight": total_weight})

    shipment.description_of_content = f"Shipment for Sales Invoice {si.name}"
    shipment.shipment_amount= si.grand_total
    shipment.shipment_id= si.name
    shipment.carrier_service=si.transporter_name
    # ✅ return doc for "get-mapped-doc" style usage (unsaved)
    return shipment.as_dict()

from frappe.utils import cint

def indian_post_tracking_handler(doc, method=None):
    """
    Single handler for Sales Invoice:
    - on_submit: assign tracking IDs (1 per qty)
    - on_cancel: release tracking IDs back to unused
    """

    # Only for Indian Post
    if not doc.get("transporter") or doc.transporter.strip().lower() != "indian post":
        return

    TRACKING_DOCTYPE = "Indian Post Tracking ID"

    # -------------------------
    # CANCEL: RELEASE IDS
    # -------------------------
    if method == "on_cancel":
        if not doc.get("custom_tracking_id_against_item"):
            return

        for row in doc.custom_tracking_id_against_item:
            if not row.tracking_id:
                continue
            frappe.db.set_value(
                TRACKING_DOCTYPE,
                row.tracking_id,
                {"is_used": 0, "against_document": None},
                update_modified=False
            )
        return

    # -------------------------
    # SUBMIT: ASSIGN IDS
    # -------------------------
    if method == "before_submit":
        # Avoid duplicate assignment if already present
        if doc.get("custom_tracking_id_against_item"):
            return

        if not doc.get("items"):
            frappe.throw("No items found to assign tracking IDs.")

        for item in doc.items:
            qty = cint(item.qty) or 0
            if qty <= 0:
                continue

            # Assign 1 tracking id per qty
            for _ in range(qty):
                tracking_id = frappe.db.get_value(
                    TRACKING_DOCTYPE,
                    {"is_used": 0},
                    "name"
                )

                if not tracking_id:
                    frappe.throw("No unused Indian Post Tracking ID available.")

                doc.append("custom_tracking_id_against_item", {
                    "tracking_id": tracking_id,
                    "item_code": item.item_code,
                    "sales_invoice_item": item.name,
                    "qty": 1,  # optional if your child table has it
                })

                frappe.db.set_value(
                    TRACKING_DOCTYPE,
                    tracking_id,
                    {"is_used": 1, "against_document": doc.name},
                    update_modified=False
                )


import json
from frappe.utils import now_datetime, flt, cint


@frappe.whitelist()
def create_indian_post_tracking_log(
    sales_invoice,
data,
    items=None,
):
    if not sales_invoice:
        frappe.throw("sales_invoice is required")
    if isinstance(data, str):
        import json
        data = json.loads(data)
    si = frappe.get_doc("Sales Invoice", sales_invoice)

    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be submitted")

    # 🔥 CRITICAL FIX: normalize items
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            frappe.throw("Invalid items data received")

    if not isinstance(items, list):
        frappe.throw("Items must be a list")

    amount = flt(data.get("amount")) if data.get("amount") is not None else flt(getattr(si, "rounded_total", 0) or si.grand_total)

    doc = frappe.get_doc({
        "doctype": "Indian Post Tracking Log",
        "transporter": data.get("transporter") or "",
        # "tracking_id": tracking_id or "",
        "no_of_boxes": int(data.get("no_of_boxes") or 0),
        "length_cm": flt(data.get("length_cm") or 0),
        "breadth_cm": flt(data.get("breadth_cm") or 0),
        "height_cm": flt(data.get("height_cm") or 0),
        "reference_type": "Sales Invoice",
        "reference_name": si.name,
        "total_weight": data.get("weight_in_grams"),
        "customer": si.customer,
        "created_at": now_datetime(),
        "customer_address": si.shipping_address_name,
        "customer_address_display": si.shipping_address,
        "company": si.company,
        "company_address": si.company_address,
        "company_address_display": si.company_address_display,
        "is_cancelled": 0,
        "payment_status": data.get("payment_status") or "Paid",
        "estimeted_arrival_time": data.get("estimated_time_arrival") or "",
        "amount": data.get("amount"),
        "items": []
    })

    si_items = {row.name: row for row in si.items}

    for r in items:
        print_qty = cint(r.get("print_qty") or 0)
        if print_qty <= 0:
            continue
        
        si_row = r.get("sales_invoice_item")
        if si_row and si_row not in si_items:
            frappe.throw(f"Invalid Sales Invoice Item row: {si_row}")

        doc.append("items", {
            "item_code": r.get("item_code"),
            "item_name": r.get("item_name"),
            "qty": print_qty,
            "sales_invoice_item": si_row or "",
        })
    doc.total_qty = sum(flt(r.qty or 0) for r in doc.items)
    if not doc.items:
        frappe.throw("No items selected")

    doc.insert(ignore_permissions=True)
    recompute_sticker_print_status(si.name)
    _update_sales_orders_from_sales_invoice(si)

    return {"name": doc.name}


@frappe.whitelist()
def create_packing_ok_slip_dialog(sales_invoice, data):
    """
    data is dict coming from dialog
    """
    import json

    if isinstance(data, str):
        data = json.loads(data)

    si = frappe.get_doc("Sales Invoice", sales_invoice)

    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be submitted")

    # Check if already created
    existing = frappe.db.get_value(
        "Packing OK Slip",
        {"sales_invoice": si.name,"docstatus": 1},
        "name"
    )

    if existing:
        return {"name": existing, "already_exists": 1}

    # Create Packing OK Slip
    pko = frappe.new_doc("Packing OK Slip")

    pko.sales_invoice = si.name
    pko.customer = si.customer
    pko.customer_name = si.customer_name or si.customer

    # Invoice details
    pko.invoice_amount = si.grand_total

    # Customer details
    pko.mobile_no = (
        getattr(si, "contact_mobile", None)
        or getattr(si, "customer_mobile", None)
        or frappe.db.get_value("Customer", si.customer, "mobile_no")
    )
    # Dialog values
    pko.no_of_boxes = int(data.get("no_of_boxes") or 0)
    pko.transporter = data.get("transporter") or si.transporter
    pko.transporter_name = data.get("transporter_name") or si.transporter_name
    # Insert document
    pko.insert(ignore_permissions=True)
    pko.submit()
    return {"name": pko.name,"already_exists": 0}


@frappe.whitelist()
def create_lr_from_sales_invoice_dialog(sales_invoice, data):
    """
    data is dict coming from dialog
    """
    if isinstance(data, str):
        import json
        data = json.loads(data)
    si = frappe.get_doc("Sales Invoice", sales_invoice)
    if si.docstatus != 1:
        frappe.throw("Sales Invoice must be submitted")

    # ✅ reopen if already created
    existing = frappe.db.get_value("Upload LR Main", {"sales_invoice": si.name}, "name")
    if existing:
        return {"name": existing, "already_exists": 1}

    lr = frappe.new_doc("Upload LR Main")

    # Link invoice
    lr.sales_invoice = si.name
    lr.customer = si.customer
    lr.customer_name = si.customer_name or si.customer

    # Basic customer details
    lr.customer_mobile = (
        getattr(si, "contact_mobile", None)
        or getattr(si, "customer_mobile", None)
        or frappe.db.get_value("Customer", si.customer, "mobile_no")
    )
    lr.customer_address = getattr(si, "shipping_address", None) or getattr(si, "customer_address", None)

    # Dialog values -> LR fields
    lr.no_of_boxes = int(data.get("no_of_boxes") or 0)
    lr.weight_in_grams = int(data.get("weight_in_grams") or 0)
    lr.transporter=si.transporter
    lr.total_charges = flt(data.get("total_charges")) if data.get("total_charges") is not None else flt(getattr(si, "rounded_total", 0) or si.grand_total)
    lr.transporter_name = data.get("transport_name") or ""
    lr.payment_status = data.get("payment_status") or "Paid"
    lr.estimeted_arrival_time=data.get("estimated_time_arrival") or ""
    lr.customer_delivery_date=data.get("customer_delivery_date") or ""
    lr.remark=data.get("remark") or ""
    lr.tracking_id=data.get("tracking_id") or ""
    lr.lr_copy=data.get("lr_copy") or ""
    lr.total_qty=si.total_qty
    lr.insert(ignore_permissions=True)
    lr.submit()
    
    set_dispatched(si.name)
    _update_sales_orders_from_sales_invoice(si)
    return {"name": lr.name}

def set_sales_order_from_sales_invoice(doc, method=None):
    if "In Transit Warehouse Manager" in frappe.get_roles():
        doc.custom_is_van_invoice = 1
    else:
        doc.custom_is_van_invoice = 0
    if not doc.get("items"):
        return
    for item in doc.items:
        if item.sales_order:
            doc.custom_sales_order = item.sales_order
            doc.custom_sales_order_amount=flt(frappe.db.get_value("Sales Order", item.sales_order, "grand_total") or 0)
            break
            

def set_transporter_from_sales_order(doc, method=None):
    # If already set manually, don't override
    if doc.get("transporter"):
        return

    # Collect linked Sales Orders from items
    so_names = {d.sales_order for d in (doc.get("items") or []) if d.sales_order}
    if not so_names:
        return

    # If multiple SOs, take first (or you can throw an error instead)
    so_name = sorted(list(so_names))[0]

    transporter = frappe.db.get_value("Sales Order", so_name, "custom_transporter")
    if transporter:
        doc.transporter = transporter
        

from erpnext.accounts.utils import get_balance_on

def check_customer_closing_balance(doc,method):
    if not doc.customer and not doc.is_return:
        return

    # Get receivable account
    account = doc.debit_to

    if not account:
        frappe.throw("Customer receivable account not set")
    sales_order=None
    if doc.items:
        for item in doc.items:
            if item.sales_order:
                sales_order=item.sales_order
                break
    if frappe.db.get_value("Sales Order", sales_order, "custom_payment_type")=="Cash On Delivery":
        return
    
    # ✅ Get closing balance using ERPNext utility
    closing_balance = flt(get_balance_on(
        account=account,
        party_type="Customer",
        party=doc.customer,
        company=doc.company   # 🔥 IMPORTANT (multi-company safe)
    ))

    # Positive = customer owes you
    # Negative = advance available
    available_balance = abs(closing_balance) if closing_balance < 0 else 0
    tolerance = 5.0
    # Validation
    if available_balance + tolerance < flt(doc.grand_total) and frappe.session.user != "soham.pawar@shoption.in":
        frappe.throw(
            f"Insufficient balance. Available balance is {available_balance}, "
            f"Invoice amount is {doc.grand_total}. Please contact Accounts Team."
        )
        
import frappe
from frappe.utils import flt


# ----------------------------------------
# HELPER: TOTAL REFUNDED QTY (SI ITEM)
# ----------------------------------------
import frappe
from frappe.utils import flt

@frappe.whitelist()
def attach_sales_invoice(doc, method=None):
    file = frappe.attach_print(
    doctype="Sales Invoice",
    name=doc.name,
    file_name=f"{doc.name}.pdf",
    print_format="Standard"
    )

    # doc.db_set("custom_pdf", file.file_url)



# ----------------------------------------
# HELPER: TOTAL REFUNDED QTY (SI ITEM)
# ----------------------------------------
def _get_total_refunded_qty_si(si_item):
    qty = frappe.db.sql("""
        SELECT SUM(sii.qty)
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.sales_invoice_item = %s
          AND si.is_return = 1
          AND si.docstatus = 1
    """, si_item)

    return abs(flt(qty[0][0] or 0))

# ----------------------------------------
# HELPER: TOTAL REFUNDED QTY (SO ITEM)
# ----------------------------------------
def _get_total_refunded_qty_so(so_item):
    qty = frappe.db.sql("""
        SELECT SUM(sii.qty)
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.so_detail = %s
          AND si.is_return = 1
          AND si.docstatus = 1
    """, so_item)

    return abs(flt(qty[0][0] or 0))


# ----------------------------------------
# MAIN FUNCTION
# ----------------------------------------
def set_refunded_item_status(doc, method=None):
    method = method or ""

    # Only for Credit Note
    if not doc.is_return:
        return

    so_names = set()
    si_name = doc.return_against
    # ✅ SET CURRENT CREDIT NOTE STATUS
    frappe.db.set_value(
        "Sales Invoice",
        doc.name,
        "custom_dispatch_status",
        "REFUNDED",
        update_modified=False
    )
    for item in doc.items:
        frappe.db.set_value(
            "Sales Invoice Item",
            item.name,
            "custom_item_dispatch_status",
            "REFUNDED",
            update_modified=False
        )
        # ----------------------------------------
        # SALES INVOICE ITEM
        # ----------------------------------------
        if item.sales_invoice_item:

            original_qty = flt(frappe.db.get_value(
                "Sales Invoice Item", item.sales_invoice_item, "qty"
            ) or 0)

            refunded_qty = _get_total_refunded_qty_si(item.sales_invoice_item)
            # ✅ ONLY FULL REFUND
            if refunded_qty >= original_qty:
                frappe.db.set_value(
                    "Sales Invoice Item",
                    item.sales_invoice_item,
                    "custom_item_dispatch_status",
                    "REFUNDED",
                    update_modified=False
                )

        # ----------------------------------------
        # SALES ORDER ITEM
        # ----------------------------------------
        if item.so_detail:

            so_name = frappe.db.get_value("Sales Order Item", item.so_detail, "parent")
            if so_name:
                so_names.add(so_name)

            original_qty = flt(frappe.db.get_value(
                "Sales Order Item", item.so_detail, "qty"
            ) or 0)

            refunded_qty = _get_total_refunded_qty_so(item.so_detail)

            # ✅ ONLY FULL REFUND
            if refunded_qty >= original_qty:
                frappe.db.set_value(
                    "Sales Order Item",
                    item.so_detail,
                    "custom_item_status",
                    "REFUNDED",
                    update_modified=False
                )

    # ----------------------------------------
    # UPDATE MAIN SALES INVOICE
    # ----------------------------------------
    if si_name:
        _update_sales_invoice_refund_status(si_name)

    # ----------------------------------------
    # UPDATE MAIN SALES ORDER
    # ----------------------------------------
    for so_name in so_names:
        _update_sales_order_refund_status(so_name)


# ----------------------------------------
# SALES INVOICE MAIN STATUS
# ----------------------------------------
def _update_sales_invoice_refund_status(si_name):

    items = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": si_name},
        fields=["name", "qty"]
    )

    for item in items:
        refunded_qty = _get_total_refunded_qty_si(item.name)

        # ❌ If any item NOT fully refunded → STOP
        if refunded_qty < flt(item.qty):
            return

    # ✅ ALL items fully refunded
    frappe.db.set_value(
        "Sales Invoice",
        si_name,
        "custom_dispatch_status",
        "REFUNDED",
        update_modified=False
    )


# ----------------------------------------
# SALES ORDER MAIN STATUS
# ----------------------------------------
def _update_sales_order_refund_status(so_name):

    items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": so_name},
        fields=["name", "qty"]
    )

    for item in items:
        refunded_qty = _get_total_refunded_qty_so(item.name)

        # ❌ If any item NOT fully refunded → STOP
        if refunded_qty < flt(item.qty):
            return

    # ✅ ALL items fully refunded
    frappe.db.set_value(
        "Sales Order",
        so_name,
        "custom_dispatch_status",
        "REFUNDED",
        update_modified=False
    )

@frappe.whitelist()
def set_discount_from_sales_order(sales_order, current_invoice=None):
    if not sales_order:
        return {
            "discount_amount": 0,
            "apply_discount_on": "Grand Total"
        }

    so = frappe.db.get_value(
        "Sales Order",
        sales_order,
        ["discount_amount", "apply_discount_on"],
        as_dict=True
    )

    if not so:
        return {
            "discount_amount": 0,
            "apply_discount_on": "Grand Total"
        }

    return {
        "discount_amount": flt(so.discount_amount),
        "apply_discount_on": so.apply_discount_on or "Grand Total"
    }


@frappe.whitelist()
def apply_proportional_coupon_discount(doc, method=None, clear_discount_without_sales_order=False):
    if isinstance(doc, str):
        doc = frappe.get_doc(json.loads(doc))
    elif isinstance(doc, dict):
        doc = frappe.get_doc(doc)

    if (
        clear_discount_without_sales_order
        and not doc.is_return
        and not any(d.sales_order for d in doc.items or [])
    ):
        doc.discount_amount = 0
        doc.base_discount_amount = 0
        doc.additional_discount_percentage = 0
        refresh_item_gst_details(doc)
        return doc
        doc.set("advances", [])

    set_proportional_sales_order_discount(doc)
    refresh_item_gst_details(doc)
    for sales_order in sorted({d.sales_order for d in doc.items or [] if d.sales_order}):
        adjust_discount_to_match_sales_order_total(doc, sales_order)

    return doc

    # if frappe.session.user == "soham.pawar@shoption.in":
    #     return
    # if doc.is_return:
    #     return

    # if not doc.items:
    #     return

    # total_discount = 0

    # sales_orders = list({
    #     d.sales_order
    #     for d in doc.items
    #     if d.sales_order
    # })

    # for so_name in sales_orders:

    #     so_doc = frappe.get_doc("Sales Order", so_name)

    #     so_discount = flt(so_doc.discount_amount)
    #     so_grand_total = flt(so_doc.grand_total)

    #     if not so_discount or not so_grand_total:
    #         continue

    #     # Current invoice amount for this SO only
    #     current_invoice_amount = sum(
    #         flt(d.amount)
    #         for d in doc.items
    #         if d.sales_order == so_name
    #     )

    #     if current_invoice_amount <= 0:
    #         continue

    #     # Current invoice qty for this SO
    #     current_invoice_qty = sum(
    #         flt(d.qty)
    #         for d in doc.items
    #         if d.sales_order == so_name
    #     )

    #     # SO total qty
    #     so_total_qty = sum(
    #         flt(d.qty)
    #         for d in so_doc.items
    #     )

    #     # Previously invoiced qty
    #     previous_qty = frappe.db.sql("""
    #         SELECT
    #             SUM(sii.qty)
    #         FROM `tabSales Invoice Item` sii
    #         INNER JOIN `tabSales Invoice` si
    #             ON si.name = sii.parent
    #         WHERE
    #             si.docstatus = 1
    #             AND si.is_return = 0
    #             AND sii.sales_order = %s
    #             AND si.name != %s
    #     """, (
    #         so_name,
    #         doc.name or ""
    #     ))[0][0] or 0

    #     previous_qty = flt(previous_qty)

    #     # Previously used discount
    #     # Uses submitted invoices only
    #     used_discount = frappe.db.sql("""
    #         SELECT
    #             SUM(IFNULL(si.discount_amount, 0))
    #         FROM `tabSales Invoice` si
    #         WHERE
    #             si.docstatus = 1
    #             AND si.is_return = 0
    #             AND EXISTS (
    #                 SELECT 1
    #                 FROM `tabSales Invoice Item` sii
    #                 WHERE sii.parent = si.name
    #                 AND sii.sales_order = %s
    #             )
    #     """, (
    #         so_name
    #     ))[0][0] or 0

    #     used_discount = flt(used_discount)

    #     # Remaining available discount
    #     remaining_discount = max(
    #         0,
    #         round(so_discount - used_discount, 2)
    #     )

    #     # All discount already consumed
    #     if remaining_discount == 0:
    #         continue

    #     # Proportional discount
    #     proportional_discount = (
    #         current_invoice_amount / so_grand_total
    #     ) * so_discount

    #     # Detect last invoice by qty
    #     is_last_invoice = (
    #         previous_qty + current_invoice_qty
    #     ) >= (so_total_qty - 0.0001)
    #     if is_last_invoice:
    #         # Give all remaining discount
    #         proportional_discount = remaining_discount
    #     else:
    #         proportional_discount = min(
    #             proportional_discount,
    #             remaining_discount
    #         )

    #     proportional_discount = max(
    #         0,
    #         min(
    #             round(proportional_discount, 2),
    #             remaining_discount
    #         )
    #     )

    #     # Store allocated discount per item
    #     so_items = [
    #         d for d in doc.items
    #         if d.sales_order == so_name
    #     ]

    #     so_items_amount = sum(
    #         flt(d.amount)
    #         for d in so_items
    #     )

    #     for item in so_items:

    #         item_share = (
    #             flt(item.amount) / so_items_amount
    #         ) if so_items_amount else 0

    #         item.distributed_discount_amount = round(
    #             proportional_discount * item_share,
    #             2
    #         )

    #     total_discount += proportional_discount
    # doc.apply_discount_on = "Grand Total"
    # doc.discount_amount = round(total_discount, 2)

    # # Final safety
    # if doc.discount_amount < 0:
    #     doc.discount_amount = 0

def set_proportional_sales_order_discount(doc, method=None):
    if doc.is_return or not doc.get("items"):
        return

    sales_orders = sorted({d.sales_order for d in doc.items if d.sales_order})
    if not sales_orders:
        return

    original_discount = flt(doc.discount_amount)
    original_base_discount = flt(doc.base_discount_amount)
    original_additional_discount_percentage = flt(doc.additional_discount_percentage)

    doc.discount_amount = 0
    doc.base_discount_amount = 0
    doc.additional_discount_percentage = 0
    doc.calculate_taxes_and_totals()

    total_discount = 0
    found_so_discount = False
    has_distributed_discount = frappe.get_meta("Sales Invoice Item").has_field(
        "distributed_discount_amount"
    )

    for so_name in sales_orders:
        so = frappe.db.get_value(
            "Sales Order",
            so_name,
            ["discount_amount", "apply_discount_on"],
            as_dict=True,
        )
        so_discount = flt(so.discount_amount) if so else 0
        if not so_discount:
            continue
        found_so_discount = True

        current_items = [d for d in doc.items if d.sales_order == so_name]
        current_amount = sum(abs(flt(d.amount)) for d in current_items)
        if not current_amount:
            continue

        so_item_amount = frappe.db.sql(
            """
            SELECT SUM(ABS(IFNULL(amount, 0)))
            FROM `tabSales Order Item`
            WHERE parent = %s
            """,
            so_name,
        )[0][0] or 0
        so_item_amount = flt(so_item_amount)
        if not so_item_amount:
            continue

        used_discount = _get_used_sales_order_discount(so_name, doc.name)
        remaining_discount = max(so_discount - used_discount, 0)
        if not remaining_discount:
            continue

        invoice_qty = sum(abs(flt(d.qty)) for d in current_items)
        remaining_amount = max(so_item_amount - _get_billed_sales_order_amount(so_name, doc.name), 0)
        is_last_invoice = (
            _get_previously_invoiced_qty(so_name, doc.name) + invoice_qty
        ) >= (_get_sales_order_qty(so_name) - 0.0001)
        if remaining_amount:
            is_last_invoice = is_last_invoice or current_amount >= (remaining_amount - 0.0001)

        proportional_discount = so_discount * (current_amount / so_item_amount)
        allocated_discount = remaining_discount if is_last_invoice else proportional_discount
        allocated_discount = min(allocated_discount, remaining_discount, current_amount)
        allocated_discount = flt(max(allocated_discount, 0), doc.precision("discount_amount"))
        allocated_discount = min(allocated_discount, remaining_discount, so_discount)
        allocated_discount = flt(allocated_discount, doc.precision("discount_amount"))

        if has_distributed_discount:
            for item in current_items:
                item.distributed_discount_amount = flt(
                    allocated_discount * abs(flt(item.amount)) / current_amount,
                    item.precision("distributed_discount_amount"),
                )

        total_discount += allocated_discount

    if total_discount:
        doc.apply_discount_on = "Grand Total"
        doc.discount_amount = flt(total_discount, doc.precision("discount_amount"))
        doc.base_discount_amount = flt(
            doc.discount_amount * flt(doc.conversion_rate or 1),
            doc.precision("base_discount_amount"),
        )
    else:
        if found_so_discount:
            doc.discount_amount = 0
            doc.base_discount_amount = 0
        else:
            doc.discount_amount = original_discount
            doc.base_discount_amount = original_base_discount
            doc.additional_discount_percentage = original_additional_discount_percentage


def refresh_item_gst_details(doc):
    doc.calculate_taxes_and_totals()
    try:
        from india_compliance.gst_india.overrides.transaction import (
            update_gst_details,
            update_taxable_values,
        )
    except ImportError:
        return

    update_taxable_values(doc)
    update_gst_details(doc)


def _get_used_sales_order_discount(so_name, current_invoice=None):
    return flt(
        frappe.db.sql(
            """
            SELECT SUM(
                CASE
                    WHEN inv.invoice_item_amount != 0
                        THEN ABS(IFNULL(si.discount_amount, 0))
                            * ABS(IFNULL(sii.amount, 0))
                            / inv.invoice_item_amount
                    ELSE 0
                END
            )
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            INNER JOIN (
                SELECT parent, SUM(ABS(IFNULL(amount, 0))) AS invoice_item_amount
                FROM `tabSales Invoice Item`
                GROUP BY parent
            ) inv ON inv.parent = si.name
            WHERE si.docstatus = 1
              AND IFNULL(si.is_return, 0) = 0
              AND si.name != %s
              AND sii.sales_order = %s
            """,
            (current_invoice or "", so_name),
        )[0][0]
        or 0
    )


def _get_billed_sales_order_amount(so_name, current_invoice=None):
    return flt(
        frappe.db.sql(
            """
            SELECT SUM(ABS(IFNULL(sii.amount, 0)))
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1
              AND IFNULL(si.is_return, 0) = 0
              AND si.name != %s
              AND sii.sales_order = %s
            """,
            (current_invoice or "", so_name),
        )[0][0]
        or 0
    )


def _get_billed_sales_order_grand_total(so_name, current_invoice=None):
    return flt(
        frappe.db.sql(
            """
            SELECT SUM(
                CASE
                    WHEN inv.invoice_item_amount != 0
                        THEN ABS(IFNULL(si.grand_total, 0))
                            * ABS(IFNULL(so_items.sales_order_item_amount, 0))
                            / inv.invoice_item_amount
                    ELSE 0
                END
            )
            FROM `tabSales Invoice` si
            INNER JOIN (
                SELECT parent, SUM(ABS(IFNULL(amount, 0))) AS sales_order_item_amount
                FROM `tabSales Invoice Item`
                WHERE sales_order = %s
                GROUP BY parent
            ) so_items ON so_items.parent = si.name
            INNER JOIN (
                SELECT parent, SUM(ABS(IFNULL(amount, 0))) AS invoice_item_amount
                FROM `tabSales Invoice Item`
                GROUP BY parent
            ) inv ON inv.parent = si.name
            WHERE si.docstatus = 1
              AND IFNULL(si.is_return, 0) = 0
              AND si.name != %s
            """,
            (so_name, current_invoice or ""),
        )[0][0]
        or 0
    )


def _get_previously_invoiced_qty(so_name, current_invoice=None):
    return flt(
        frappe.db.sql(
            """
            SELECT SUM(ABS(IFNULL(sii.qty, 0)))
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1
              AND IFNULL(si.is_return, 0) = 0
              AND si.name != %s
              AND sii.sales_order = %s
            """,
            (current_invoice or "", so_name),
        )[0][0]
        or 0
    )


def _get_sales_order_qty(so_name):
    return flt(
        frappe.db.sql(
            """
            SELECT SUM(ABS(IFNULL(qty, 0)))
            FROM `tabSales Order Item`
            WHERE parent = %s
            """,
            so_name,
        )[0][0]
        or 0
    )


def _get_billed_sales_order_item_amount(so_item_name):
    return flt(
        frappe.db.sql(
            """
            SELECT SUM(ABS(IFNULL(sii.amount, 0)))
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1
              AND IFNULL(si.is_return, 0) = 0
              AND sii.so_detail = %s
            """,
            so_item_name,
        )[0][0]
        or 0
    )


def adjust_discount_to_match_sales_order_total(doc, so_name):
    if doc.is_return or not doc.get("items"):
        return

    if not any(d.sales_order == so_name for d in doc.items):
        return

    so_grand_total = flt(frappe.db.get_value("Sales Order", so_name, "grand_total"))
    if not so_grand_total:
        return

    used_grand_total = _get_billed_sales_order_grand_total(so_name, doc.name)
    expected_grand_total = flt(
        max(so_grand_total - used_grand_total, 0),
        doc.precision("grand_total"),
    )

    refresh_item_gst_details(doc)

    current_grand_total = flt(doc.grand_total, doc.precision("grand_total"))
    difference = flt(current_grand_total - expected_grand_total, doc.precision("discount_amount"))
    if abs(difference) <= 0.01:
        return

    max_discount = flt(
        max(flt(doc.grand_total) + flt(doc.discount_amount), 0),
        doc.precision("discount_amount"),
    )
    adjusted_discount = flt(
        min(max(flt(doc.discount_amount) + difference, 0), max_discount),
        doc.precision("discount_amount"),
    )

    doc.apply_discount_on = "Grand Total"
    doc.discount_amount = adjusted_discount
    doc.base_discount_amount = flt(
        adjusted_discount * flt(doc.conversion_rate or 1),
        doc.precision("base_discount_amount"),
    )
    refresh_item_gst_details(doc)

    remaining_difference = flt(
        flt(doc.grand_total, doc.precision("grand_total")) - expected_grand_total,
        doc.precision("discount_amount"),
    )
    if abs(remaining_difference) <= 0.01:
        return

    adjusted_discount = flt(
        min(max(flt(doc.discount_amount) + remaining_difference, 0), max_discount),
        doc.precision("discount_amount"),
    )
    doc.discount_amount = adjusted_discount
    doc.base_discount_amount = flt(
        adjusted_discount * flt(doc.conversion_rate or 1),
        doc.precision("base_discount_amount"),
    )
    refresh_item_gst_details(doc)


@frappe.whitelist()
def make_sales_invoice_from_sales_order(source_name, target_doc=None, ignore_permissions=False, args=None):
    import json

    from frappe.contacts.doctype.address.address import get_company_address
    from frappe.model.mapper import get_mapped_doc
    from frappe.model.utils import get_fetch_values
    from frappe.utils import cint

    from erpnext.accounts.party import get_party_account
    from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
    from erpnext.stock.doctype.item.item import get_item_defaults

    if args is None:
        args = {}
    if isinstance(args, str):
        args = json.loads(args)

    has_unit_price_items = frappe.db.get_value("Sales Order", source_name, "has_unit_price_items")

    def is_unit_price_row(source):
        return has_unit_price_items and source.qty == 0

    def postprocess(source, target):
        source.discount_amount = 0
        target.discount_amount = 0
        target.base_discount_amount = 0
        target.additional_discount_percentage = 0
        set_missing_values(source, target)
        if target.get("allocate_advances_automatically"):
            target.set_advances()

    def set_missing_values(source, target):
        target.flags.ignore_permissions = True
        target.run_method("set_missing_values")
        target.run_method("set_po_nos")
        target.run_method("calculate_taxes_and_totals")
        target.run_method("set_use_serial_batch_fields")

        if source.company_address:
            target.update({"company_address": source.company_address})
        else:
            target.update(get_company_address(target.company))

        if target.company_address:
            target.update(get_fetch_values("Sales Invoice", "company_address", target.company_address))

        if source.loyalty_points and source.order_type == "Shopping Cart":
            target.redeem_loyalty_points = 1

        target.debit_to = get_party_account("Customer", source.customer, source.company)

    def update_item(source, target, source_parent):
        def get_billed_qty(so_item_name):
            from frappe.query_builder.functions import Sum

            table = frappe.qb.DocType("Sales Invoice Item")
            query = (
                frappe.qb.from_(table)
                .select(Sum(table.qty).as_("qty"))
                .where((table.docstatus == 1) & (table.so_detail == so_item_name))
            )
            return query.run(pluck="qty")[0] or 0

        billed_qty = get_billed_qty(source.name)
        billed_amount = _get_billed_sales_order_item_amount(source.name)
        target.qty = (
            source.qty - billed_qty
            if (source.qty and source.billed_amt)
            else (source.qty if is_unit_price_row(source) else source.qty - source.returned_qty)
        )

        if source_parent.has_unit_price_items:
            target.amount = flt(source.amount) - billed_amount if flt(source.amount) else 0
        elif source.qty:
            is_last_item_invoice = (billed_qty + flt(target.qty)) >= (flt(source.qty) - 0.0001)
            if is_last_item_invoice:
                target.amount = flt(source.amount) - billed_amount
            else:
                target.amount = flt(source.amount) * flt(target.qty) / flt(source.qty)
        else:
            target.amount = flt(source.amount) - billed_amount

        target.amount = flt(max(target.amount, 0), target.precision("amount"))
        if target.qty:
            target.rate = flt(target.amount / flt(target.qty), target.precision("rate"))

        target.base_amount = target.amount * flt(source_parent.conversion_rate)
        target.base_rate = target.rate * flt(source_parent.conversion_rate)

        if source_parent.project:
            target.cost_center = frappe.db.get_value("Project", source_parent.project, "cost_center")
        if target.item_code:
            item = get_item_defaults(target.item_code, source_parent.company)
            item_group = get_item_group_defaults(target.item_code, source_parent.company)
            cost_center = item.get("selling_cost_center") or item_group.get("selling_cost_center")

            if cost_center:
                target.cost_center = cost_center

    def select_item(d):
        filtered_items = args.get("filtered_children", [])
        return d.name in filtered_items if filtered_items else True

    doclist = get_mapped_doc(
        "Sales Order",
        source_name,
        {
            "Sales Order": {
                "doctype": "Sales Invoice",
                "field_map": {
                    "party_account_currency": "party_account_currency",
                    "payment_terms_template": "payment_terms_template",
                },
                "field_no_map": ["payment_terms_template"],
                "validation": {"docstatus": ["=", 1]},
            },
            "Sales Order Item": {
                "doctype": "Sales Invoice Item",
                "field_map": {
                    "name": "so_detail",
                    "parent": "sales_order",
                },
                "postprocess": update_item,
                "condition": lambda doc: (
                    True
                    if is_unit_price_row(doc)
                    else (doc.qty and (doc.base_amount == 0 or abs(doc.billed_amt) < abs(doc.amount)))
                )
                and select_item(doc),
            },
            "Sales Taxes and Charges": {
                "doctype": "Sales Taxes and Charges",
                "reset_value": True,
            },
            "Sales Team": {"doctype": "Sales Team", "add_if_empty": True},
        },
        target_doc,
        postprocess,
        ignore_permissions=ignore_permissions,
    )

    automatically_fetch_payment_terms = cint(
        frappe.db.get_single_value("Accounts Settings", "automatically_fetch_payment_terms")
    )
    if automatically_fetch_payment_terms:
        doclist.set_payment_schedule()

    doclist.set("advances", [])
    set_proportional_sales_order_discount(doclist)
    refresh_item_gst_details(doclist)
    adjust_discount_to_match_sales_order_total(doclist, source_name)
    doclist.set("advances", [])
    return doclist

def cancel_cross_warehouse_sre_for_invoice(invoice_name):
    """
    Cancel Stock Reservation Entries where:
    - SO Warehouse != SI Warehouse
    - SO Item is fully delivered
    - SRE still Reserved / Partially Reserved
    """

    records = frappe.db.sql(
        """
        SELECT DISTINCT
            sre.name AS stock_reservation_entry
        FROM `tabSales Invoice Item` sii

        INNER JOIN `tabSales Invoice` si
            ON si.name = sii.parent

        INNER JOIN `tabSales Order Item` soi
            ON soi.name = sii.so_detail

        INNER JOIN `tabSales Order` so
            ON so.name = soi.parent

        INNER JOIN `tabStock Reservation Entry` sre
            ON sre.voucher_detail_no = soi.name
            AND sre.docstatus = 1
            AND sre.voucher_type = 'Sales Order'
            AND sre.status IN ('Reserved', 'Partially Reserved')

        WHERE
            si.name = %s
            AND si.docstatus = 1
            AND IFNULL(soi.warehouse, '') != IFNULL(sii.warehouse, '')
            AND soi.delivered_qty >= soi.qty
        """,
        (invoice_name,),
        as_dict=True,
    )

    for row in records:
        try:
            sre = frappe.get_doc(
                "Stock Reservation Entry",
                row.stock_reservation_entry
            )

            if sre.docstatus == 1:
                sre.flags.ignore_permissions = True
                sre.cancel()

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Failed to cancel SRE {row.stock_reservation_entry}"
            )


def sales_invoice_on_submit(doc, method=None):
    if doc.is_return:
        return

    cancel_cross_warehouse_sre_for_invoice(doc.name)


def cron_cancel_cross_warehouse_sre():

    records = frappe.db.sql(
        """
        SELECT DISTINCT
            sre.name AS stock_reservation_entry
        FROM `tabSales Order Item` soi

        INNER JOIN `tabSales Order` so
            ON so.name = soi.parent

        INNER JOIN `tabSales Invoice Item` sii
            ON sii.so_detail = soi.name

        INNER JOIN `tabSales Invoice` si
            ON si.name = sii.parent

        INNER JOIN `tabStock Reservation Entry` sre
            ON sre.voucher_detail_no = soi.name
            AND sre.docstatus = 1
            AND sre.voucher_type = 'Sales Order'
            AND sre.status IN ('Reserved', 'Partially Reserved')

        WHERE
            so.docstatus = 1
            AND si.docstatus = 1
            AND IFNULL(soi.warehouse, '') != IFNULL(sii.warehouse, '')
            AND soi.delivered_qty >= soi.qty
        """,
        as_dict=True,
    )

    for row in records:
        try:
            sre = frappe.get_doc(
                "Stock Reservation Entry",
                row.stock_reservation_entry
            )

            if sre.docstatus == 1:
                sre.flags.ignore_permissions = True
                sre.cancel()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Failed to cancel SRE {row.stock_reservation_entry}"
            )

from frappe import _
from frappe.utils import flt


def validate_return_against_paid_amount(doc, method=None):
    if not doc.is_return or not doc.return_against:
        return

    original_invoice = frappe.get_doc("Sales Invoice", doc.return_against)

    sales_orders = list({
        d.sales_order
        for d in original_invoice.items
        if d.sales_order
    })

    if not sales_orders:
        return

    total_paid = 0

    for sales_order in sales_orders:
        total_paid += flt(
            frappe.db.get_value(
                "Sales Order",
                sales_order,
                "advance_paid"
            )
        )

    credit_note_amount = abs(flt(doc.grand_total))

    if credit_note_amount > total_paid:
        frappe.throw(
           _("You can only create a Credit Note up to the amount received from the customer. Advance Received: {1}, Credit Note Amount: {0}.").format(
                frappe.bold(
                    frappe.format_value(
                        credit_note_amount,
                        {"fieldtype": "Currency"}
                    )
                ),
                frappe.bold(
                    frappe.format_value(
                        total_paid,
                        {"fieldtype": "Currency"}
                    )
                )
            ),
           title=_("Refund Amount Exceeds Payment Received")
        )