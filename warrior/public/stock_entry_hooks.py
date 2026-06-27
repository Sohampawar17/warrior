import frappe
from warrior.public.sales_order import update_dispatch_status_for_item_warehouses,_reserve_stock_fifo_for_affected_pairs
from frappe.utils import flt
from india_compliance.gst_india.utils.taxes_controller import CustomTaxController

from warrior.public.ewaybill_print import get_stock_transfer_sales_rate


def set_dealer_selling_rate_for_stock_transfer(doc, method=None):
    if doc.purpose != "Material Transfer":
        return

    doc.set_missing_values()

    has_sales_rate = False

    for row in doc.items:
        if not row.item_code:
            continue

        sales_rate = get_stock_transfer_sales_rate(row.item_code)
        if not sales_rate:
            continue

        transfer_qty = flt(row.transfer_qty) or flt(row.qty)
        amount = flt(transfer_qty * sales_rate, row.precision("amount"))

        has_sales_rate = True
        row.basic_rate = sales_rate
        row.valuation_rate = sales_rate
        row.basic_amount = amount
        row.amount = amount
        row.additional_cost = 0

    if not has_sales_rate:
        return

    doc.distribute_additional_costs()
    doc.update_valuation_rate()
    _set_item_taxable_values(doc)
    _set_item_tax_amounts(doc)
    _calculate_taxes_and_totals(doc)
    doc.set_total_incoming_outgoing_value()
    doc.set_total_amount()


def _set_item_taxable_values(doc):
    for row in doc.items:
        if row.meta.has_field("taxable_value"):
            row.taxable_value = flt(row.amount, row.precision("taxable_value"))


def _set_item_tax_amounts(doc):
    tax_fields = ("igst", "cgst", "sgst", "cess")
    for row in doc.items:
        taxable_value = flt(row.get("taxable_value"))

        for tax in tax_fields:
            amount_field = f"{tax}_amount"
            rate_field = f"{tax}_rate"

            if not row.meta.has_field(amount_field):
                continue

            row.set(
                amount_field,
                flt(
                    taxable_value * flt(row.get(rate_field)) / 100,
                    row.precision(amount_field),
                ),
            )

        if row.meta.has_field("cess_non_advol_amount"):
            row.cess_non_advol_amount = flt(
                row.get("cess_non_advol_amount"),
                row.precision("cess_non_advol_amount"),
            )


def _calculate_taxes_and_totals(doc):
    if doc.doctype != "Stock Entry" and hasattr(doc, "calculate_taxes_and_totals"):
        doc.calculate_taxes_and_totals()
        return

    CustomTaxController(doc).set_taxes_and_totals()


def update_dispatch_status_from_stock_entry(doc, method=None):
    if doc.docstatus != 1:
        return

    enqueue_dispatch_update(doc)


def update_dispatch_status_from_stock_entry_cancel(doc, method=None):
    enqueue_dispatch_update(doc)

def enqueue_dispatch_update(doc):

    affected_pairs = set()

    for row in doc.items:
        if not row.item_code:
            continue

        if row.s_warehouse:
            affected_pairs.add((row.item_code, row.s_warehouse))

        if row.t_warehouse:
            affected_pairs.add((row.item_code, row.t_warehouse))

    if not affected_pairs:
        return

    frappe.enqueue(
        method=_reserve_stock_fifo_for_affected_pairs,
        queue="short",
        timeout=6000,
        affected_pairs=list(affected_pairs),
        enqueue_after_commit=True,
    )

    frappe.enqueue(
        method=update_dispatch_status_for_item_warehouses,
        queue="short",
        timeout=6000,
        affected_pairs=list(affected_pairs),
        enqueue_after_commit=True,
    )