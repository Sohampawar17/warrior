import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, now_datetime, get_datetime, add_to_date
from erpnext.selling.doctype.sales_order.sales_order import make_material_request
import json
from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import (
			create_stock_reservation_entries_for_so_items as create_stock_reservation_entries,
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

def _get_paid_amount_for_so(so_name: str) -> float:
    paid_amount = frappe.db.sql(
        """
        SELECT SUM(per.allocated_amount)
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Order'
          AND per.reference_name = %s
          AND pe.docstatus = 1
        """,
        so_name,
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
        so_name,
    )[0][0]
    paid_amount = flt(paid_amount or 0) + flt(je_paid_amount or 0)
    return flt(paid_amount or 0)


def _get_reserved_qty_for_so_item(sales_order, sales_order_item):
    return flt(
        frappe.db.sql(
            """
            SELECT IFNULL(SUM(IFNULL(sre.reserved_qty, 0)), 0)
            FROM `tabStock Reservation Entry` sre
            WHERE
                sre.voucher_type = 'Sales Order'
                AND sre.voucher_no = %s
                AND sre.voucher_detail_no = %s
                AND sre.docstatus = 1
            """,
            (sales_order, sales_order_item),
        )[0][0] or 0
    )


def cancel_reservation_for_so(so):
    so.flags.ignore_permissions = True
    so.flags.ignore_validate_update_after_submit = True

    so.cancel_stock_reservation_entries(notify=False)
    so.set("reserve_stock", 0)
    for d in so.items:
        d.set("reserve_stock", 0)

    so.save()
    frappe.db.commit()


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


def should_reserve_for_so(so) -> bool:
    tolerance = 1  # ₹1 tolerance

    customer_group = (
        so.customer_group
        or frappe.db.get_value("Customer", so.customer, "customer_group")
        or ""
    ).strip().lower()

    paid_amount = flt(_get_paid_amount_for_so(so.name))
    so_total = flt(so.rounded_total or so.grand_total or 0)

    payment_type = (
        getattr(so, "custom_payment_type", None) or ""
    ).strip().lower()

    pending_amount = so_total - paid_amount
    is_fully_paid = pending_amount <= tolerance and so_total > 0

    if customer_group == "farmer":
        if payment_type == "full payment":
            return is_fully_paid

        # Advance payment / COD Farmer
        return paid_amount > 0

    if customer_group == "dealer":
        return is_fully_paid

    return False


def update_dispatch_status_for_sales_order(sales_order_name):
    so = frappe.get_doc("Sales Order", sales_order_name)
    if _is_terminal_dispatch_status(so.get("custom_dispatch_status")):
        return

    status = _get_dispatch_status(so)
    if so.get("custom_dispatch_status") != status:
        so.db_set("custom_dispatch_status", status, update_modified=False)
        

def reserve_stock_for_so(so):
    print("\n" + "=" * 100)
    print(f"RESERVATION CHECK FOR SO : {so.name}")
    print("=" * 100)

    eligible_rows = []
    eligible_items_details = []
    reserved_rows = []

    for d in so.items:
        if not d.get("warehouse"):
            print(f"SKIP {d.item_code} : No warehouse")
            continue

        req = flt(d.get("stock_qty") or d.get("qty") or 0)

        if req <= 0:
            print(f"SKIP {d.item_code} : Qty is 0")
            continue

        reserved_qty = _get_reserved_qty_for_so_item(so.name, d.name)
        remaining_qty = flt(req - reserved_qty)

        avail = flt(
            get_available_qty_to_reserve(
                item_code=d.item_code,
                warehouse=d.warehouse
            ) or 0
        )

        print(
            f"\nITEM : {d.item_code}"
            f"\nWarehouse      : {d.warehouse}"
            f"\nRequired Qty   : {req}"
            f"\nReserved Qty   : {reserved_qty}"
            f"\nRemaining Qty  : {remaining_qty}"
            f"\nAvailable Qty  : {avail}"
        )

        if remaining_qty <= 0:
            print("STATUS : Already Fully Reserved")
            reserved_rows.append(d)
            continue

        if avail >= remaining_qty:
            print("STATUS : Eligible For Reservation")

            eligible_rows.append(d)

            eligible_items_details.append({
                "sales_order_item": d.name,
                "warehouse": d.warehouse,
                "qty_to_reserve": remaining_qty / flt(d.get("conversion_factor") or 1),
                "conversion_factor": flt(d.get("conversion_factor") or 1),
            })
        else:
            print(
                f"STATUS : Not Eligible "
                f"(Need {remaining_qty}, Available {avail})"
            )

    print("\nSUMMARY")
    print(f"Eligible Rows        : {len(eligible_rows)}")
    print(f"Already Reserved     : {len(reserved_rows)}")
    print(f"Reservation Entries  : {len(eligible_items_details)}")

    rows_to_mark_reserved = {d.name for d in eligible_rows + reserved_rows}

    if not rows_to_mark_reserved:
        print(f"NO RESERVATION POSSIBLE FOR SO {so.name}")

        so.flags.ignore_permissions = True
        so.flags.ignore_validate_update_after_submit = True

        so.set("reserve_stock", 0)

        for d in so.items:
            d.set("reserve_stock", 0)

        so.save(ignore_permissions=True)

        return

    so.flags.ignore_permissions = True
    so.flags.ignore_validate_update_after_submit = True

    so.set("reserve_stock", 1)

    for d in so.items:
        d.set("reserve_stock", 1 if d.name in rows_to_mark_reserved else 0)

    so.save(ignore_permissions=True)

    print(f"SO Reserve Stock Updated : {so.reserve_stock}")

    if not eligible_items_details:
        print("NO NEW STOCK RESERVATION ENTRY REQUIRED")
        return

    try:
        print(
            f"CREATING {len(eligible_items_details)} "
            f"STOCK RESERVATION ENTRIES"
        )

        create_stock_reservation_entries(
            sales_order=so,
            items_details=eligible_items_details,
            notify=False,
        )

        frappe.db.commit()

        print(f"SUCCESS : Reservation Entries Created For {so.name}")

    except Exception:
        print(f"ERROR : Reservation Failed For {so.name}")
        print(frappe.get_traceback())

        frappe.log_error(
            frappe.get_traceback(),
            f"Stock reservation error for Sales Order {so.name}",
        )

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


