frappe.ui.form.on('Material Shortage', {
	
	fetch_material_requests(frm) {
		frm.clear_table('items');
		frm.refresh_field('items');
		frm.clear_table('summery_item');
		frm.refresh_field('summery_item');
		frm.call({
			method: 'calculate_shortage',
			doc: frm.doc,
			freeze: true,
			freeze_message: 'Fetching pending Material Requests...'
		});
	}
});// Capture row BEFORE it is removed
frappe.ui.form.on('Material Shortage Summary Item', {
	before_summery_item_remove(frm, cdt, cdn) {
		frm._removed_summary_item = frappe.model.get_doc(cdt, cdn);
	}
});

// Remove ONLY related item rows
frappe.ui.form.on('Material Shortage Items', {
	items_remove(frm, cdt, cdn) {
		frm.clear_table('summery_item');
		frm.call({
			method: 'build_summary_table',
			doc: frm.doc,
			freeze: true,
			freeze_message: 'Updating summary...',
			callback() {
				frm.refresh_field('summery_item');
				frm.refresh_field('items');
			}
		});
	}
});

