import frappe
from frappe.utils import flt, getdate, nowdate
from erpnext.selling.doctype.sales_order.sales_order import make_material_request
import json
from warrior.public.service import (
    reserve_stock_for_so,
    should_reserve_for_so
)


DISPATCH_STATUS_PENDING_PAYMENT = "PENDING PAYMENT"
DISPATCH_STATUS_FULLY_PAID = "FULLY PAID"
DISPATCH_STATUS_PARTIAL_DISPATCH = "PARTIAL DISPATCH"
DISPATCH_STATUS_READY_TO_DISPATCH = "READY TO DISPATCH"
DISPATCH_STATUS_MATERIAL_SHORTAGE = "MATERIAL SHORTAGE"
    
DISPATCH_STATUS_INVOICED = "INVOICED"
DISPATCH_STATUS_PARTIALLY_INVOICED = "PARTIALLY INVOICED"
DISPATCH_STATUS_DISPATCHED = "DISPATCHED"
DISPATCH_STATUS_PARTIALLY_DISPATCHED = "PARTIALLY DISPATCHED"
DISPATCH_STATUS_DELIVERED = "DELIVERED"
DISPATCH_STATUS_PARTIALLY_AVAILABLE = "PARTIALLY AVAILABLE"
DISPATCH_STATUS_PARTIALLY_DELIVERED = "PARTIALLY DELIVERED"
DISPATCH_STATUS_REFUNDED = "REFUNDED"
DISPATCH_STATUS_CANCELLED = "CANCELLED"

TERMINAL_DISPATCH_STATUSES = {
    DISPATCH_STATUS_REFUNDED,
    DISPATCH_STATUS_CANCELLED,
}


def get_available_qty_to_reserve(item_code, warehouse):
    qty = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "reserved_stock"],
        as_dict=True
    ) or {}

    return flt(qty.get("actual_qty", 0)) - flt(qty.get("reserved_stock", 0))

def _normalize_text(value):
    return (value or "").strip().lower()


def _normalize_dispatch_status(value):
    return (value or "").strip().upper()


def _is_terminal_dispatch_status(value):
    return _normalize_dispatch_status(value) in TERMINAL_DISPATCH_STATUSES


def _should_use_indian_post(so):
    return (
        _normalize_text(getattr(so, "customer_group", None)) == "farmer"
        and _normalize_text(getattr(so, "transporter", None)) == "indian post"
    )

def create_material_request_from_so(doc, method):
    """
    Automatically create Material Request using ERPNext standard method
    only if stock is insufficient
    """

    shortage_found = False

    for item in doc.items:
        actual_qty = frappe.db.get_value(
            "Bin",
            {
                "item_code": item.item_code,
                "warehouse": item.warehouse
            },
            "actual_qty"
        ) or 0

        if flt(item.qty) > flt(actual_qty):
            shortage_found = True
            break

    if not shortage_found:
        return

    # Prevent duplicate MR
    if frappe.db.exists(
        "Material Request",
        {"sales_order": doc.name, "docstatus": ["!=", 2]}
    ):
        return

    # ✅ Call STANDARD ERPNext method
    mr = make_material_request(doc.name)

    mr.material_request_type = "Purchase"
    mr.schedule_date = doc.delivery_date
    mr.insert(ignore_permissions=True)
    mr.submit()

    frappe.msgprint(
        f"Material Request <b>{mr.name}</b> created using standard logic."
    )

@frappe.whitelist()
def has_draft_invoice(sales_order):
    exists = frappe.db.exists(
        "Sales Invoice Item",
        {
            "sales_order": sales_order,
            "docstatus": 0
        }
    )

    return {"has_draft": bool(exists)}

def get_shop_name(doc, method):
    if not doc.customer:
        doc.custom_shop_name = ""
        return

    from warrior.api_utils import get_shop_name_from_customer
    doc.custom_shop_name = get_shop_name_from_customer(doc.customer) or ""


