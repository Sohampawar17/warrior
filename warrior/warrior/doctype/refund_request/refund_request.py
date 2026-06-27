# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate
from warrior.public.sales_order import _get_paid_amount_for_sales_order
from shoption_api.cart.cart import orders_to_map,process_order_payments


class RefundRequest(Document):

    def validate(self):
        if frappe.db.exists("Refund Request", {"order_doctype": self.order_doctype, "order_id": self.order_id, "name": ["!=", self.name], "docstatus": 1}):
            frappe.throw("Refund Request already exists for this order")
        if self.requested_refund_amount and float(self.requested_refund_amount) < 0:
            frappe.throw("Refund amount cannot be negative")
        # ✅ auto compute paid_amount (advance received)
        self.get_order_summary_for_refund()
        # ✅ optionally block refund > paid
        if float(self.requested_refund_amount or 0) > float(self.paid_amount or 0):
            frappe.throw(f"Refund amount cannot be greater than paid amount ({self.paid_amount})")

    def on_update(self):
        """
        Auto create Journal Entry when workflow becomes Paid
        Also store approved_by / paid_by
        """
        state = (self.workflow_state or "")

        # ✅ capture who approved (when state becomes Approved)
        if state == "Approved By Manager" and not self.approved_by:
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approved_by_name", frappe.db.get_value("User", frappe.session.user, "full_name") or "")

        # ✅ Paid state: create JE only once + store paid_by
        if state == "Paid":
            if not self.paid_by:
                self.db_set("paid_by", frappe.session.user)
                self.db_set("paid_on",nowdate())
                self.db_set("paid_by_name", frappe.db.get_value("User", frappe.session.user, "full_name") or "")

            # prevent duplicates if already created
            if not self.journal_entry:
                self.create_refund_journal_entry()

    @frappe.whitelist()
    def get_order_summary_for_refund(self):
        if not self.order_doctype or not self.order_id:
            return {}

        doc = frappe.get_doc(self.order_doctype, self.order_id)

        paid = _get_paid_amount_for_sales_order(self.order_id) if self.order_doctype == "Sales Order" else 0
        self.db_set("paid_amount", paid)
        self.customer = getattr(doc, "customer", None)
        self.customer_name = getattr(doc, "customer_name", None)
        self.grand_total = float(getattr(doc, "grand_total", 0) or 0)
        self.mobile_number = getattr(doc, "contact_mobile", None)

    def create_refund_journal_entry(self):
        if self.refund_mode=="Bank":
            if not self.utr_number or not self.bank_transaction_id or not self.company_bank_account:
                frappe.throw("Bank Transaction ID, Payment Proof,Company bank Account is required for Bank Refund")
        if self.refund_mode != "Map to another order":
            rr = self
            amount = float(rr.requested_refund_amount or 0)
            if amount <= 0:
                frappe.throw("Refund amount must be > 0")

            company = rr.company or frappe.defaults.get_user_default("Company")
            if not company:
                frappe.throw("Company is required")

            if not rr.customer:
                frappe.throw("Customer is required")

            # Accounts
            advance_account = frappe.db.get_value("Company", company, "default_receivable_account")
            if not advance_account:
                frappe.throw("Default Receivable Account not set in Company")

            bank_account = frappe.db.get_value("Company", company, "default_cash_account")
            if not bank_account:
                frappe.throw("Default Cash/Bank account not set in Company")

            je = frappe.new_doc("Journal Entry")
            je.voucher_type = "Journal Entry"
            je.company = company
            je.posting_date = frappe.utils.getdate(self.created_on) or nowdate()
            je.user_remark = f"Advance Refund | SO {rr.order_id} | Refund Request {rr.name}"

            # Debit Customer (Advance/Receivable)
            je.append("accounts", {
                "account": advance_account,
                "party_type": "Customer",
                "party": rr.customer,
                "debit_in_account_currency": amount
            })

            # Credit Bank/Cash
            je.append("accounts", {
                "account": bank_account,
                "credit_in_account_currency": amount
            })

            je.insert(ignore_permissions=True)
            je.submit()
            frappe.db.set_value(
                "Sales Order",
                rr.order_id,
                "custom_dispatch_status",
                "REFUNDED",
                update_modified=True
            )
            rr.db_set("journal_entry", je.name)
        else:
            response = process_order_payments(
                self.order_id,
                "map",
                self.target_order
            )

            if not response.get("status"):
                frappe.throw(response.get("message"))

            je_name = response.get("data")

            if je_name:
                self.db_set("journal_entry", je_name)
        # ✅ save JE reference in your field
            
    def on_cancel(self):
        if self.journal_entry:
            je_doc = frappe.get_doc("Journal Entry", self.journal_entry)

            if je_doc.docstatus == 1:
                je_doc.cancel()

            self.db_set("journal_entry", None)

        # 🔥 revert SO status
        if self.order_id:
            frappe.db.set_value(
                "Sales Order",
                self.order_id,
                "custom_dispatch_status",
                "PENDING PAYMENT",
                update_modified=True
            )