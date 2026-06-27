# import frappe
# from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder

# class CustomPurchaseOrder(PurchaseOrder):

#     def _validate_update_after_submit(self):
#         """
#         Allow updating payment_schedule.due_date after submit
#         """
#         # Run default checks FIRST
#         super()._validate_update_after_submit()

#         # Now selectively allow due_date change
#         for row in self.payment_schedule:
#             row.flags.ignore_validate_update_after_submit = True