@frappe.whitelist()
def get_so_item_stock_qty(sales_order=None, sales_order_item=None, item_code=None, warehouse=None):
    qty = frappe.db.get_value(
        "Bin",
        {"item_code": item_code, "warehouse": warehouse},
        ["actual_qty", "reserved_stock"],
        as_dict=True
    ) or {}

    actual_qty = flt(qty.get("actual_qty", 0)) - flt(qty.get("reserved_stock", 0))


    if not sales_order or not sales_order_item:
        return {
            "actual_qty": actual_qty,
            "reserved_qty": 0,
            "available_qty": actual_qty,
        }

    reserved_qty = flt(
        frappe.db.sql(
            """
            SELECT IFNULL(SUM(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)), 0)
            FROM `tabStock Reservation Entry` sre
            WHERE
                sre.voucher_type = 'Sales Order'
                AND sre.voucher_no = %s
                AND sre.voucher_detail_no = %s
                AND sre.docstatus = 1
            """,
            (sales_order, sales_order_item),
        )[0][0]
        or 0
    )

    return {
        "actual_qty": actual_qty,
        "reserved_qty": reserved_qty,
        "available_qty": flt(actual_qty - reserved_qty),
    }



def set_dispatch_status(doc, method=None):
    if _is_terminal_dispatch_status(doc.get("custom_dispatch_status")):
        return

    status = _get_dispatch_status(doc)
    if doc.get("custom_dispatch_status") != status:
        doc.custom_dispatch_status = status


def set_dispatch_status_after_submit(doc, method=None):
    update_dispatch_status_for_sales_order(doc.name)


def update_dispatch_status_for_sales_order(sales_order_name):
    so = frappe.get_doc("Sales Order", sales_order_name)
    if _is_terminal_dispatch_status(so.get("custom_dispatch_status")):
        return

    status = _get_dispatch_status(so)
    if so.get("custom_dispatch_status") != status:
        so.db_set("custom_dispatch_status", status, update_modified=False)


def update_dispatch_status_for_item_warehouses(affected_pairs):
    if not affected_pairs:
        return

    conditions = []
    params = []

    for item_code, warehouse in affected_pairs:
        conditions.append("(soi.item_code = %s and soi.warehouse = %s)")
        params.extend([item_code, warehouse])

    sales_orders = frappe.db.sql(
        f"""
        SELECT DISTINCT soi.parent
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name = soi.parent
        WHERE so.docstatus = 1
          AND so.transaction_date >= %s
          AND IFNULL(so.custom_dispatch_status, '') NOT IN %s
          AND ({' OR '.join(conditions)})
        """,
        ["2026-04-01", tuple(TERMINAL_DISPATCH_STATUSES)] + params,
    )

    for (sales_order_name,) in sales_orders:
        update_dispatch_status_for_sales_order(sales_order_name)

def _reserve_stock_fifo_for_affected_pairs(affected_pairs):
    processed_orders = set()

    for item_code, warehouse in affected_pairs:

        sales_orders = frappe.db.sql(
            """
            SELECT DISTINCT so.name
            FROM `tabSales Order` so
            INNER JOIN `tabSales Order Item` soi
                ON soi.parent = so.name
            WHERE so.docstatus = 1
              AND soi.item_code = %s
              AND soi.warehouse = %s
              AND IFNULL(so.status,'') NOT IN ('Closed','Completed')
              AND IFNULL(so.custom_dispatch_status,'') IN (
                    'FULLY PAID',
                    'PARTIALLY AVAILABLE',
                    'MATERIAL SHORTAGE',
                    'PARTIAL DISPATCH'
              )
            ORDER BY
                so.transaction_date ASC,
                so.creation ASC
            """,
            (item_code, warehouse),
            pluck="name",
        )

        for so_name in sales_orders:

            if so_name in processed_orders:
                continue

            processed_orders.add(so_name)

            try:
                so = frappe.get_doc("Sales Order", so_name)

                if should_reserve_for_so(so):
                    reserve_stock_for_so(so)

            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"FIFO Reservation Failed: {so_name}"
                )


