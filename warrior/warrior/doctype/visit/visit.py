# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Visit(Document):
	def before_save(self):
		self.set_marketplace_from_customer()
	def set_marketplace_from_customer(self):

		customer_id = self.customer

		if not customer_id:
			self.marketplace = None
			return

		# Primary address from Customer
		address_name = frappe.db.get_value(
			"Customer",
			customer_id,
			"customer_primary_address"
		)

		# Fallback: latest Shipping Address via Dynamic Link (FIXED)
		if not address_name:
			res = frappe.db.sql(
				"""
				SELECT dl.parent
				FROM `tabDynamic Link` dl
				JOIN `tabAddress` a ON a.name = dl.parent
				WHERE dl.link_doctype = 'Customer'
				AND dl.link_name = %s
				AND a.address_type = 'Shipping'
				ORDER BY a.modified DESC
				LIMIT 1
				""",
				customer_id
			)

			address_name = res[0][0] if res else None

		# Get city
		city = frappe.db.get_value(
			"Address",
			address_name,
			"city"
		) if address_name else None
		self.marketplace=city or None
