# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.pdf import get_pdf
from frappe import get_print

class IndianPostTrackingLog(Document):

	# def before_save(self):
	# 	html = get_print(
	# 		self.doctype,
	# 		self.name,
	# 		print_format="indian post format",  # 👈 your format name
	# 		doc=self
	# 	)

	# 	# 🔥 Convert to PDF
	# 	pdf = get_pdf(html)

	# 	# 🔥 Attach to document
	# 	file_doc = frappe.get_doc({
	# 		"doctype": "File",
	# 		"file_name": f"{self.name}.pdf",
	# 		"attached_to_doctype": self.doctype,
	# 		"attached_to_name": self.name,
	# 		"content": pdf,
	# 		"is_private": 0
	# 	})

	# 	file_doc.save(ignore_permissions=True)

	def before_insert(self):
		if self.reference_type != "Sales Invoice" or not self.reference_name:
			return
		sales_order=frappe.db.get_value("Sales Invoice Item", {"parent": self.reference_name}, "sales_order")
		if sales_order:
			self.sales_order = sales_order
		if self.reference_name:
			# 🔹 Step 1: Get existing value
			existing = frappe.db.get_value(
				"Sales Invoice",
				self.reference_name,
				"custom_no_of_boxes"
			) or 0

			# 🔹 Step 2: Add current value
			new_total = existing + (self.no_of_boxes or 0)

			# 🔹 Step 3: Update back to Sales Invoice
			frappe.db.set_value(
				"Sales Invoice",
				self.reference_name,
				"custom_no_of_boxes",
				new_total
			)
		TRACKING_DOCTYPE = "Indian Post Tracking ID"
		if not self.tracking_id:
			tracking_id = frappe.db.get_value(
					TRACKING_DOCTYPE,
					{"is_used": 0},
					"name"
				)

			if not tracking_id:
				frappe.throw("No unused Indian Post Tracking ID available.")
			self.tracking_id = tracking_id
			frappe.db.set_value(
					TRACKING_DOCTYPE,
					tracking_id,
					{"is_used": 1, "against_document": self.reference_name},
					update_modified=False
				)

	def on_update(self):
		if self.reference_type != "Sales Invoice" or not self.reference_name:
			return
		from warrior.public.sales_invoice_hooks import recompute_sticker_print_status
		recompute_sticker_print_status(self.reference_name)
		self._update_sales_orders()

	def on_trash(self):
		TRACKING_DOCTYPE = "Indian Post Tracking ID"
		tracking_id = self.tracking_id
		frappe.db.set_value(
				TRACKING_DOCTYPE,
				tracking_id,
				{"is_used": 0, "against_document": None},
				update_modified=False
			)
		if self.reference_type != "Sales Invoice" or not self.reference_name:
			return
		from warrior.public.sales_invoice_hooks import recompute_sticker_print_status
		recompute_sticker_print_status(self.reference_name)
		self._update_sales_orders()

	def _update_sales_orders(self):
		si = frappe.get_doc("Sales Invoice", self.reference_name)
		sales_orders = {row.get("sales_order") for row in (si.items or []) if row.get("sales_order")}
		if not sales_orders:
			return
		from warrior.public.sales_order import update_dispatch_status_for_sales_order
		for sales_order_name in sales_orders:
			update_dispatch_status_for_sales_order(sales_order_name)