def update_dispatch_status_from_delivery_note(doc, method=None):
    if not doc or not doc.get("items"):
        return

    sales_orders = {
        row.get("against_sales_order") or row.get("sales_order")
        for row in doc.items
        if row.get("against_sales_order") or row.get("sales_order")
    }

    for sales_order_name in sales_orders:
        update_dispatch_status_for_sales_order(sales_order_name)


def _get_dispatch_status(so):
    if so.docstatus != 1:
        return None

    total_qty = _get_sales_order_total_qty(so)
    if total_qty <= 0:
        return None

    invoiced_qty = _get_invoiced_qty_for_sales_order(so.name)
    dispatched_qty = _get_dispatched_qty_for_sales_order(so)
    has_shipment = _has_submitted_shipment_for_sales_order(so.name)

    if has_shipment:
        if invoiced_qty >= total_qty:
            return DISPATCH_STATUS_DELIVERED
        if invoiced_qty > 0:
            return DISPATCH_STATUS_PARTIALLY_DELIVERED

    if dispatched_qty >= total_qty:
        return DISPATCH_STATUS_DISPATCHED
    if dispatched_qty > 0:
        return DISPATCH_STATUS_PARTIALLY_DISPATCHED

    if invoiced_qty >= total_qty:
        return DISPATCH_STATUS_INVOICED
    if invoiced_qty > 0:
        return DISPATCH_STATUS_PARTIALLY_INVOICED

    return _get_pre_invoice_dispatch_status(so)


def _get_sales_order_total_qty(so):
    total = 0.0
    for item in so.items or []:
        total += flt(item.stock_qty or item.qty or 0)
    return total


def _get_dispatched_qty_for_sales_order(so):
    if _should_use_indian_post(so):
        return _get_dispatched_qty_from_indian_post(so.name)
    return _get_dispatched_qty_from_lr(so.name)


def _get_invoiced_qty_for_sales_order(sales_order_name):
    rows = frappe.db.sql(
        """
        SELECT SUM(COALESCE(sii.stock_qty, sii.qty))
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.sales_order = %s
          AND si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 0
        """,
        sales_order_name,
    )
    return flt(rows[0][0] or 0)


def _get_dispatched_qty_from_indian_post(sales_order_name):
    invoice_names = frappe.db.sql(
        """
        SELECT DISTINCT sii.parent
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.sales_order = %s
          AND si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 0
        """,
        sales_order_name,
    )
    invoice_names = [row[0] for row in invoice_names if row and row[0]]
    if not invoice_names:
        return 0

    rows = frappe.db.sql(
        """
        SELECT SUM(ti.qty)
        FROM `tabIndian Post Tracking Log` log
        JOIN `tabTracking Id Against Item` ti ON ti.parent = log.name
        WHERE log.reference_type = 'Sales Invoice'
          AND log.reference_name IN %(invoice_names)s
          AND IFNULL(log.is_cancelled, 0) = 0
        """,
        {"invoice_names": tuple(invoice_names)},
    )
    return flt(rows[0][0] or 0)


def _get_dispatched_qty_from_lr(sales_order_name):
    invoice_names = frappe.db.sql(
        """
        SELECT DISTINCT sii.parent
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.sales_order = %s
          AND si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 0
        """,
        sales_order_name,
    )
    invoice_names = [row[0] for row in invoice_names if row and row[0]]
    if not invoice_names:
        return 0

    rows = frappe.db.sql(
        """
        SELECT SUM(lr.total_qty)
        FROM `tabUpload LR Main` lr
        WHERE lr.sales_invoice IN %(invoice_names)s
          AND lr.docstatus = 1
        """,
        {"invoice_names": tuple(invoice_names)},
    )
    return flt(rows[0][0] or 0)


