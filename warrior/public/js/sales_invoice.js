const STICKER_PRINT_FORMAT = "india post format";

function normalize_text(value) {
  return (value || "").toString().trim().toLowerCase();
}

function should_print_sticker(frm) {
  const transporter = normalize_text(frm.doc.transporter_name);
  const customer_group = normalize_text(frm.doc.customer_group);
  return transporter === "indian post" && customer_group === "farmer" && frm.doc.docstatus === 1 && frm.doc.custom_dispatch_status === "Print Stickers";
}
function show_print_sticker(frm) {
  const transporter = normalize_text(frm.doc.transporter_name);
  const customer_group = normalize_text(frm.doc.customer_group);
  return transporter === "indian post" && customer_group === "farmer" && frm.doc.docstatus === 1
}

function trigger_sticker_print(frm) {
  const format = encodeURIComponent(STICKER_PRINT_FORMAT);
  const url =
    `/printview?` +
    `doctype=Sales%20Invoice` +
    `&name=${encodeURIComponent(frm.doc.name)}` +
    `&format=${format}` +
    `&trigger_print=1` +
    `&no_letterhead=1` +
    `&_lang=en`;

  window.open(url, "_blank");
}

async function set_discount_from_sales_order(frm) {
    if (frm.doc.docstatus !== 0) {
        return;
    }

    const sales_order = frm.doc.items?.[0]?.sales_order;

    if (!sales_order) {
        return;
    }

    const r = await frappe.call({
        method: "warrior.public.sales_invoice_hooks.set_discount_from_sales_order",
        args: {
            sales_order: sales_order,
            current_invoice: frm.doc.name
        }
    });

    if (!r.message) {
        return;
    }

    if (
        r.message.apply_discount_on &&
        r.message.apply_discount_on !== frm.doc.apply_discount_on
    ) {
        await frm.set_value(
            "apply_discount_on",
            r.message.apply_discount_on || "Grand Total"
        );
    }

    // DO NOT SET DISCOUNT HERE
    // Python will calculate final discount
}

const recalculate_sales_order_discount = frappe.utils.debounce(async function (frm) {
  if (!frm || frm.doc.docstatus !== 0 || frm.__updating_sales_order_discount) {
    return;
  }

  frm.__updating_sales_order_discount = true;
  try {
    const r = await frappe.call({
      method: "warrior.public.sales_invoice_hooks.apply_proportional_coupon_discount",
      args: {
        doc: frm.doc,
        clear_discount_without_sales_order: true,
      },
    });

    if (r.message) {
      frappe.model.sync(r.message);
      frm.refresh_fields();
    }
  } finally {
    frm.__updating_sales_order_discount = false;
  }
}, 300);

function clear_sales_invoice_advances(frm) {
  if (!frm || frm.doc.docstatus !== 0 || !frm.doc.advances?.length) {
    return;
  }

  frm.clear_table("advances");
  frm.refresh_field("advances");
}

