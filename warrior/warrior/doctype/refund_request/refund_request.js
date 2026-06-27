// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Refund Request", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("Refund Request", {
  order_id(frm) {
    if (!frm.doc.order_id || !frm.doc.order_doctype) return;
    frappe.call({
      method: "get_order_summary_for_refund",
      doc: frm.doc,
      callback: (r) => {
        if (!r.message) return;
        frm.set_value(r.message);
      }
    });
  },
  refresh(frm) {
    if (
        frm.doc.refund_mode == "Bank" &&
        frm.doc.workflow_state == "Approved by Manager"
    ) {
        frm.set_df_property("utr_number", "reqd", true);
        frm.set_df_property("company_bank_account", "reqd", true);
        frm.set_df_property("bank_transaction_id", "reqd", true);
    } else {
        frm.set_df_property("utr_number", "reqd", false);
        frm.set_df_property("company_bank_account", "reqd", false);
        frm.set_df_property("bank_transaction_id", "reqd", false);
    }
}
});