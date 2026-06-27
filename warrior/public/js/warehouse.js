frappe.ui.form.on('Warehouse', {
    setup: function (frm) {
        set_warehouse_child_queries(frm);
    },

    refresh: function (frm) {
        set_warehouse_child_queries(frm);
    },

    onload: function (frm) {
        set_warehouse_child_queries(frm);
    },

    custom_fetch_tehsil: function (frm) {
        let districts = (frm.doc.custom_districts || [])
            .map(row => row.district)
            .filter(Boolean);

        if (!districts.length) {
            frm.clear_table('custom_tehsils');
            frm.refresh_field('custom_tehsils');
            return;
        }

        frappe.call({
            method: "warrior.public.warehouse.get_tehsils_by_districts",
            args: { districts: districts },
            callback: function (res) {
                if (!res.message) return;

                let valid_tehsils = res.message;
                let existing_rows = frm.doc.custom_tehsils || [];

                frm.doc.custom_tehsils = existing_rows.filter(row =>
                    valid_tehsils.includes(row.tehsil)
                );

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
    },

    custom_fetch_marketplaces: function (frm) {
        let tehsils = (frm.doc.custom_tehsils || [])
            .map(row => row.tehsil)
            .filter(Boolean);

        if (!tehsils.length) {
            frm.clear_table('custom_marketplaces');
            frm.refresh_field('custom_marketplaces');
            return;
        }

        frappe.call({
            method: "warrior.public.warehouse.get_marketplaces_by_tehsils",
            args: { tehsils: tehsils },
            callback: function (res) {
                if (!res.message) return;

                let valid_marketplaces = res.message;
                let existing_rows = frm.doc.custom_marketplaces || [];

                frm.doc.custom_marketplaces = existing_rows.filter(row =>
                    valid_marketplaces.includes(row.marketplace)
                );

                let current_marketplaces = frm.doc.custom_marketplaces.map(r => r.marketplace);

                valid_marketplaces.forEach(m => {
                    if (!current_marketplaces.includes(m)) {
                        let row = frm.add_child('custom_marketplaces');
                        row.marketplace = m;
                    }
                });

                frm.refresh_field('custom_marketplaces');
            }
        });
    }
});


function set_warehouse_child_queries(frm) {
    // Table MultiSelect: District
    frm.set_query("custom_districts", function (doc) {
        let states = (doc.custom_states || [])
            .map(row => row.state)
            .filter(Boolean);

        return {
            filters: {
                state: ["in", states.length ? states : [""]]
            }
        };
    });

    // Table MultiSelect: Tehsil
    frm.set_query("custom_tehsils", function (doc) {
        let districts = (doc.custom_districts || [])
            .map(row => row.district)
            .filter(Boolean);

        return {
            filters: {
                district: ["in", districts.length ? districts : [""]]
            }
        };
    });

    // Table MultiSelect: Marketplace
    frm.set_query("custom_marketplaces", function (doc) {
        let tehsils = (doc.custom_tehsils || [])
            .map(row => row.tehsil)
            .filter(Boolean);

        return {
            filters: {
                tahshil: ["in", tehsils.length ? tehsils : [""]]
            }
        };
    });
}