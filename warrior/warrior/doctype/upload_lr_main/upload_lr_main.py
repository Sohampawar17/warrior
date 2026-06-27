# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class UploadLRMain(Document):

	def before_save(self):
		if not self.sales_invoice:
			return
		sales_order=frappe.db.get_value("Sales Invoice Item", {"parent": self.sales_invoice}, "sales_order")
		if sales_order:
			self.sales_order = sales_order

	def on_submit(self):
		if not self.sales_invoice:
			return
		from warrior.public.sales_invoice_hooks import set_dispatched
		set_dispatched(self.sales_invoice)
		_update_sales_orders_from_invoice(self.sales_invoice)

	def on_cancel(self):
		if not self.sales_invoice:
			return
		frappe.db.set_value(
                "Sales Invoice",
                self.sales_invoice,
                "custom_dispatch_status",
                "Outward",
                update_modified=False,
            )
		_update_sales_orders_from_invoice(self.sales_invoice)


def _update_sales_orders_from_invoice(sales_invoice_name):
	if not sales_invoice_name:
		return
	si = frappe.get_doc("Sales Invoice", sales_invoice_name)
	sales_orders = {row.get("sales_order") for row in (si.items or []) if row.get("sales_order")}
	if not sales_orders:
		return
	from warrior.public.sales_order import update_dispatch_status_for_sales_order
	for sales_order_name in sales_orders:
		update_dispatch_status_for_sales_order(sales_order_name)
