async function get_so_item_qty_values(frm, row) {
  if (!row.item_code || !row.warehouse) {
    return {
      actual_qty: 0,
      reserved_qty: 0
    };
  }

  const r = await frappe.call({
    method: "warrior.public.sales_order.get_so_item_stock_qty",
    args: {
      sales_order: frm && frm.doc ? frm.doc.name : null,
      sales_order_item: row.name,
      item_code: row.item_code,
      warehouse: row.warehouse
    }
  });

  const data = (r && r.message) || {};
  return {
    actual_qty: flt(data.actual_qty || 0),
    reserved_qty: flt(data.reserved_qty || 0)
  };
}

async function set_qty_check_fields(frm, cdt, cdn) {
  const row = locals[cdt] && locals[cdt][cdn];
  if (!row) return;

  const qty_data = await get_so_item_qty_values(frm, row);
  const reserve_qty = flt(qty_data.reserved_qty || 0);
  const actual_qty = flt(qty_data.actual_qty || 0);
  const available_qty = flt(actual_qty - reserve_qty);

  const updates = {
    custom_warehouse_actual_qty: actual_qty,
    custom_reserve_qty: reserve_qty,
    custom_actual_qty: actual_qty,
    custom_available_qty: available_qty
  };

  let changed = false;
  Object.keys(updates).forEach((fieldname) => {
    if (flt(row[fieldname] || 0) === flt(updates[fieldname] || 0)) return;
    row[fieldname] = updates[fieldname];
    changed = true;
  });

  if (!changed || !frm) return;

  const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
  if (grid && typeof grid.refresh_row === "function") {
    grid.refresh_row(cdn);
  } else {
    frm.refresh_field("items");
  }
}