frappe.ui.form.on("Sales Invoice Item", {
  qty(frm) {
        clear_sales_invoice_advances(frm);
    recalculate_sales_order_discount(frm);
  },

  items_remove(frm) {
        clear_sales_invoice_advances(frm);

    recalculate_sales_order_discount(frm);
  },
});
frappe.ui.form.on("Sales Invoice", {
  async validate(frm) {
        await set_discount_from_sales_order(frm);
    },
  refresh(frm) {
    // await set_discount_from_sales_order(frm);

    // ✅ Only after submit
    if (frm.doc.docstatus !== 1) return;

    // ✅ Prevent duplicates on refresh
    frm.remove_custom_button(__("Print Sticker"));
    frm.remove_custom_button(__("Create Delivery Slip"), __("Create"));
    frm.remove_custom_button(__("Payment"), __("Create"));
    frm.remove_custom_button(__("Mark Delivered"));

    // ✅ Add your buttons
    if (should_print_sticker(frm)) {
      frm.add_custom_button(__("Print Sticker"), () => {
        open_sticker_dialog(frm);
      }, __("Create"));

    }
    if (show_print_sticker(frm)) {
      frm.add_custom_button(__("Stickers"), () => {
        open_print_dialog(frm);
      });
    }
    if (
      !["Packing OK", "Print Stickers", "Invoiced"].includes(frm.doc.custom_dispatch_status) &&
      frm.doc.docstatus === 1
    ) {
      frm.add_custom_button(__("Box Stickers"), () => {
        open_box_sticker_dialog(frm);
      });
    }

    if ((frm.doc.custom_dispatch_status == "Dispatched") && frm.doc.docstatus == 1) {
      frm.add_custom_button(
        __("Create Delivery Slip"),
        async () => {
          const r = await frappe.call({
            method: "warrior.public.sales_invoice_hooks.make_shipment_from_sales_invoice",
            args: { sales_invoice: frm.doc.name },
            freeze: true,
            freeze_message: __("Creating Delivery Slip..."),
          });

          if (r.message) {
            frappe.model.sync(r.message);
            frappe.set_route("Form", r.message.doctype, r.message.name);
          }
        },
        __("Create")
      );
    }

    if ((frm.doc.custom_dispatch_status == "Upload LR Main") && frm.doc.docstatus == 1 && !should_print_sticker(frm)) {
      frm.add_custom_button("Create LR Upload", async () => {

        const d = new frappe.ui.Dialog({
          title: __("Create LR Upload"),
          size: "large",
          fields: [
            // ===============================
            // CARRY FORWARD INFO (READ ONLY)
            // ===============================
            { fieldtype: "Section Break", label: __("Carry Forward Info") },

            {
              fieldname: "sales_invoice_ro",
              fieldtype: "Data",
              label: __("Sales Invoice"),
              read_only: 1,
              default: frm.doc.name
            },
            {
              fieldname: "customer_ro",
              fieldtype: "Data",
              label: __("Customer"),
              read_only: 1,
              default: frm.doc.customer_name || frm.doc.customer || ""
            },

            { fieldtype: "Column Break" },

            {
              fieldname: "customer_mobile_ro",
              fieldtype: "Data",
              label: __("Customer Mobile"),
              read_only: 1,
              default: frm.doc.contact_mobile || frm.doc.contact_phone || ""
            },

            { fieldtype: "Section Break" },

            // Nice formatted address blocks
            { fieldname: "customer_addr_html", fieldtype: "HTML", label: __("Customer Address") },
            { fieldtype: "Column Break" },
            { fieldname: "company_addr_html", fieldtype: "HTML", label: __("Company Address") },

            // ===============================
            // PACKAGE DETAILS (EDITABLE)
            // ===============================
            { fieldtype: "Section Break", label: __("Package Details") },
            { fieldname: "no_of_boxes", label: __("No of Boxes"), fieldtype: "Int", reqd: 1, default: frm.doc.custom_no_of_boxes || 1 },
            { fieldname: "total_charges", label: __("Total Charges"), fieldtype: "Float", reqd: 1 },
            { fieldtype: "Column Break" },
            { fieldname: "weight_in_grams", label: __("Weight (In Grams)"), fieldtype: "Int", reqd: 0 },
            // Row 2
            { fieldtype: "Section Break" },
            // ===============================
            // TRACKING & TRANSPORT (EDITABLE)
            // ===============================
            { fieldtype: "Section Break", label: __("Tracking & Transport") },
            {
              fieldname: "transport_name",
              label: __("Transport Name"),
              fieldtype: "Data",
              default: frm.doc.transporter_name || "",
              reqd: 1
            },
            {
              fieldname: "tracking_id",
              label: __("Tracking Id"),
              fieldtype: "Data",
              reqd: 1
            },

            { fieldtype: "Column Break" },

            { fieldname: "lr_copy", label: __("LR Copy"), fieldtype: "Attach", reqd: 1 },
            { fieldname: "remark", label: __("Remark"), fieldtype: "Small Text" },
            { fieldname: "estimated_time_arrival", label: __("Estimated Arrival Time"), fieldtype: "Datetime", reqd: 1 },

            { fieldtype: "Section Break" },

            {
              fieldname: "payment_status",
              label: __("Payment Status"),
              fieldtype: "Select",
              options: "Paid\nTo Pay",
              default: "Paid",
              reqd: 1
            }
          ],

          primary_action_label: __("Create"),
          primary_action: async () => {
            const values = d.get_values();
            if (!values) return;

            const r = await frappe.call({
              method: "warrior.public.sales_invoice_hooks.create_lr_from_sales_invoice_dialog",
              args: {
                sales_invoice: frm.doc.name,
                data: values
              },
              freeze: true,
              freeze_message: __("Creating LR document...")
            });

            let out = r.message || {};
            const lr_name = out.name;

            // If backend returns only name, fetch full doc to show carry-forward fields
            if (lr_name && (!out.customer_address && !out.customer_name)) {
              try {
                out = await frappe.db.get_doc("Upload LR Main", lr_name);
              } catch (e) { }
            }

            // Show carry-forward info in dialog (readonly)
            if (out && lr_name) {
              d.set_value("created_lr_ro", lr_name);

              // Render addresses (HTML)
              d.fields_dict.customer_addr_html.$wrapper.html(out.customer_address || "");
              d.fields_dict.company_addr_html.$wrapper.html(frm.doc.company_address_display || "");

              // Optionally set readonly fields from created doc
              d.set_value("customer_ro", out.customer_name || out.customer || d.get_value("customer_ro"));
              d.set_value("customer_mobile_ro", out.customer_mobile || d.get_value("customer_mobile_ro"));
            }

            d.hide();

            if (lr_name) {
              frappe.set_route("Form", "Upload LR Main", lr_name);
            } else {
              frappe.msgprint(__("LR created, but docname not returned."));
            }
          }
        });

        // Initial address render from Invoice (before creation)
        d.fields_dict.customer_addr_html.$wrapper.html(frm.doc.address_display || frm.doc.shipping_address || "");
        d.fields_dict.company_addr_html.$wrapper.html(frm.doc.company_address_display || "");

        d.show();
      }, __("Create"));
    }
    if (frm.doc.custom_dispatch_status === "Packing OK") {
      frm.add_custom_button(__("Packing OK"), () => {

        open_packing_ok_dialog(frm);
      }, __("Create"));
    }

    // ✅ Remove standard buttons AFTER ERPNext adds them
    frappe.after_ajax(() => {
      setTimeout(() => {
        // These are standard "Create" buttons ERPNext shows
        frm.page.remove_inner_button(__("Delivery Note"), __("Create"));
        frm.page.remove_inner_button(__("Payment Request"), __("Create"));
        frm.page.remove_inner_button(__("Dunning"), __("Create"));
        frm.page.remove_inner_button(__("Maintenance Schedule"), __("Create"));
        frm.page.remove_inner_button(__("Invoice Discounting"), __("Create"));
        frm.page.remove_inner_button(__("Payment Request"), __("Create"));
        // Depending on version/label, these may exist
        frm.page.remove_inner_button(__("Create Shipment"), __("Create"));
        frm.page.remove_inner_button(__("Payment"), __("Create"));
        frm.page.remove_inner_button(__("Delivery"), __("Create"));
      }, 200);
    });
  },
});


