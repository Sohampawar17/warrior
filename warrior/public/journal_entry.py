import frappe
from warrior.public.sales_order import update_dispatch_status_for_sales_order
from warrior.public.payment_entry_hooks import (
    reserve_stock_for_so,
    should_reserve_for_so
)

def update_order_status(doc,method):
    if doc.doctype == "Journal Entry": 
        for d in doc.accounts:
            if d.reference_type == "Sales Order" and d.is_advance =="Yes":
                update_dispatch_status_for_sales_order(d.reference_name)