def _has_submitted_shipment_for_sales_order(sales_order_name):
    invoice_names = frappe.db.sql(
        """
        SELECT DISTINCT sii.parent
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.sales_order = %s
          AND si.docstatus = 1
          AND IFNULL(si.is_return, 0) = 0
        """,
        sales_order_name,
    )
    invoice_names = [row[0] for row in invoice_names if row and row[0]]
    if not invoice_names:
        return False

    shipment = frappe.db.get_value(
        "Shipment",
        {"custom_sales_invoice": ["in", invoice_names], "docstatus": 1},
        "name",
    )
    return bool(shipment)



def _get_pre_invoice_dispatch_status(so):
    tolerance = 1  # ₹1 tolerance
    paid_amount = flt(_get_paid_amount_for_sales_order(so.name))
    so_total = flt(so.rounded_total or so.grand_total or 0)
    pending_amount = so_total - paid_amount
    # Apply tolerance on pending
    is_fully_paid = pending_amount <= tolerance and so_total > 0
    is_partially_paid = paid_amount > 0 and pending_amount > tolerance
    payment_type = (so.custom_payment_type or "").strip().lower()
    customer_group = (so.customer_group or "").strip().lower()
    is_cod_farmer = (
        payment_type == "cash on delivery"
        and customer_group == "farmer"
    )
        # ------------------------------------------------
    # Delivery Date Check
    # ------------------------------------------------
    delivery_date = (
        getattr(so, "delivery_date", None)
        or getattr(so, "custom_delivery_date", None)
    )
    print(f"delivery date {delivery_date} and cod farmer {is_cod_farmer} and payment_type {payment_type} and customer_group {customer_group} and paid amount {paid_amount}")
    if delivery_date and getdate(delivery_date) > getdate(nowdate()):
        if is_fully_paid or (is_cod_farmer and is_partially_paid):
            return DISPATCH_STATUS_FULLY_PAID
        return DISPATCH_STATUS_PENDING_PAYMENT
    # ------------------------------------------------
    # PAYMENT VALIDATION
    # ------------------------------------------------
    if is_cod_farmer:
        # ❗ If nothing paid → Pending
        if paid_amount <= 0:
            return DISPATCH_STATUS_PENDING_PAYMENT
    else:
        # Normal customers must be fully paid
        if not is_fully_paid:
            return DISPATCH_STATUS_PENDING_PAYMENT

    # ------------------------------------------------
    # STOCK CHECK
    # ------------------------------------------------
    fully_reserved_items = 0
    available_items = 0
    total_items = len(so.items)

    for item in so.items:
        required_qty = flt(item.stock_qty or item.qty)

        reserved_qty = flt(
            frappe.db.sql("""
                SELECT IFNULL(
                    SUM(
                        IFNULL(reserved_qty,0)
                        - IFNULL(delivered_qty,0)
                    ),0
                )
                FROM `tabStock Reservation Entry`
                WHERE docstatus = 1
                AND voucher_type = 'Sales Order'
                AND voucher_no = %s
                AND voucher_detail_no = %s
            """, (so.name, item.name))[0][0]
        )

        available_qty = flt(
            get_available_qty_to_reserve(
                item.item_code,
                item.warehouse
            )
        )

        if reserved_qty >= required_qty:
            fully_reserved_items += 1

        if available_qty > 0:
            available_items += 1

    # All items reserved
    if fully_reserved_items == total_items:
        return DISPATCH_STATUS_READY_TO_DISPATCH

    # At least one fully reserved
    if fully_reserved_items > 0:
        return DISPATCH_STATUS_PARTIAL_DISPATCH

    # Stock available but not reserved
    if available_items > 0:
        return DISPATCH_STATUS_PARTIALLY_AVAILABLE

    # Nothing available
    return DISPATCH_STATUS_MATERIAL_SHORTAGE

def _get_effective_available_qty_for_so_item(sales_order_name, item):
    free_available_qty = flt(
        get_available_qty_to_reserve(item.item_code, item.warehouse) or 0
    )

    reserved_for_same_so_item = flt(
        frappe.db.sql(
            """
            SELECT IFNULL(SUM(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)), 0)
            FROM `tabStock Reservation Entry` sre
            WHERE sre.docstatus = 1
              AND sre.voucher_type = 'Sales Order'
              AND sre.voucher_no = %s
              AND sre.voucher_detail_no = %s
            """,
            (sales_order_name, item.name),
        )[0][0]
        or 0
    )

    return flt(free_available_qty + reserved_for_same_so_item)