async function open_packing_ok_dialog(frm) {
  const d = new frappe.ui.Dialog({
    title: __("Packing OK"),
    size: "large",
    fields: [
      { fieldtype: "Section Break", label: __("Shipping Address") },
      { fieldname: "shipping_addr_html", fieldtype: "HTML", label: __("Shipping Address") },
      { fieldtype: "Section Break", label: __("Packing Details") },
      { fieldname: "no_of_boxes", label: __("No of Boxes"), fieldtype: "Int", reqd: 1 },
      { fieldtype: "Column Break" },
      {
        fieldname: "transporter",
        label: __("Transporter"),
        fieldtype: "Link",
        options: "Supplier",
        default: frm.doc.transporter || "",
      },
      {
        fieldname: "transporter_name",
        label: __("Transporter Name"),
        fieldtype: "Data",
        default: frm.doc.transporter_name || frm.doc.transporter || "",
      }
    ],
    primary_action_label: __("Create"),
    primary_action: async () => {
      const values = d.get_values();
      if (!values) return;

      const r = await frappe.call({
        method: "warrior.public.sales_invoice_hooks.create_packing_ok_slip_dialog",
        args: {
          sales_invoice: frm.doc.name,
          data: values,
        },
        freeze: true,
        freeze_message: __("Creating Packing OK Slip..."),
      });

      d.hide();

      const out = r.message || {};
      const packing_ok_name = out.name;
      const packing_ok_exists = out.already_exists;
      if (packing_ok_exists) {
        frappe.show_alert({
          message: __("Packing OK Slip already exists"),
          indicator: "orange",
        });
      } else {

        frappe.show_alert({
          message: __("Packing OK Slip Created"),
          indicator: "green",
        });
      }
      window.location.reload();      // const o = await frappe.call({
      //   method: "warrior.public.sales_invoice_hooks.create_outward_from_sales_invoice",
      //   args: { sales_invoice: frm.doc.name },
      //   freeze: true,
      //   freeze_message: __("Creating Outward..."),
      // });

      // const outward = (o && o.message) || {};
      // if (outward.name) {
      //   frappe.set_route("Form", "Outward", outward.name);
      // } else if (packing_ok_name) {
      //   frappe.set_route("Form", "Packing OK Slip", packing_ok_name);
      // }
    },
  });

  if (frm.doc.shipping_address_name) {
    try {
      const addr = await frappe.db.get_doc("Address", frm.doc.shipping_address_name);
      if (addr) {
        const html = addr.address_display || frm.doc.shipping_address || "";
        if (d.fields_dict.shipping_addr_html) {
          d.fields_dict.shipping_addr_html.$wrapper.html(html || "");
        }
        if (!d.get_value("district")) {
          d.set_value("district", addr.county || addr.city || "");
        }
        if (!d.get_value("state")) {
          d.set_value("state", addr.state || "");
        }
        if (!d.get_value("pincode")) {
          d.set_value("pincode", addr.pincode || "");
        }
      }
    } catch (e) { }
  }

  if (d.fields_dict.shipping_addr_html && !frm.doc.shipping_address_name) {
    d.fields_dict.shipping_addr_html.$wrapper.html(frm.doc.shipping_address || "");
  }

  d.show();
}
async function open_sticker_dialog(frm) {
  const default_rows = (frm.doc.items || [])
    .map(r => {
      const remaining = flt(r.custom_remaining_print_qty || 0);
      const print_qty = Math.max(flt(r.qty) - remaining, 0);
      console.log("item", r.item_code, "qty", r.qty, "remaining", remaining, "print_qty", print_qty);
      return {
        sales_invoice_item: r.name,
        item_code: r.item_code,
        item_name: r.item_name,
        qty: flt(r.qty),
        print_qty: cint(print_qty)
      };
    })
    .filter(r => cint(r.print_qty) > 0);

  if (!default_rows.length) {
    frappe.msgprint(__("All items already printed."));
    return;
  }

  const d = new frappe.ui.Dialog({
    title: __("Print Stickers / Create Tracking Log"),
    size: "large",
    fields: [
      // ===============================
      // CARRY-FORWARD INFO (READ ONLY)
      // ===============================
      { fieldtype: "Section Break", label: __("Carry Forward Info") },

      {
        fieldname: "reference_name_ro",
        fieldtype: "Data",
        label: __("Reference"),
        read_only: 1,
        default: frm.doc.name
      },
      {
        fieldname: "customer_ro",
        fieldtype: "Data",
        label: __("Customer"),
        read_only: 1,
        default: frm.doc.customer_name || frm.doc.customer || ""
      },

      { fieldtype: "Column Break" },

      {
        fieldname: "company_ro",
        fieldtype: "Data",
        label: __("Company"),
        read_only: 1,
        default: frm.doc.company || ""
      },

      { fieldtype: "Section Break" },

      // show formatted addresses as HTML
      { fieldname: "customer_addr_html", fieldtype: "HTML", label: __("Customer Address") },
      { fieldtype: "Column Break" },
      { fieldname: "company_addr_html", fieldtype: "HTML", label: __("Company Address") },

      // ===============================
      // PACKAGE DETAILS (EDITABLE)
      // ===============================
      { fieldtype: "Section Break", label: __("Package Details") },

      // Row 1
      {
        fieldname: "amount",
        label: __("Freight Amount"),
        fieldtype: "Currency",
        reqd: 1,
        default: flt(frm.doc.outstanding_amount || frm.doc.outstanding_amount || 0)
      },
      { fieldname: "no_of_boxes", label: __("No of Boxes"), fieldtype: "Int", reqd: 1 },

      { fieldtype: "Column Break" },

      { fieldname: "weight_in_grams", label: __("Weight (In Grams)"), fieldtype: "Int", reqd: 1 },

      // Row 2
      { fieldtype: "Section Break" },

      { fieldname: "length_cm", label: __("Length (cm)"), fieldtype: "Float", reqd: 1 },
      { fieldname: "breadth_cm", label: __("Breadth (cm)"), fieldtype: "Float", reqd: 1 },

      { fieldtype: "Column Break" },

      { fieldname: "height_cm", label: __("Height (cm)"), fieldtype: "Float", reqd: 1 },
      {
        fieldname: "transporter",
        fieldtype: "Link",
        label: __("Transporter"),
        options: "Supplier",
        reqd: 1,
        read_only: 1,
        default: frm.doc.transporter || ""
      },
      {
        fieldname: "transporter_name",
        fieldtype: "Data",
        label: __("Transporter Name"),
        reqd: 1,
        default: frm.doc.transporter_name || ""
      },

      // Row 3
      { fieldtype: "Section Break" },

      {
        fieldname: "estimated_time_arrival",
        label: __("Estimated Arrival Time"),
        fieldtype: "Datetime",
        reqd: 1
      },
      {
        fieldname: "payment_status",
        label: __("Payment Status"),
        fieldtype: "Select",
        options: "Paid\nTo Pay",
        default: "Paid",
        reqd: 1
      },

      // ===============================
      // ITEMS TABLE (FULL WIDTH)
      // ===============================
      { fieldtype: "Section Break" },

      {
        fieldname: "items_to_print",
        fieldtype: "Table",
        label: __("Items to Print"),
        reqd: 1,
        fields: [
          { fieldtype: "Data", fieldname: "item_code", label: __("Item Code"), in_list_view: 1, read_only: 1 },
          { fieldtype: "Data", fieldname: "item_name", label: __("Item Name"), in_list_view: 1, read_only: 1 },
          { fieldtype: "Float", fieldname: "qty", label: __("Invoice Qty"), in_list_view: 1, read_only: 1 },
          { fieldtype: "Int", fieldname: "print_qty", label: __("Print Qty"), in_list_view: 1, reqd: 1 },
          { fieldtype: "Data", fieldname: "sales_invoice_item", label: "SI Row", hidden: 1 }
        ]
      },

    ],

    primary_action_label: __("Create Tracking Log"),
    primary_action: async (values) => {
      const rows = (values.items_to_print || []).filter(r => cint(r.print_qty) > 0);
      if (!rows.length) {
        frappe.msgprint(__("Please set Print Qty for at least one item."));
        return;
      }

      const payload_items = rows.map(r => ({
        item_code: r.item_code,
        item_name: r.item_name,
        qty: flt(r.qty),
        print_qty: cint(r.print_qty),
        sales_invoice_item: r.sales_invoice_item
      }));

      const resp = await frappe.call({
        method: "warrior.public.sales_invoice_hooks.create_indian_post_tracking_log",
        args: {
          data: values,
          sales_invoice: frm.doc.name,
          items: payload_items
        },
        freeze: true,
        freeze_message: __("Creating Tracking Log...")
      });

      // server may return full doc or just {name}
      let log = resp.message || {};
      const logname = log.name;

      // if only name returned, fetch full doc to show carry-forward info
      if (logname && (!log.customer_address_display && !log.company_address_display)) {
        try {
          log = await frappe.db.get_doc("Indian Post Tracking Log", logname);
        } catch (e) {
          // ignore; print can still happen
        }
      }

      // fill read-only carry-forward info in the dialog (before hide, just for UX)
      if (log && logname) {
        d.set_value("tracking_id_ro", log.tracking_id || "");

        // render address HTML (best)
        d.fields_dict.customer_addr_html.$wrapper.html(log.customer_address_display || "");
        d.fields_dict.company_addr_html.$wrapper.html(log.company_address_display || "");
      }

      d.hide();

      if (logname) {
        const url =
          `/printview?doctype=${encodeURIComponent("Indian Post Tracking Log")}` +
          `&name=${encodeURIComponent(logname)}` +
          `&format=${encodeURIComponent("indian post format")}` +
          `&no_letterhead=0&trigger_print=1`;

        window.open(url, "_blank");
      } else {
        frappe.msgprint(__("Tracking Log created, but docname not returned."));
      }
    }
  });

  // Fill initial address HTML from invoice (optional)
  d.fields_dict.customer_addr_html.$wrapper.html(frm.doc.shipping_address || frm.doc.address_display || "");
  d.fields_dict.company_addr_html.$wrapper.html(frm.doc.company_address_display || "");

  // ✅ Put data into the grid AFTER dialog is created
  d.fields_dict.items_to_print.df.data = default_rows;
  d.fields_dict.items_to_print.grid.refresh();

  // ✅ Calculate total stickers
  const refresh_total = () => {
    const rows = d.get_value("items_to_print") || [];
    const total = rows.reduce((sum, r) => sum + cint(r.print_qty || 0), 0);
    d.set_value("total_labels", total);
  };

  d.show();
  refresh_total();

  d.fields_dict.items_to_print.grid.wrapper.on("change", refresh_total);
}



