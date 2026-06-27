import frappe

def override_payment_schedule(doc, method=None):
    """
    Override ERPNext payment schedule validations
    """
    if not doc.get("payment_schedule"):
        return

    # Disable duplicate due date validation
    frappe.flags.ignore_duplicate_payment_schedule = True

    # Disable discount date vs due date validation
    for row in doc.payment_schedule:
        row.discount_date = None
        
# working 
# import frappe
# from frappe.utils import add_days, getdate

# def force_payment_schedule_dates(doc, method=None):

#     if not doc.payment_schedule:
#         return

#     txn_date = getdate(doc.transaction_date)

#     for row in doc.payment_schedule:

#         # NEVER touch PI / LR controlled rows
#         if row.payment_term in (
#             "Some 10% Against PI",
#             "Some 10% Against Dispatch LR",
#             "Some 10% Against GRN",
#             "Some 60% Credit Of Days"
#         ):
#             continue

#         # Fix only ERPNext auto-filled junk
#         if not row.due_date or getdate(row.due_date) == txn_date:

#             try:
#                 credit_days = int(row.credit_days or 0)
#             except Exception:
#                 credit_days = 0

#             row.due_date = add_days(txn_date, credit_days)

#     doc.flags.ignore_validate = True
#     doc.flags.ignore_on_update = True


import frappe
from frappe.utils import getdate

def force_payment_schedule_dates(doc, method=None):
    if not doc.payment_schedule:
        return

    txn_date = getdate(doc.transaction_date)

    # Only control FIRST ROW
    first_row = doc.payment_schedule[0]

    # Force due date = transaction date
    first_row.due_date = txn_date

    # Clean safety
    first_row.credit_days = 0
    first_row.credit_months = 0

    doc.flags.ignore_validate = True
    doc.flags.ignore_on_update = True
