# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


class VanTransactions(Document):
	def on_submit(self):
		if not self.created_by:
			self.created_by = frappe.session.user
		if (self.transaction_status or "").lower() == "approved":
			self.create_payment_entry()


	def create_payment_entry(self):
		if not self.sales_order:
			frappe.throw("Sales Order not found for this transaction")
		if self.payment_entry:
			frappe.throw("Payment Entry already created")

		# Ensure Sales Order is submitted
		if frappe.db.get_value("Sales Order", self.sales_order, "docstatus") == 0:
			doc = frappe.get_doc("Sales Order", self.sales_order)
			doc.submit()

		# Get Account Config
		account, currency = frappe.db.get_value(
			"Payu Setting",
			None,
			["account_for_payment_entry", "paid_to_account_currency"]
		)

		company = frappe.defaults.get_user_default("company")
		paid_from = frappe.db.get_value("Company", company, "default_receivable_account")

		if not paid_from:
			frappe.throw("Default Receivable Account not set in Company")
		# ==========================================
		# STEP 3: FETCH ONLY VALID INVOICES
		# ==========================================
		invoices = frappe.db.sql("""
			SELECT DISTINCT si.name
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii
				ON sii.parent = si.name
			WHERE
				si.docstatus = 1
				AND si.status != 'Cancelled'
				AND sii.sales_order = %s
				AND si.outstanding_amount > 0   -- ✅ IMPORTANT FIX
			ORDER BY si.posting_date ASC
		""", (self.sales_order,), as_dict=1)

		references = []
		remaining_amount = self.transaction_amount

		# ==========================================
		# STEP 4: ALLOCATE PAYMENT
		# ==========================================
		for inv in invoices:
			if remaining_amount <= 0:
				break

			latest_outstanding = frappe.db.get_value(
				"Sales Invoice",
				inv.name,
				"outstanding_amount"
			)

			if not latest_outstanding or latest_outstanding <= 0:
				continue

			allocated = min(remaining_amount, latest_outstanding)

			references.append({
				"reference_doctype": "Sales Invoice",
				"reference_name": inv.name,
				"allocated_amount": allocated
			})

			remaining_amount -= allocated

		# ==========================================
		# STEP 5: FALLBACK ONLY IF AMOUNT LEFT
		# ==========================================
		if remaining_amount > 0:
			references.append({
				"reference_doctype": "Sales Order",
				"reference_name": self.sales_order,
				"allocated_amount": remaining_amount
			})

		# ==========================================
		# STEP 6: FINAL CLEAN (CRITICAL FIX)
		# ==========================================
		valid_references = []

		for ref in references:
			if ref["reference_doctype"] == "Sales Invoice":
				outstanding = frappe.db.get_value(
					"Sales Invoice",
					ref["reference_name"],
					"outstanding_amount"
				)

				if outstanding and outstanding > 0:
					ref["allocated_amount"] = min(ref["allocated_amount"], outstanding)
					valid_references.append(ref)
			else:
				valid_references.append(ref)

		references = [r for r in valid_references if r.get("allocated_amount", 0) > 0]

		if not references:
			frappe.throw("All invoices are already fully paid. Cannot create Payment Entry.")

		# ==========================================
		# STEP 7: CREATE PAYMENT ENTRY
		# ==========================================
		pe = frappe.get_doc({
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"party_type": "Customer",
			"posting_date": getdate(self.created_at),
			"party": self.customer,
			"paid_amount": self.transaction_amount,
			"received_amount": self.transaction_amount,
			"mode_of_payment": "Cash",
			"target_exchange_rate": 1,
			"paid_from": paid_from,
			"paid_to":self.account_paid_to or  account,
			"paid_to_account_currency": currency,
			"reference_no": self.name,
			"reference_date": getdate(self.created_at),
			"custom_sales_order": self.sales_order,

			"references": references
		})

		# SAFE INSERT
		try:
			pe.insert(ignore_permissions=True)
			pe.submit()

		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title="PAYMENT ENTRY ERROR"
			)
			frappe.throw(f"Payment Entry Failed: {str(e)}")

		frappe.db.set_value(self.doctype, self.name, "payment_entry", pe.name)