async function open_print_dialog(frm) {
  if (!frm.doc.name) return;

  const r = await frappe.call({
    method: "frappe.client.get_list",
    args: {
      doctype: "Indian Post Tracking Log",
      filters: {
        reference_type: "Sales Invoice",
        reference_name: frm.doc.name,
        is_cancelled: 0
      },
      fields: ["name", "tracking_id", "transporter", "total_weight", "creation"],
      order_by: "creation desc",
      limit_page_length: 50
    }
  });

  const logs = r.message || [];

  let html = "";

  if (!logs.length) {
    html = `<div class="text-muted">No stickers created for this invoice.</div>`;
  } else {
    html = `
      <table class="table table-bordered table-sm">
        <thead>
          <tr>
            <th>Tracking ID</th>
            <th>Transporter</th>
            <th>Weight (kg)</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
    `;

    logs.forEach(log => {
      html += `
        <tr>
          <td><b>${frappe.utils.escape_html(log.tracking_id || log.name)}</b></td>
          <td>${frappe.utils.escape_html(log.transporter || "-")}</td>
          <td>${log.total_weight || 0}</td>
          <td>${frappe.datetime.str_to_user(log.creation)}</td>
          <td>
            <button class="btn btn-xs btn-default" data-open="${log.name}">Open</button>
            <button class="btn btn-xs btn-primary" data-print="${log.name}">Print</button>
          </td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
  }

  const d = new frappe.ui.Dialog({
    title: __("Stickers"),
    size: "large",
    fields: [
      {
        fieldname: "stickers_html",
        fieldtype: "HTML"
      }
    ],
    primary_action_label: __("Close"),
    primary_action() {
      d.hide();
    }
  });

  d.show();
  d.fields_dict.stickers_html.$wrapper.html(html);

  // Open
  d.$wrapper.find("button[data-open]").on("click", function () {
    const name = $(this).attr("data-open");
    frappe.set_route("Form", "Indian Post Tracking Log", name);
  });

  // Print → open print dialog
  d.$wrapper.find("button[data-print]").on("click", function () {
    const name = $(this).attr("data-print");
    const log = logs.find(l => l.name === name);
    const url =
      `/printview?doctype=${encodeURIComponent("Indian Post Tracking Log")}` +
      `&name=${encodeURIComponent(name)}` +
      `&trigger_print=1&format=indian%20post%20format&no_letterhead=0&letterhead=Shoption%20Letter%20Head&settings=%7B%7D&_lang=en`;

    window.open(url, "_blank");// 👈 your existing print dialog
  });
}


async function open_box_sticker_dialog(frm) {
  if (!frm.doc.name) return;

  const r = await frappe.call({
    method: "frappe.client.get_list",
    args: {
      doctype: "Box Pasting Sticker",
      filters: {
        sales_invoice: frm.doc.name
        , docstatus: 1
      },
      fields: [
        "name",
        "box_number",
        "no_of_boxes",
        "marketplace",
        "tehsil",
        "customer_name",
        "invoice_amount",
        "creation",
        "envelope"
      ],
      order_by: "creation desc",
      limit_page_length: 50
    }
  });

  const logs = r.message || [];

  let html = "";

  if (!logs.length) {
    html = `<div class="text-muted">No box stickers created for this invoice.</div>`;
  } else {

    html = `
      <table class="table table-bordered table-sm">
        <thead>
          <tr>
            <th>Box</th>
            <th>Customer</th>
            <th>Marketplace</th>
            <th>Tehsil</th>
            <th>Amount</th>
            <th>Created</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
    `;

    logs.forEach(doc => {
      html += `
        <tr>
          <td><b>${doc.box_number || "-"} / ${doc.no_of_boxes || "-"}</b></td>
          <td>${frappe.utils.escape_html(doc.customer_name || "-")}</td>
          <td><b>${frappe.utils.escape_html(doc.marketplace || "-")}</b></td>
          <td><b>${frappe.utils.escape_html(doc.tehsil || "-")}</b></td>
          <td>₹ ${doc.invoice_amount || 0}</td>
          <td>${frappe.datetime.str_to_user(doc.creation)}</td>
          <td>
            <button class="btn btn-xs btn-default" data-open="${doc.name}">
              Open
            </button>

            <button class="btn btn-xs btn-primary" data-print="${doc.name}">
              Print
            </button>
          </td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
  }

  const d = new frappe.ui.Dialog({
    title: __("Box Stickers"),
    size: "large",
    fields: [
      {
        fieldname: "html",
        fieldtype: "HTML"
      }
    ],
    primary_action_label: __("Close"),
    primary_action() {
      d.hide();
    }
  });

  d.show();
  d.fields_dict.html.$wrapper.html(html);

  // OPEN DOCUMENT
  d.$wrapper.find("button[data-open]").on("click", function () {
    const name = $(this).attr("data-open");
    frappe.set_route("Form", "Box Pasting Sticker", name);
  });

  // PRINT STICKER
  d.$wrapper.find("button[data-print]").on("click", function () {
    const name = $(this).attr("data-print");

    const url =
      `/printview?doctype=${encodeURIComponent("Box Pasting Sticker")}`
      + `&name=${encodeURIComponent(name)}`
      + `&format=${encodeURIComponent("Box Pasting Sticker")}`
      + `&trigger_print=1`
      + `&no_letterhead=1`;

    window.open(url, "_blank");
  });
}