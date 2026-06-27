frappe.ui.form.on("Supplier", {
    refresh(frm) {
        if (!frm.fields_dict.custom_transporters) return;

        let grid = frm.fields_dict.custom_transporters.grid;

        if (grid && grid.get_field("transporter")) {
            grid.get_field("transporter").get_query = function () {
                return {
                    filters: {
                        disabled: 0,
                        is_transporter: 1
                    }
                };
            };
        }
    }
});