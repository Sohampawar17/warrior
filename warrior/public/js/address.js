frappe.ui.form.on("Address", {

    refresh(frm) {
        // ✅ Apply all filters on load
        set_filters(frm);
    },

    state(frm) {
        frm.set_value("custom_district", "");
        frm.set_value("custom_tahshil", "");
        frm.set_value("city", "");

        set_filters(frm);
    },

    custom_district(frm) {
        frm.set_value("custom_tahshil", "");
        frm.set_value("city", "");

        set_filters(frm);
    },

    custom_tahshil(frm) {
        frm.set_value("city", "");

        set_filters(frm);
    }
});


// 🔥 Common function (BEST PRACTICE)
function set_filters(frm) {

    // ✅ District filter
    frm.set_query("custom_district", function () {
        return {
            filters: {
                state: frm.doc.state || ""
            }
        };
    });

    // ✅ Tehsil filter
    frm.set_query("custom_tahshil", function () {
        return {
            filters: {
                district: frm.doc.custom_district || ""
            }
        };
    });

    // ✅ Marketplace filter
    frm.set_query("city", function () {
        return {
            filters: {
                tahshil: frm.doc.custom_tahshil || ""
            }
        };
    });
}