def _get_paid_amount_for_sales_order(sales_order_name):
    paid_amount = frappe.db.sql(
        """
        SELECT SUM(per.allocated_amount)
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE pe.custom_sales_order = %s
          AND pe.docstatus = 1
        """,
        sales_order_name,
    )[0][0]
    je_paid_amount=frappe.db.sql(
        """
        SELECT SUM(per.credit)
        FROM `tabJournal Entry Account` per
        JOIN `tabJournal Entry` pe ON pe.name = per.parent
        WHERE per.reference_type = 'Sales Order'
          AND per.reference_name = %s
          AND pe.docstatus = 1 AND is_advance="Yes"
        """,
        sales_order_name,
    )[0][0]
    paid_amount = flt(paid_amount or 0) + flt(je_paid_amount or 0)
    return flt(paid_amount or 0)


def cron_update_sales_order_dispatch_status():
    sales_orders = frappe.get_all(
        "Sales Order",
        filters={
            "docstatus": 1,
            "transaction_date": [">=", "2026-04-08"],
            "custom_dispatch_status": [
                "IN",
                [   "PENDING PAYMENT",
                    "PARTIAL DISPATCH",
                    "MATERIAL SHORTAGE",
                    "PARTIALLY AVAILABLE",
                    "FULLY PAID",
                ],
            ],
        },
        pluck="name",
        limit_page_length=2000,
        order_by="transaction_date asc",
    )

    print("\n" + "=" * 120)
    print(f"FOUND {len(sales_orders)} SALES ORDERS")
    print("=" * 120)

    processed = 0
    updated = 0
    errors = 0

    for idx, so_name in enumerate(sales_orders, start=1):
        try:
            print("\n" + "-" * 120)
            print(f"[{idx}/{len(sales_orders)}] PROCESSING : {so_name}")

            so = frappe.get_doc("Sales Order", so_name)

            print(
                f"Current Status: {so.custom_dispatch_status} | "
                f"Reserve Stock: {so.reserve_stock}"
            )

            print("Running stock reservation...")
            _reserve_available_stock_for_sales_order(so)

            so.reload()

            print(
                f"After Reservation -> "
                f"Reserve Stock: {so.reserve_stock}"
            )

            new_status = _get_dispatch_status(so)

            print(f"Calculated Status: {new_status}")

            if not new_status:
                print("No status returned. Skipping.")
                continue

            if (so.custom_dispatch_status or "") != new_status:
                print(
                    f"STATUS UPDATE: "
                    f"{so.custom_dispatch_status} -> {new_status}"
                )

                frappe.db.set_value(
                    "Sales Order",
                    so.name,
                    "custom_dispatch_status",
                    new_status,
                    update_modified=False,
                )

                updated += 1

            else:
                print("Status unchanged.")

            processed += 1

        except Exception:
            errors += 1

            print(f"\nERROR IN SALES ORDER: {so_name}")
            print(frappe.get_traceback())

            frappe.log_error(
                title="Cron: Dispatch status update failed",
                message=f"Sales Order: {so_name}\n\n{frappe.get_traceback()}",
            )

    frappe.db.commit()

    print("\n" + "=" * 120)
    print("CRON COMPLETED")
    print("=" * 120)
    print(f"Processed : {processed}")
    print(f"Updated   : {updated}")
    print(f"Errors    : {errors}")
    print("=" * 120)



def _reserve_available_stock_for_sales_order(so):
    try:

        if should_reserve_for_so(so):
            reserve_stock_for_so(so)
            so.reload()
    except Exception:
        frappe.log_error(
            title="Cron: Stock reservation failed",
            message=f"Sales Order: {so.name}\n\n{frappe.get_traceback()}",
        )


