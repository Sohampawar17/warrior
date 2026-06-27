# Copyright (c) 2026, Abhishek Dubey
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PackingOKSlip(Document):
    
    def before_save(self):
        # Fetch Sales Invoice Details
        invoice = frappe.get_doc("Sales Invoice", self.sales_invoice)
        self.customer = invoice.customer
        self.customer_name = invoice.customer_name
        address = frappe.db.get_value("Address",invoice.shipping_address_name, ["*"], as_dict=True)
        if address:
            self.address_line_1 = address.address_line1
            self.marketplace = address.city
            self.tehsil = address.custom_tahshil
            self.district = address.custom_district
            self.state = address.state
            self.pincode = address.pincode
        self.invoice_amount = invoice.grand_total
        frappe.db.set_value(
            "Sales Invoice",
            self.sales_invoice,
            "custom_no_of_boxes",
            self.no_of_boxes
        )

    def before_submit(self):

        # Generate Dispatch ID if not exists
        if not self.dispatch_id:
            self.dispatch_id = frappe.generate_hash(length=8).upper()

        # Create Envelope
        envelope = frappe.get_doc({
            "doctype": "Envelope",
            "customer": self.customer,
            "customer_name": self.customer_name,
            "address_line_1": self.address_line_1,
            "marketplace": self.marketplace,
            "tehsil": self.tehsil,
            "district": self.district,
            "state": self.state,
            "pincode": self.pincode,
            "transporter": self.transporter,
            "transporter_name": self.transporter_name,
            "invoice_no": self.sales_invoice,
            "invoice_amount": self.invoice_amount,
            "no_of_boxes__big_font": self.no_of_boxes,
            "dispatch_id": self.dispatch_id,
            "packing_ok": self.name
        }).insert(ignore_permissions=True)

        # Create Boxes
        for i in range(1, self.no_of_boxes + 1):
            qr_value = f"{self.dispatch_id}-{i}"
            doc=frappe.get_doc({
                "doctype": "Box Pasting Sticker",
                "box_number": i,
                "sales_invoice": self.sales_invoice,
                "customer": self.customer,
                "customer_name": self.customer_name,
                "marketplace": self.marketplace,
                "tehsil": self.tehsil,
                "no_of_boxes": self.no_of_boxes,
                "invoice_amount": self.invoice_amount,
                "dispatch_id": self.dispatch_id,
                "qr_code_value": qr_value,
                "envelope": envelope.name,
                "packing_ok": self.name
            }).insert(ignore_permissions=True)
            doc.submit()
        # Update Sales Invoice Dispatch Status
        frappe.db.set_value(
            "Sales Invoice",
            self.sales_invoice,
            "custom_dispatch_status",
            "Outward"
        )
        
    def before_cancel(self):
        # Update Sales Invoice Dispatch Status on Cancel
        frappe.db.set_value(
            "Sales Invoice",
            self.sales_invoice,
            "custom_dispatch_status",
            "Packing OK"
        )
        for box in frappe.get_all("Box Pasting Sticker", filters={"sales_invoice": self.sales_invoice}):
            box_doc = frappe.get_doc("Box Pasting Sticker", box.name)
            if box_doc.docstatus == 1:  # Set to Cancelled
                box_doc.cancel()
            
        for envelope in frappe.get_all("Envelope", filters={"invoice_no": self.sales_invoice}):
            frappe.db.set_value("Envelope", envelope.name, "is_cancelled", 1)
            