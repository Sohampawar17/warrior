// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.ui.form.on("Van Payment Reconciliation", {
	refresh(frm) {
		if (!frm.doc.received_bank_account && !frm.doc.reference_warrior) {
			frm.call({
				method: "get_reference_details",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Fetching reference details...")
			}).then(() => {
				frm.refresh_fields([
					"reference_warrior",
					"received_bank_account"
				]);

				set_manager_approval_required_fields(frm);
			});
		} else {
			set_manager_approval_required_fields(frm);
		}
	},

	workflow_state(frm) {
		set_manager_approval_required_fields(frm);
	},

	onload(frm) {
		set_manager_approval_required_fields(frm);
	},

	validate(frm) {
		set_manager_approval_required_fields(frm);
	}
});

function set_manager_approval_required_fields(frm) {
	const is_approved =
		(frm.doc.workflow_state || "") === "Approved By Manager";

	console.log("Workflow State:", frm.doc.workflow_state);
	console.log("is_approved:", is_approved);

	// Required fields after manager approval
	[
		"company_account",
		"company_bank_account",
		"payment_proof",
		"received_amount"
	].forEach(fieldname => {
		if (frm.fields_dict[fieldname]) {
			frm.set_df_property(fieldname, "reqd", is_approved);
		}
	});

	// Fields editable only after manager approval
	[
		"received_bank_account",
		"paid_amount",
		"posting_date",
		"utr_no",
		"attachment"
	].forEach(fieldname => {
		if (frm.fields_dict[fieldname]) {
			frm.toggle_enable(fieldname, !is_approved);
		}
	});

	frm.refresh_fields([
		"company_account",
		"company_bank_account",
		"payment_proof",
		"received_amount",
		"received_bank_account",
		"posting_date",
		"utr_no",
		"attachment"
	]);
}