@frappe.whitelist()
def make_refund_request_from_sales_order(sales_order, payload=None):
    so = frappe.get_doc("Sales Order", sales_order)

    if payload and isinstance(payload, str):
        payload = json.loads(payload)

    payload = payload or {}
    if frappe.db.exists("Refund Request", {"order_doctype": "Sales Order", "order_id": so.name, "docstatus":1}):
        frappe.throw("Refund Request already exists for this Sales Order")
    rr = frappe.new_doc("Refund Request")
    rr.order_doctype = "Sales Order"
    rr.order_id = so.name
    rr.customer = so.customer
    rr.customer_name = so.customer_name
    rr.grand_total = so.grand_total
    rr.mobile_number=so.contact_mobile
    # from dialog
    rr.requested_refund_amount = float(payload.get("requested_refund_amount") or 0)
    rr.refund_mode = payload.get("refund_mode")
    rr.refund_reason = payload.get("refund_reason")
    rr.created_on = now()
    rr.upi_id = payload.get("upi_id")
    rr.qr_code = payload.get("qr_code")
    rr.account_name = payload.get("account_name")
    rr.account_no = payload.get("account_no")
    rr.ifsc_code = str(payload.get("ifsc"))
    rr.bank_name = payload.get("bank_name")
    rr.bank_branch = payload.get("bank_branch")
    rr.chequebook_copy = payload.get("chequebook_copy")
    rr.target_order=payload.get("target_order")

    rr.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"name": rr.name}

from frappe.utils import now

@frappe.whitelist()
def make_van_transaction_from_sales_order(sales_order, payload=None):
    so = frappe.get_doc("Sales Order", sales_order)

    if payload and isinstance(payload, str):
        payload = json.loads(payload)

    payload = payload or {}

    vt = frappe.new_doc("Van Transactions")

    vt.transaction_mode = payload.get("transaction_mode", "Cash")
    vt.transaction_status = "Approved"
    vt.created_at = now()
    vt.created_by = frappe.session.user
    vt.customer = so.customer
    vt.customer_mobile_no = so.contact_mobile
    vt.customer_name = so.customer_name
    vt.customer_group = so.customer_group

    vt.sales_order = so.name
    vt.remark = payload.get("remark")
    vt.account_paid_to = payload.get("account_paid_to")
    vt.entry_type = payload.get("entry_type", "General/Cash/Throuh Van")
    vt.transaction_amount = payload.get("transaction_amount", 0)
    vt.van_payment_mode = payload.get("van_payment_mode", "CASH")
    vt.insert(ignore_permissions=True)
    vt.submit()
    return {"name": vt.name}


@frappe.whitelist()
def get_van_account_for_user():
    user = frappe.session.user

    sales_person = frappe.db.get_value(
        "Sales Person",
        {"custom_user": user},  # adjust field name
        "name"
    )

    if not sales_person:
        return ""

    return frappe.db.get_value(
        "Sales Person",
        sales_person,
        "custom_account_mapped"  # adjust field name
    )


from shoption_api.dealer.api import generate_username
import frappe


