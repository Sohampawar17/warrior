# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from warrior.public.sales_invoice_hooks import  _should_use_stickers,_update_sales_orders_from_sales_invoice

class Outward(Document):
	def before_submit(self):
		# Update Sales Invoice Dispatch Status
		for i in self.outward_invoices:
			if i.sales_invoice and i.select:
				si = frappe.get_doc("Sales Invoice", i.sales_invoice)
				# frappe.db.set_value(
				# 	"Sales Invoice",
				# 	i.sales_invoice,
				# 	"custom_dispatch_status",
				# 		"Dispatched"
				# )
				if si.custom_dispatch_status!= "Outward":
					i.select = 0
					continue
				if _should_use_stickers(si):
					frappe.db.set_value(
						"Sales Invoice",
						i.sales_invoice,
						"custom_dispatch_status",
							"Dispatched"
					)
					_update_sales_orders_from_sales_invoice(si)

				else:
					frappe.db.set_value(
						"Sales Invoice",
						i.sales_invoice,
						"custom_dispatch_status",
							"Upload LR Main"
					)
		
	def before_cancel(self):
		for i in self.outward_invoices:
			if i.sales_invoice:
				si = frappe.get_doc("Sales Invoice", i.sales_invoice)
				frappe.db.set_value(
					"Sales Invoice",
					i.sales_invoice,
					"custom_dispatch_status",
						"Outward"
				)
				_update_sales_orders_from_sales_invoice(si)