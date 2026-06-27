frappe.ui.form.on("Purchase Order", {
//  setup(frm) {

//         frm.transporter_list = [];

//         frm.set_query("custom_transporter", function() {
//             return {
//                 filters: {
//                     name: ["in", frm.transporter_list?.length
//                         ? frm.transporter_list
//                         : ["__no_value__"]
//                     ]
//                 }
//             };
//         });
//     },
  refresh(frm) {
//     if (!frm.doc.supplier) return;

// frm.set_query("custom_transporter", (doc) => {
//     return {
//         filters: {
//             disabled: 0,
//             is_transporter: 1,
//             name: ["in", ["T0079"]]  // ✅ correct operator
//         }
//     };
// });
    if (frm.doc.docstatus !== 1) return;

    setTimeout(() => {
 if (
    frm.doc.workflow_state == "Pending For Inward"
) {
      frm.add_custom_button(
        __("Purchase Invoice (GRN)"),
        () => {
          frappe.model.open_mapped_doc({
            method: "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
            frm: frm,
          });
        },
        __("Create")
      );
        }
      ["Purchase Invoice", "Payment", "Purchase Receipt", "Payment Request"]
        .forEach(label => {
          frm.page.remove_inner_button(__(label), __("Create"));
        });
    }, 300);
  }
});

frappe.ui.form.on("Purchase Order", {
  onload_post_render(frm) {
    if (frm.doc.docstatus !== 1) return;

    setTimeout(() => {
      if (
    frm.doc.workflow_state == "Pending For Inward"
) {
    frm.add_custom_button(
        __("Purchase Invoice (GRN)"),
        () => {
            frappe.model.open_mapped_doc({
                method: "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
                frm: frm,
            });
        },
        __("Create")
    );
}
      ["Purchase Invoice", "Payment", "Purchase Receipt", "Payment Request"]
        .forEach(label => {
          frm.page.remove_inner_button(__(label), __("Create"));
        });
    }, 300);
  },
  // supplier(frm) {

  //   // Clear transporter
  //   frm.set_value('custom_transporter', null);

  //   if (!frm.doc.supplier) return;

  //   frappe.call({
  //     method: "warrior.public.purchase_order_hooks.get_supplier_transporters",
  //     args: {
  //       supplier: frm.doc.supplier
  //     },
  //     callback: function (r) {

  //       console.log("Server Response:", r.message);

  //       if (!r.message || !r.message.length) {
  //         console.log("No transporters returned");
  //         return;
  //       }

  //       frm.set_query("custom_transporter", function () {
  //         return {
  //           filters: {
  //             name: ["in", r.message]
  //           }
  //         };
  //       });

  //       frm.refresh_field("custom_transporter");
  //     }
  //   });
  // }


});
function load_transporters(frm) {
    frappe.call({
        method: "warrior.public.purchase_order_hooks.get_supplier_transporters",
        args: {
            supplier: frm.doc.supplier
        },
        callback: function (r) {

            frm.transporter_list = r.message || [];

            console.log("Transporters loaded:", frm.transporter_list);

            // ✅ reset invalid value
            if (!frm.transporter_list.includes(frm.doc.custom_transporter)) {
                frm.set_value("custom_transporter", null);
            }

            // 🔥 force refresh dropdown cache
            frm.refresh_field("custom_transporter");
        }
    });
}