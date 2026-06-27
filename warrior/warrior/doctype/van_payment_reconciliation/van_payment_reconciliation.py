# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate


class VanPaymentReconciliation(Document):
	def validate(self):
		self.validate_required_fields()
		self.validate_accounts()
		self.mandatory()

	def on_submit(self):
		self.create_internal_transfer_payment_entry()

	def on_cancel(self):
		if not self.payment_entry:
			return

		pe = frappe.get_doc("Payment Entry", self.payment_entry)
		if pe.docstatus == 1:
			pe.cancel()

	def validate_required_fields(self):
		missing = []
		for fieldname, label in (
			("received_bank_account", "Received Bank Account"),
			("paid_amount", "Paid Amount"),
			("posting_date", "Posting Date"),
			("utr_no", "UTR No"),
			("attachment", "Attachment"),
		):
			if not self.get(fieldname):
				missing.append(label)

		# if (self.workflow_state or "") == "Approved By Manager":
		# 	for fieldname, label in (
		# 		("company_account", "Company Account"),
		# 		("company_bank_account", "Company Bank Account"),
		# 	):
		# 		if not self.get(fieldname):
		# 			missing.append(label)

		if missing:
			frappe.throw("Mandatory fields required: {0}".format(", ".join(missing)))

		if flt(self.paid_amount) <= 0:
			frappe.throw("Paid Amount must be greater than zero")

	
	def mandatory(self):
		if self.utr_no:
			is_exists = frappe.get_all(
				self.doctype,
				filters={
					"utr_no": self.utr_no,
					"name": ["!=", self.name],
					"docstatus": ["!=", 2],
				},
			)
			if is_exists:
				frappe.throw("UTR No already exists for another Van Payment Reconciliation")

		if self.bank_transaction_id:
			is_exists = frappe.get_all(
				self.doctype,  
				filters={
					"bank_transaction_id": self.bank_transaction_id,
					"name": ["!=", self.name],
					"docstatus": ["!=", 2],
				},
			)
			if is_exists:
				frappe.throw(
					"Bank Transaction ID already exists for another Van Payment Reconciliation"
				)
   
 
 
 
 
	def validate_accounts(self):
		if self.received_bank_account == self.company_account:
			frappe.throw("Received Bank Account and Company Account cannot be same")

		for account in [self.received_bank_account, self.company_account]:
			if account and not frappe.db.exists(
				"Account",
				{
					"name": account,
					"disabled": 0,
					"is_group": 0
				}
			):
				frappe.msgprint(f"Account '{account}' is not an enabled ledger account")
		company_bank_gl_account = frappe.db.get_value("Bank Account", self.company_bank_account, "account")
		if company_bank_gl_account and company_bank_gl_account != self.company_account:
			frappe.throw(
				"Company Bank Account must be linked with Company Account {0}".format(self.company_account)
			)

		source_company = frappe.db.get_value("Account", self.received_bank_account, "company")
		target_company = frappe.db.get_value("Account", self.company_account, "company")
		if source_company and target_company and source_company != target_company:
			frappe.throw("Received Bank Account and Company Account must belong to the same company")

	def create_internal_transfer_payment_entry(self):
		if self.payment_entry:
			frappe.throw("Payment Entry already created")

		company = frappe.db.get_value("Account", self.company_account, "company")
		if not company:
			company = frappe.defaults.get_user_default("Company")

		if not company:
			frappe.throw("Company is required to create Payment Entry")

		pe = frappe.get_doc({
			"doctype": "Payment Entry",
			"payment_type": "Internal Transfer",
			"company": company,
			"posting_date": getdate(self.posting_date),
			"paid_from": self.received_bank_account,
			"paid_to": self.company_account,
			"paid_amount": self.paid_amount,
			"received_amount": self.received_amount,
			"custom_requested_amount": self.paid_amount,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"reference_no": self.utr_no,
			"reference_date": getdate(self.posting_date),
			"bank_account": self.company_bank_account,
			"custom_utr_no": self.utr_no,
			"custom_attachment": self.payment_proof,
			"custom_remark": self.remarks,
			"remarks": "Van Payment Reconciliation {0}".format(self.name),
		})

		try:
			pe.insert(ignore_permissions=True)
			pe.submit()
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title="VAN RECONCILIATION PAYMENT ENTRY ERROR",
			)
			frappe.throw("Payment Entry Failed: {0}".format(str(e)))

		frappe.db.set_value(self.doctype, self.name, "payment_entry", pe.name)

 
	@frappe.whitelist()
	def get_reference_details(self):
		user = frappe.session.user

		if not user or user == "Guest":
			frappe.throw("User not logged in")

		self.reference_warrior = user

		account = frappe.db.get_value(
			"Sales Person",
			{"custom_user": user},
			"custom_account_mapped"
		)

		if not account and not self.received_bank_account:
			frappe.throw(
				"No bank account mapped for the current user in Sales Person"
			)

		self.received_bank_account = account