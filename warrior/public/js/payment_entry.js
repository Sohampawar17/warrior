function toggle_supplier_mandatory_fields(frm) {
	const is_supplier = frm.doc.party_type === "Supplier";
	frm.set_df_property("custom_utr_no", "reqd", is_supplier ? 1 : 0);
	frm.set_df_property("custom_attachment", "reqd", is_supplier ? 1 : 0);
}



frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		toggle_supplier_mandatory_fields(frm);
	},
	party_type(frm) {
		toggle_supplier_mandatory_fields(frm);
	},
	validate(frm) {
		toggle_supplier_mandatory_fields(frm);
		if (frm.doc.party_type === "Supplier") {
			if (!frm.doc.custom_utr_no) {
				frappe.throw(__("UTR No is mandatory for Supplier Payment Entry."));
			}
			if (!frm.doc.custom_attachment) {
				frappe.throw(__("Attachment is mandatory for Supplier Payment Entry."));
			}
		}
	},
});
