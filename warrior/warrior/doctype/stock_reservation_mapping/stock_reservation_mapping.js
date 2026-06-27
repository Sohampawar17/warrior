function set_total_qty_to_map(frm) {
  const total = (frm.doc.items || []).reduce((sum, row) => sum + flt(row.qty_to_map || 0), 0);
  frm.set_value("total_qty_to_map", total);
}

function get_order_details_fieldname(frm) {
  return frm.fields_dict.order_details ? "order_details" : "target_sales_order_details";
}

function get_source_table_fieldname(frm) {
  return frm.fields_dict.target_order_items ? "target_order_items" : "source_orders";
}

function get_selected_target_rows(frm) {
  return (frm.doc.target_order_items || frm.doc.source_orders || []).filter((row) => cint(row.select) === 1);
}

function get_selected_source_orders(frm) {
  return (frm.doc.source_sales_order || [])
    .map((row) => row.sales_order)
    .filter(Boolean);
}

function update_source_sales_order_from_selection(frm) {
  const selected_rows = get_selected_target_rows(frm);
  if (!selected_rows.length) return;

  const first_source_order = selected_rows[0].sales_order;
  if (frm.doc.target_sales_order === first_source_order) {
    frm.set_value("target_sales_order", "");
  }
}

function fetch_source_orders(frm) {
  if (!frm.doc.target_sales_order) {
    frappe.msgprint(__("Select Target Sales Order first."));
    return;
  }

  frappe.call({
    method: "warrior.warrior.doctype.stock_reservation_mapping.stock_reservation_mapping.fetch_source_orders",
    args: {
      dispatch_status: frm.doc.dispatch_status,
      source_sales_order: frm.doc.source_sales_order,
      target_sales_order: frm.doc.target_sales_order
    },
    freeze: true,
    freeze_message: __("Fetching source orders..."),
    callback(r) {
      const source_table = get_source_table_fieldname(frm);
      frm.clear_table(source_table);

      (r.message || []).forEach((row) => {
        const child = frm.add_child(source_table);
        child.sales_order = row.sales_order;
        child.customer = row.customer;
        child.customer_name = row.customer_name;
        child.dispatch_status = row.dispatch_status;
        child.item = row.item;
        child.item_name = row.item_name;
        child.warehouse = row.warehouse;
        child.ordered_qty = row.ordered_qty;
        child.reserved_qty = row.reserved_qty;
        child.available_qty = row.available_qty;
        child.sales_order_item = row.sales_order_item;
        child.stock_reservation_entry = row.stock_reservation_entry;
      });

      frm.refresh_field(source_table);
      frappe.show_alert({
        message: __("Fetched {0} source rows", [r.message ? r.message.length : 0]),
        indicator: "green"
      });
    }
  });
}

function clear_source_sales_orders(frm) {
  frm.clear_table("source_sales_order");
  frm.refresh_field("source_sales_order");
}

function render_order_html(frm) {
  const order_details_field = get_order_details_fieldname(frm);

  if (!frm.doc.target_sales_order) {
    frm.set_df_property(order_details_field, "options", "");
    return;
  }

  frm.set_df_property(
    order_details_field,
    "options",
    "<div style='padding:10px;color:#666;'>Loading order details...</div>"
  );

  frappe.call({
    method: "warrior.warrior.doctype.stock_reservation_mapping.stock_reservation_mapping.get_target_sales_order_details",
    args: {
      target_sales_order: frm.doc.target_sales_order
    },
    callback(r) {
      const html = r.message && r.message.html ? r.message.html : "";
      frm.set_df_property(order_details_field, "options", html);
    }
  });
}

function fetch_target_items(frm) {
  const target_table = get_source_table_fieldname(frm);

  if (!frm.doc.target_sales_order) {
    frm.clear_table(target_table);
    frm.refresh_field(target_table);
    set_total_qty_to_map(frm);
    return;
  }

  frappe.call({
    method: "warrior.warrior.doctype.stock_reservation_mapping.stock_reservation_mapping.fetch_target_items",
    args: {
      target_sales_order: frm.doc.target_sales_order
    },
    freeze: true,
    freeze_message: __("Fetching target items..."),
   callback(r) {
      frm.clear_table(target_table);

      (r.message || []).forEach((row) => {
        const child = frm.add_child(target_table);
        child.select = 1;
        child.sales_order = row.sales_order;
        child.customer = row.customer;
        child.customer_name = row.customer_name;
        child.dispatch_status = row.dispatch_status;
        child.item = row.item;
        child.item_name = row.item_name;
        child.warehouse = row.warehouse;
        child.ordered_qty = row.ordered_qty;
        child.item_reserved_qty = row.item_reserved_qty;
        child.reserved_qty = row.reserved_qty;
        child.available_qty = row.available_qty;
        child.sales_order_item = row.sales_order_item;
        child.stock_reservation_entry = row.stock_reservation_entry;
      });

      frm.refresh_field(target_table);
      frappe.show_alert({
        message: __("Fetched {0} target item rows", [r.message ? r.message.length : 0]),
        indicator: "green"
      });
    }
  });
}

