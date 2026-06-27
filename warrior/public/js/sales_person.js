frappe.ui.form.on('Sales Person', {

    // -------------------------
    // SETUP
    // -------------------------
    setup: function(frm) {

        // District filter
        if (frm.fields_dict.custom_districts) {
            frm.set_query("district", "custom_districts", function(doc) {
                let state = (doc.custom_filter_states || []).map(row => row.state);

                return {
                    filters: [
                        ['District', 'state', 'in', state.length ? state : [""]]
                    ]
                };
            });
        }

        // Tehsil filter
        if (frm.fields_dict.custom_tehsils) {
            frm.set_query("tehsil", "custom_tehsils", function(doc) {
                let districts = (doc.custom_districts || []).map(row => row.district);

                return {
                    filters: [
                        ['Tehsil', 'district', 'in', districts.length ? districts : [""]]
                    ]
                };
            });
        }
    },

    // -------------------------
    // STATE CHANGE
    // -------------------------
    custom_filter_state: function(frm) {
        frm.clear_table('custom_districts');
        frm.clear_table('custom_tehsils');
        frm.refresh_fields(['custom_districts', 'custom_tehsils']);
    },

    // -------------------------
    // DISTRICT CHANGE (SMART SYNC)
    // -------------------------

    custom_fetch_district:  function(frm) {

    let districts = (frm.doc.custom_filter_states || []).map(row => row.state);

    if (!districts.length) {
        frm.clear_table('custom_districts');
        frm.refresh_field('custom_districts');
        return;
    }

    frappe.call({
        method: "warrior.public.sales_person.get_districts_by_states",
        args: {
            states: districts
        },
        callback: function(res) {

            if (!res.message) return;

            let valid_districts = res.message;

            let existing_rows = frm.doc.custom_districts || [];

            // ✅ REMOVE invalid districts
            frm.doc.custom_districts = existing_rows.filter(row =>
                valid_districts.includes(row.district)
            );

            // ✅ ADD missing districts (no duplicates)
            let current_districts = frm.doc.custom_districts.map(r => r.district);

            valid_districts.forEach(d => {
                if (!current_districts.includes(d)) {
                    let row = frm.add_child('custom_districts');
                    row.district = d;
                }
            });

            frm.refresh_field('custom_districts');
        }
    });
},
    custom_fetch_tehsil: function(frm) {

    let districts = (frm.doc.custom_districts || []).map(row => row.district);

    if (!districts.length) {
        frm.clear_table('custom_tehsils');
        frm.refresh_field('custom_tehsils');
        return;
    }

    frappe.call({
        method: "warrior.public.sales_person.get_tehsils_by_districts",
        args: {
            districts: districts
        },
        callback: function(res) {

            if (!res.message) return;

            let valid_tehsils = res.message;

            let existing_rows = frm.doc.custom_tehsils || [];

            // ✅ REMOVE invalid tehsils
            frm.doc.custom_tehsils = existing_rows.filter(row =>
                valid_tehsils.includes(row.tehsil)
            );

            // ✅ ADD missing tehsils (no duplicates)
            let current_tehsils = frm.doc.custom_tehsils.map(r => r.tehsil);

            valid_tehsils.forEach(t => {
                if (!current_tehsils.includes(t)) {
                    let row = frm.add_child('custom_tehsils');
                    row.tehsil = t;
                }
            });

            frm.refresh_field('custom_tehsils');
        }
    });
}
});