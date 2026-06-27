// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Reassignment", {
	setup(frm) {
		frm.trigger("set_open_lead_todo_user_filters");
	},

	refresh(frm) {
		frm.trigger("set_open_lead_todo_user_filters");
		frm.trigger("toggle_stage_grid");
	},

	set_open_lead_todo_user_filters(frm) {
		const open_lead_todo_user_query = () => ({
			query:
				"warrior.warrior.doctype.lead_reassignment.lead_reassignment.get_open_lead_todo_user_query",
		});

		frm.set_query("user", open_lead_todo_user_query);
		frm.set_query("lead_reassigned_to", open_lead_todo_user_query);
	},

	user(frm) {
		frm.trigger("load_stage_counts");
	},

	load_stage_counts(frm) {
		frm.clear_table("stages");
		frm.refresh_field("stages");

		if (!frm.doc.user) {
			return;
		}

		frappe.call({
			method:
				"warrior.warrior.doctype.lead_reassignment.lead_reassignment.get_stage_counts",
			args: {
				user: frm.doc.user,
			},
			callback(r) {
				(r.message || []).forEach((row) => {
					const child = frm.add_child("stages");
					child.lead_stage = row.lead_stage;
					child.lead_count = row.lead_count;
					child.select = 0;
				});
				frm.refresh_field("stages");
			},
		});
	},

	toggle_stage_grid(frm) {
		frm.fields_dict.stages.grid.toggle_enable("lead_stage", false);
		frm.fields_dict.stages.grid.toggle_enable("lead_count", false);
	},
});
