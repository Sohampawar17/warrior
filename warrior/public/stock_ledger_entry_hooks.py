import frappe
from frappe.utils import flt
from warrior.public.sales_order import (
    update_dispatch_status_for_item_warehouses,
    get_available_qty_to_reserve,
    _reserve_stock_fifo_for_affected_pairs
)
from warrior.public.payment_entry_hooks import (
    reserve_stock_for_so,
    should_reserve_for_so
)


def update_dispatch_status_from_sle(doc, method=None):

    if not doc.item_code or not doc.warehouse:
        return

    # ----------------------------------------
    # Background Job
    # ----------------------------------------

    frappe.enqueue(
        "warrior.public.stock_hooks.process_sle_dispatch_update",
        queue="long",
        timeout=1200,
        item_code=doc.item_code,
        warehouse=doc.warehouse
    )


def process_sle_dispatch_update(item_code, warehouse):

    try:

        update_dispatch_status_for_item_warehouses({
            (item_code, warehouse)
        })

        _reserve_stock_for_waiting_sales_orders(
            item_code,
            warehouse
        )

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "process_sle_dispatch_update"
        )


def _reserve_stock_for_waiting_sales_orders(
    item_code,
    warehouse
):

    if not item_code or not warehouse:
        return

    available = flt(
        get_available_qty_to_reserve(
            item_code=item_code,
            warehouse=warehouse
        ) or 0
    )
    if available <= 0:
        return

    so_names = frappe.db.sql(
        """
        SELECT DISTINCT soi.parent
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so
            ON so.name = soi.parent
        WHERE soi.item_code = %s
          AND soi.warehouse = %s
          AND IFNULL(soi.reserve_stock, 0) = 0
          AND so.docstatus = 1
          AND IFNULL(so.status, '') NOT IN (
                'Closed',
                'Completed',
                'Cancelled'
          )
        """,
        (item_code, warehouse),
        pluck="parent",
    )

    for so_name in so_names:

        try:

            so = frappe.get_doc(
                "Sales Order",
                so_name
            )

            if not should_reserve_for_so(so):
                continue

            reserve_stock_for_so(so)

        except Exception:

            frappe.log_error(
                frappe.get_traceback(),
                f"Reserve Stock Failed: {so_name}"
            )

def update_dispatch_from_purchase_invoice(
    doc,
    method=None
):

    # ----------------------------------------
    # Only if stock updated
    # ----------------------------------------

    if not doc.update_stock:
        return

    affected_pairs = set()

    for row in doc.items:

        if row.item_code and row.warehouse:

            affected_pairs.add(
                (row.item_code, row.warehouse)
            )

    if not affected_pairs:
        return

    # ----------------------------------------
    # Background Queue
    # ----------------------------------------

    frappe.enqueue(
        "warrior.public.stock_ledger_entry_hooks.process_purchase_invoice_dispatch_update",
        queue="long",
        timeout=1200,
        affected_pairs=list(affected_pairs),
        job_name=f"dispatch-update-pi-{doc.name}"
    )


def process_purchase_invoice_dispatch_update(
    affected_pairs
):

    try:

        affected_pairs = [
            tuple(x)
            for x in affected_pairs
        ]

        # ----------------------------------------
        # 1. FIRST: Reserve stock FIFO
        # ----------------------------------------
        _reserve_stock_fifo_for_affected_pairs(affected_pairs)

        # ----------------------------------------
        # 2. THEN: Update dispatch status
        # ----------------------------------------
        update_dispatch_status_for_item_warehouses(
            affected_pairs
        )

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            "process_purchase_invoice_dispatch_update"
        )