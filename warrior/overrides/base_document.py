import frappe
from frappe.model.base_document import BaseDocument

_original_validate = BaseDocument._validate_update_after_submit


def custom_validate_update_after_submit(self):
    """
    Allow updating payment_schedule.due_date after submit
    ONLY for Purchase Order
    AND ONLY when explicitly allowed via flag
    """

    # ✅ Allow only when flag is set
    if (
        self.doctype == "Purchase Order"
        and frappe.flags.allow_po_payment_schedule_update
    ):
        return

    # ❌ Default ERPNext behavior for everything else
    _original_validate(self)


BaseDocument._validate_update_after_submit = custom_validate_update_after_submit