def create_user_from_customer():
    duplicate_users = frappe.db.sql("""
        SELECT user
        FROM `tabPortal User`
        WHERE IFNULL(user, '') != ''
        GROUP BY user
        HAVING COUNT(*) > 1
    """, as_dict=True)
    print(f"duplicates users {str(duplicate_users)}")
    for row in duplicate_users:

        customers = frappe.db.sql("""
            SELECT
                c.name,
                c.customer_name,
                c.mobile_no,
                c.customer_group,
                c.creation
            FROM `tabPortal User` pu
            INNER JOIN `tabCustomer` c
                ON c.name = pu.parent
            WHERE pu.user = %s
            ORDER BY c.creation ASC
        """, row.user, as_dict=True)

        if not customers:
            continue

        # First customer keeps original user
        first_customer = customers[0]

        if frappe.db.exists("User", row.user):
            user = frappe.get_doc("User", row.user)

            user.first_name = first_customer.customer_name
            user.full_name = first_customer.customer_name
            user.mobile_no = first_customer.mobile_no

            # Update role profile from first customer
            if first_customer.customer_group:
                user.role_profile_name = first_customer.customer_group

            user.save(ignore_permissions=True)

        print(f"Keeping {row.user} with {first_customer.name}")

        # Create new users for remaining customers
        for customer_row in customers[1:]:

            customer = frappe.get_doc("Customer", customer_row.name)

            mobile_no = str(customer.mobile_no or "").strip()

            if not mobile_no:
                mobile_no = frappe.generate_hash(length=10)

            final_email = f"{mobile_no}@gmail.com"

            counter = 1
            while frappe.db.exists("User", final_email):
                final_email = f"{mobile_no}_{counter}@gmail.com"
                counter += 1

            role = customer.customer_group or "Customer"

            # EXACT SAME USER CREATION LOGIC
            user = frappe.get_doc({
                "doctype": "User",
                "email": final_email,
                "first_name": customer.customer_name,
                "full_name": customer.customer_name,
                "mobile_no": customer.mobile_no,
                "send_welcome_email": 0,
                "username": generate_username(),
                "role_profile_name": role
            })

            user.flags.ignore_permissions = True
            user.new_password = frappe.generate_hash(length=10)
            user.insert(ignore_permissions=True)

            api_secret = frappe.generate_hash(length=15)
            user.api_key = frappe.generate_hash(length=15)
            user.api_secret = api_secret

            user.save(ignore_permissions=True)

            # Update Portal User mapping
            portal_user_row = frappe.db.get_value(
                "Portal User",
                {
                    "parent": customer.name,
                    "user": row.user
                },
                "name"
            )

            frappe.db.set_value(
                "Portal User",
                portal_user_row,
                "user",
                user.name,
                update_modified=False
            )

            print(
                f"Customer {customer.name}: {row.user} -> {user.name}"
            )

    frappe.db.commit()

    print("Completed")

# import frappe
# from frappe.utils import flt, nowdate


# @frappe.whitelist()
# def create_dealer_invoice_outstanding_je(submit=0):
#     invoices =frappe.get_all(
#     "Sales Invoice",
#     filters={"docstatus":1,"outstanding_amount":[">",0],"customer_group":"Dealer"},
#     fields=["name","customer", "customer_name","grand_total","outstanding_amount"]
# )

#     adjustment_account = "Sales Adjustment - SPL"
#     submit = int(submit)

#     first_si = frappe.get_doc("Sales Invoice", invoices[0]["name"])

#     je = frappe.new_doc("Journal Entry")
#     je.voucher_type = "Journal Entry"
#     je.company = first_si.company
#     je.posting_date = nowdate()
#     je.user_remark = "Dealer outstanding invoice adjustment"

#     total_amount = 0

#     for row in invoices:
#         invoice_name = row.get("name")
#         outstanding = flt(row.get("outstanding_amount"))

#         if outstanding <= 0:
#             continue

#         si = frappe.get_doc("Sales Invoice", invoice_name)

#         if si.company != first_si.company:
#             frappe.throw(f"Invoice {invoice_name} belongs to another company")

#         je.append("accounts", {
#             "account": si.debit_to,
#             "party_type": "Customer",
#             "party": si.customer,
#             "credit_in_account_currency": outstanding,
#             "reference_type": "Sales Invoice",
#             "reference_name": si.name,
#             "cost_center": si.cost_center or first_si.cost_center
#         })

#         total_amount += outstanding

#     je.append("accounts", {
#         "account": adjustment_account,
#         "debit_in_account_currency": total_amount,
#         "cost_center": first_si.cost_center
#     })

#     je.insert(ignore_permissions=True)

#     if submit:
#         je.submit()

#     return {
#         "journal_entry": je.name,
#         "total_amount": total_amount,
#         "invoice_count": len(invoices),
#         "submitted": bool(submit)
#     }


