frappe.ui.form.on("Material Request", {
refresh(frm) {

        if (!frm.doc.custom_supplier && !frm.doc.name) {
            frm.set_df_property("custom_supplier", "mandatory", 1);

            frm.set_df_property("items", "cannot_add_rows", true);
            frm.set_df_property("items", "hidden", 1);
        } else {
            frm.set_df_property("custom_supplier", "mandatory", 0);
            frm.set_df_property("items", "cannot_add_rows", false);
            frm.set_df_property("items", "hidden", 0);
        }
    },
  custom_supplier(frm) {
    if (!frm.doc.custom_supplier) return;
 frm.set_df_property("items", "cannot_add_rows", false);
            frm.set_df_property("items", "hidden", 0);
    // 🔹 Fetch supplier price list
    frappe.db.get_value(
      "Supplier",
      frm.doc.custom_supplier,
      "default_price_list"
    ).then(r => {
      if (r.message) {
        frm.set_value("buying_price_list", r.message.default_price_list || "");
      }
    });

    // 🔥 CLEAR OLD ITEMS (IMPORTANT)
    frm.clear_table("items");
    frm.refresh_field("items");

    // 🔹 Fetch allowed items
    frappe.call({
      method: "warrior.public.material_requests.items_by_supplier",
      args: { supplier: frm.doc.custom_supplier },
      callback(r) {

        const allowed = r.message || [];

        // ✅ Rebind query (fresh)
        frm.set_query("item_code", "items", function () {
          return {
            filters: [["Item", "name", "in", allowed]]
          };
        });

        // 🔄 Refresh grid UI
        frm.refresh_field("items");
      }
    });
  }
});

frappe.ui.form.on("Material Request Item", {
  item_code(frm, cdt, cdn) {
console.log(frm.doc.custom_supplier);
    // check parent field
    if (!frm.doc.custom_supplier) {

      frappe.msgprint("Please select the Supplier first");

      // clear the item_code user just selected
      frappe.model.set_value(cdt, cdn, "item_code", null);

      return;
    }
  }
});
frappe.ui.form.on("Material Request", {
    refresh(frm) {

        
        frm.page.remove_inner_button("Purchase Order", "Create");
        frm.page.remove_inner_button("Request for Quotation", "Create");
        frm.page.remove_inner_button("Supplier Quotation", "Create");

        if (!frm.doc.custom_supplier) return;

        frm.add_custom_button(
    __("Purchase Order"),
    () => {

        frappe.call({
            method: "warrior.public.material_requests.get_purchase_order_map",
            args: {
                source_name: frm.doc.name
            },
            callback: function(r) {

                let po = r.message;

                if (!po) return;

                // ✔ IMPORTANT: register doc in Frappe model
                let docs = frappe.model.sync(po);

                // ✔ get actual doc reference
                let doc = docs[0];

                // ✔ open form properly
                frappe.set_route("Form", doc.doctype, doc.name);
            }
        });

    },
    __("Create")
);
    }
});