function refresh_all_item_qty_checks(frm) {
  (frm.doc.items || []).forEach((d) => void set_qty_check_fields(frm, d.doctype, d.name));
  frm.refresh_field("items");
}
frappe.ui.form.on("Sales Order", {
  setup(frm) {
    frm.set_df_property(
      "customer_group",
      "ignore_user_permissions",
      true
    );
    frm.__qty_check_refresh_timeout = null;
  },

  items_add(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  refresh(frm) {

    refresh_all_item_qty_checks(frm);
    clearTimeout(frm.__qty_check_refresh_timeout);
    frm.__qty_check_refresh_timeout = setTimeout(() => refresh_all_item_qty_checks(frm), 500);

    if (frm.doc.docstatus !== 1) return;
    if (
      frm.doc.custom_dispatch_status === "PENDING PAYMENT" &&
      frappe.user_roles.includes("In Transit Warehouse Manager")
    ) {

      frm.add_custom_button(__("Van Payment"), () => {

        frappe.call({
          method: "warrior.public.sales_order.get_van_account_for_user",
          callback: function (r) {

            let default_account = r.message || "";

            const d = new frappe.ui.Dialog({
              title: __("Create Van Transaction"),
              size: "large",
              fields: [

                {
                  fieldtype: "Section Break",
                  label: __("Order Details")
                },

                {
                  fieldname: "sales_order",
                  fieldtype: "Data",
                  label: __("Sales Order"),
                  read_only: 1,
                  default: frm.doc.name
                },
                {
                  fieldname: "customer",
                  fieldtype: "Link",
                  options: "Customer",
                  label: __("Customer"),
                  read_only: 1,
                  default: frm.doc.customer
                },
                {
                  fieldname: "customer_name",
                  fieldtype: "Data",
                  label: __("Customer Name"),
                  read_only: 1,
                  default: frm.doc.customer_name
                },

                {
                  fieldname: "mobile_no",
                  fieldtype: "Data",
                  label: __("Mobile No"),
                  read_only: 1,
                  default: frm.doc.contact_mobile
                },

                {
                  fieldtype: "Section Break",
                  label: __("Transaction Details")
                },

                {
                  fieldname: "transaction_amount",
                  fieldtype: "Currency",
                  label: __("Amount"),
                  reqd: 1,
                  default: (frm.doc.rounded_total - frm.doc.advance_paid)
                    || (frm.doc.grand_total - frm.doc.advance_paid)
                    || 0
                },

                {
                  fieldname: "transaction_mode",
                  fieldtype: "Select",
                  label: __("Transaction Mode"),
                  options: "Cash",
                  default: "Cash",
                  reqd: 1
                },

                {
                  fieldname: "account_paid_to",
                  fieldtype: "Link",
                  label: __("Account Paid To"),
                  options: "Account",
                  default: default_account,
                  reqd: 1,
                  read_only: 1,
                },

                {
                  fieldname: "remark",
                  fieldtype: "Small Text",
                  label: __("Remark")
                }
              ],

              primary_action_label: __("Create Van Transaction"),

              primary_action(values) {

                frappe.call({
                  method: "warrior.public.sales_order.make_van_transaction_from_sales_order",
                  args: {
                    sales_order: frm.doc.name,
                    payload: values
                  },
                  freeze: true,
                  freeze_message: __("Creating Van Transaction..."),
                  callback: function (r) {

                    if (!r.message) return;

                    d.hide();

                    frappe.show_alert({
                      message: __("Van Transaction Created"),
                      indicator: "green"
                    });

                    frappe.set_route(
                      "Form",
                      "Van Transactions",
                      r.message.name
                    );
                  }
                });
              }
            });

            d.show();
          }
        });

      }, __("Create"));
    }
    if (
      frm.doc.docstatus === 1 &&
      ![
        "REFUNDED", "CANCELLED", "PARTIALLY INVOICED",
        "INVOICED", "PARTIALLY DISPATCHED",
        "DISPATCHED", "PARTIALLY DELIVERED", "DELIVERED"
      ].includes(frm.doc.custom_dispatch_status) &&
      ["Fully Paid", "Partially Paid"].includes(frm.doc.custom_payment_status)
    ) {
      frm.add_custom_button(__("Refund Request"), () => {

        const d = new frappe.ui.Dialog({
          title: __("Create Refund Request"),
          size: "large",
          fields: [

            // ---------------- Order Info ----------------
            { fieldtype: "Section Break", label: __("Order Details") },

            {
              fieldname: "order_id",
              fieldtype: "Data",
              label: __("Sales Order"),
              read_only: 1,
              default: frm.doc.name
            },
            {
              fieldname: "customer",
              fieldtype: "Link",
              options: "Customer",
              label: __("Customer"),
              read_only: 1,
              default: frm.doc.customer
            },
            {
              fieldname: "customer_name",
              fieldtype: "Data",
              label: __("Customer Name"),
              read_only: 1,
              default: frm.doc.customer_name
            },

            { fieldtype: "Column Break" },

            {
              fieldname: "grand_total",
              fieldtype: "Currency",
              label: __("Order Total"),
              read_only: 1,
              default: frm.doc.rounded_total || frm.doc.grand_total
            },

            // ---------------- Refund Info ----------------
            { fieldtype: "Section Break", label: __("Refund Information") },

            {
              fieldname: "requested_refund_amount",
              fieldtype: "Currency",
              label: __("Refund Amount"),
              reqd: 1,
              read_only: 1,
              default: frm.doc.advance_paid
            },
            {
              fieldname: "refund_mode",
              fieldtype: "Select",
              label: __("Refund Mode"),
              options: ["UPI", "Bank", "Map to another order"].join("\n"),
              default: "Bank",
              reqd: 1
            },

            {
              fieldname: "refund_reason",
              fieldtype: "Small Text",
              label: __("Refund Reason")
            },
            // ---------------- UPI DETAILS ----------------
            {
              fieldtype: "Section Break",
              label: __("Map to Another Order Details"),
              depends_on: "eval:doc.refund_mode=='Map to another order'"
            },
            {
              fieldname: "target_order",
              fieldtype: "Link",
              options: "Sales Order",
              label: __("Target Order"),
              mandatory_depends_on: "eval:doc.refund_mode=='Map to another order'",
              // get_query: function (doc) {
              //   return {
              //     query: "shoption_api.cart.cart.orders_to_map_query",
              //     filters: {
              //       amount: doc.refund_amount || 0
              //     }
              //   };
              // }
            },
            // ---------------- UPI DETAILS ----------------
            {
              fieldtype: "Section Break",
              label: __("UPI Details"),
              depends_on: "eval:doc.refund_mode=='UPI'"
            },
            {
              fieldname: "upi_id",
              fieldtype: "Data",
              label: __("UPI Id"),
              mandatory_depends_on: "eval:doc.refund_mode=='UPI'"

            },
            {
              fieldname: "qr_code",
              fieldtype: "Attach",
              label: __("QR Code")
            },

            // ---------------- BANK DETAILS ----------------
            {
              fieldtype: "Section Break",
              label: __("Bank Details"),
              depends_on: "eval:doc.refund_mode=='Bank'"
            },
            {
              fieldname: "account_name",
              fieldtype: "Data",
              label: __("Account Name"),
              mandatory_depends_on: "eval:doc.refund_mode=='Bank'"
            },
            {
              fieldname: "account_no",
              fieldtype: "Data",   // ✅ FIXED
              label: __("Account No."),
              mandatory_depends_on: "eval:doc.refund_mode=='Bank'"
            },

            { fieldtype: "Column Break" },

            {
              fieldname: "bank_name",
              fieldtype: "Data",
              label: __("Bank Name"),
              mandatory_depends_on: "eval:doc.refund_mode=='Bank'"
            },
            {
              fieldname: "bank_branch",
              fieldtype: "Data",
              label: __("Bank Branch")
            },
            {
              fieldname: "ifsc",
              fieldtype: "Data",
              label: __("IFSC Code"),
              mandatory_depends_on: "eval:doc.refund_mode=='Bank'"
            },
            {
              fieldname: "chequebook_copy",
              fieldtype: "Attach",
              label: __("Cheque / Passbook Copy")
            }
          ],

          primary_action_label: __("Create Refund Request"),

          primary_action(values) {

            // ✅ Bank Mode Validation
            if (values.refund_mode === "Bank") {
              const required_fields = [
                "account_name",
                "account_no",
                "bank_name",
                "ifsc",
              ];

              for (let field of required_fields) {
                if (!values[field]) {
                  frappe.msgprint(__("Please fill {0}", [
                    field.replaceAll("_", " ").toUpperCase()
                  ]));
                  return;
                }
              }
            }

            // ✅ UPI Mode Validation
            if (values.refund_mode === "UPI") {
              const required_fields = ["upi_id"];   // ✅ corrected

              for (let field of required_fields) {
                if (!values[field]) {
                  frappe.msgprint(__("Please fill {0}", [
                    field.replaceAll("_", " ").toUpperCase()
                  ]));
                  return;
                }
              }
            }

            // ✅ Call Server
            frappe.call({
              method: "warrior.public.sales_order.make_refund_request_from_sales_order",
              args: {
                sales_order: frm.doc.name,
                payload: values
              },
              freeze: true,
              freeze_message: __("Creating Refund Request..."),
              callback: function (r) {
                if (!r.message) return;

                d.hide();

                frappe.show_alert({
                  message: __("Refund Request Created"),
                  indicator: "green"
                });

                frappe.set_route("Form", "Refund Request", r.message.name);
              }
            });
          }
        });

        d.show();
        frappe.call({
          method: "shoption_api.cart.cart.orders_to_map",
          args: {
            amount: d.get_value("requested_refund_amount"),
            customer: d.get_value("customer")
          },
          callback: function (r) {
            if (!r.message || !r.message.data) return;

            let order_list = r.message.data || [];

            // ✅ Remove current document
            order_list = order_list.filter(order => order !== frm.doc.name);

            // ✅ Apply filter
            d.fields_dict.target_order.get_query = function () {
              return {
                filters: {
                  name: ["in", order_list]
                }
              };
            };

            d.fields_dict.target_order.refresh();
          }
        });
      }, __("Create"));
    } // Run AFTER ERPNext adds its standard buttons
    frappe.after_ajax(() => {
      // Give a tiny delay because button rendering is sometimes async
      setTimeout(() => {
        const status = (frm.doc.custom_dispatch_status || "").toUpperCase();

        // First remove to avoid duplicates
        frm.page.remove_inner_button(__("Sales Invoice"), __("Create"));
        frm.page.remove_inner_button(__("Payment Request"), __("Create"));
        frm.remove_custom_button("Update Items")
        // Allow invoice until fully billed
        // 🔒 Pending Payment → Payment Entry only
        // if (status === "PENDING PAYMENT") {
        //   frm.page.add_inner_button(
        //     __("Payment Entry"),
        //     () => frm.trigger("make_payment_entry"),
        //     __("Create")
        //   );
        // }

        // 🚚 Dispatch states → Sales Invoice only
        if (["READY TO DISPATCH", "PARTIAL DISPATCH", "PARTIALLY DISPATCHED","PARTIALLY INVOICED", "PARTIALLY DELIVERED"].includes(status)) {

          // ✅ Step 1: Fully billed → don't show
          if (flt(frm.doc.per_billed) >= 100) return;

          // ✅ Step 2: Check draft invoice
          frappe.call({
            method: "warrior.public.sales_order.has_draft_invoice",
            args: {
              sales_order: frm.doc.name
            },
            callback: function (r) {

              // ❌ Draft exists → don't show
              if (r.message && r.message.has_draft) return;

              // ✅ All conditions passed → show button
              frm.page.add_inner_button(
                __("Sales Invoice"),
                () => frm.trigger("make_sales_invoice"),
                __("Create")
              );
            }
          });
        }
        // ---- Remove specific "Create" inner buttons ----
        frm.page.remove_inner_button(__("Delivery Note"), __("Create"));
        frm.page.remove_inner_button(__("Payment"), __("Create"));

        // frm.page.remove_inner_button(__("Sales Invoice"), __("Create"));
        frm.page.remove_inner_button(__("Pick List"), __("Create"));
        frm.page.remove_inner_button(__("Payment Request"), __("Create"));
        frm.page.remove_inner_button(__("Material Request"), __("Create"));
        frm.page.remove_inner_button(__("Work Order"), __("Create"));
        frm.page.remove_inner_button(__("Purchase Order"), __("Create"));
        // frm.page.remove_inner_button(__("Payment Entry"), __("Create"));
        frm.page.remove_inner_button(__("Request for Raw Materials"), __("Create"));
        frm.page.remove_inner_button(__("Project"), __("Create"));

        // If you want to remove stuff from Actions too:
        frm.page.remove_inner_button(__("Close"), __("Actions"));
        frm.page.remove_inner_button(__("Re-open"), __("Actions"));
        frm.page.remove_inner_button(__("Update Status"), __("Actions"));

      }, 200);
    });
  }
});

frappe.ui.form.on("Sales Order Item", {
  item_code(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  warehouse(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  qty(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  reserve_stock(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  stock_reserved_qty(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  actual_qty(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  custom_warehouse_actual_qty(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  },
  company_total_stock(frm, cdt, cdn) {
    set_qty_check_fields(cdt, cdn);
  }
});