function prepare_mapping(frm) {

  const selected_sources = get_selected_source_orders(frm);
  const selected_targets = get_selected_target_rows(frm);

  if (!selected_sources.length) {
    frappe.msgprint(__("Select at least one Source Sales Order."));
    return;
  }

  if (!selected_targets.length) {
    frappe.msgprint(__("Select at least one row in Target Order Items."));
    return;
  }

  // update_source_sales_order_from_selection(frm);

  if (!frm.doc.target_sales_order) {
    frappe.msgprint(__("Select Target Sales Order."));
    return;
  }

  frappe.call({
    method: "warrior.warrior.doctype.stock_reservation_mapping.stock_reservation_mapping.prepare_mapping",
    args: {
      selected_sources: selected_sources,
      target_sales_order: frm.doc.target_sales_order,
      target_items: selected_targets
    },
    freeze: true,
    freeze_message: __("Preparing mapping..."),
    callback(r) {
  frm.clear_table("items");
      console.log(r.message);
  (r.message || []).forEach((row) => {
  if (flt(row.qty_to_map || 0) <= 0) return;
  if (flt(row.target_pending_qty || 0) <= 0) return;

  const child = frm.add_child("items");

  child.source_order = row.source_order;
  child.target_sales_order = row.target_sales_order;

  child.source_sales_order_item = row.source_sales_order_item;
  child.target_sales_order_item = row.target_sales_order_item;
  child.stock_reservation_entry = row.stock_reservation_entry;
  child.item_code = row.item_code;
  child.item_name = row.item_name;
  child.warehouse = row.warehouse;
  child.source_reserved_qty = row.source_reserved_qty;
  child.target_pending_qty = row.target_pending_qty;
  child.qty_to_map = row.qty_to_map;
  child.uom = row.uom;
  child.mapping_status = row.mapping_status || "Pending";
  child.error_message = row.error_message;
});

  frm.refresh_field("items");

  set_total_qty_to_map(frm);

}
  });
}

frappe.ui.form.on("Stock Reservation Mapping", {
  setup(frm) {
    frm.set_query("source_sales_order", function() {
    return {
        query: "warrior.warrior.doctype.stock_reservation_mapping.stock_reservation_mapping.source_sales_order_query",
        filters: {
            target_sales_order: frm.doc.target_sales_order,
            target_items: JSON.stringify(frm.doc.target_order_items || [])
        }
    };
});

    frm.set_query("target_sales_order", () => {
      return {
        query: "warrior.warrior.doctype.stock_reservation_mapping.stock_reservation_mapping.target_sales_order_query"
      };
    });
  },

  refresh(frm) {
    render_order_html(frm);
  },

  fetch_source_orders(frm) {
    fetch_source_orders(frm);
  },

  prepare_mapping(frm) {
    prepare_mapping(frm);
  },

  validate(frm) {
    set_total_qty_to_map(frm);

    if (frm.doc.docstatus !== 0) return;

    if (frm.doc.items && frm.doc.items.length) {
      const rows_to_map = (frm.doc.items || []).filter((row) => flt(row.qty_to_map || 0) > 0);

      if (rows_to_map.length && !frm.doc.target_sales_order) {
        frappe.throw(__("Select Target Sales Order."));
      }
    }
  },

  target_sales_order(frm) {
    render_order_html(frm);
    fetch_target_items(frm);
    clear_source_sales_orders(frm);
  },

  source_sales_order(frm) {
  }
});

frappe.ui.form.on("Stock Reservation Mapping Source", {
  select(frm, cdt, cdn) {
    const row = locals[cdt] && locals[cdt][cdn];
    if (row && row.parentfield === "target_order_items") return;
    update_source_sales_order_from_selection(frm);
  }
});

frappe.ui.form.on("Stock Reservation Mapping Item", {
  qty_to_map(frm) {
    set_total_qty_to_map(frm);
  },
  items_remove(frm) {
    set_total_qty_to_map(frm);
  }
});
frappe.ui.form.on("Stock Reservation Mapping Source", {
    reserved_qty(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (flt(row.reserved_qty) > flt(row.available_qty)) {

            frappe.msgprint(
                __("Reserved Qty cannot be greater than Available Qty ({0})", [
                    row.available_qty
                ])
            );

            frappe.model.set_value(
                cdt,
                cdn,
                "reserved_qty",
                flt(row.available_qty)
            );
        }
    }
});