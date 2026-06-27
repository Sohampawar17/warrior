frappe.ui.form.on("Purchase Invoice Item", {
    custom_qr_start: update_serial_series,
    custom_qr_end: update_serial_series
});

frappe.ui.form.on("Purchase Invoice", {
    refresh: function () {
        setup_serial_no_range_prefill();
    }
});

frappe.after_ajax(() => {
    setup_serial_no_range_prefill();
});

function update_serial_series(frm, cdt, cdn) {
    let row = frappe.get_doc(cdt, cdn);
console.log(row);
    if (row.custom_qr_start && row.custom_qr_end) {
        let expected_qty = `${row.item_code}${row.custom_qr_start}::${row.custom_qr_end}`;
console.log(expected_qty);
        frappe.model.set_value(
            cdt,
            cdn,
            "custom_serial_series",
            expected_qty
        );
    } else {
        frappe.model.set_value(
            cdt,
            cdn,
            "custom_serial_series",
            ""
        );
    }
}

function setup_serial_no_range_prefill() {
    if (!window.erpnext || !erpnext.SerialBatchPackageSelector) {
        return;
    }

    const proto = erpnext.SerialBatchPackageSelector.prototype;
    if (proto._warrior_serial_range_patched) {
        return;
    }

    const original_make = proto.make;
    proto.make = function () {
        original_make.apply(this, arguments);

        if (!this.item || !this.item.custom_serial_series) {
            return;
        }

        if (!this.dialog || !this.dialog.fields_dict || !this.dialog.fields_dict.serial_no_range) {
            return;
        }

        this.dialog
            .set_value("enter_manually", 1)
            .then(() => this.dialog.set_value("serial_no_range", this.item.custom_serial_series))
            .then(() => {
                if (typeof this.set_serial_nos_from_range === "function") {
                    this.set_serial_nos_from_range();
                }
            });
    };

    proto._warrior_serial_range_patched = true;
}


frappe.ui.form.on('Purchase Invoice', {
    refresh(frm) {
        enforce_purchase_invoice_button_policy(frm);
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Download Barcode PDF'), () => {

                const format = encodeURIComponent("purchase invoice barcodes");

                const url =
                    `/printview?` +
                    `doctype=Purchase%20Invoice` +
                    `&name=${frm.doc.name}` +
                    `&format=${format}` +
                    `&trigger_print=1` +
                    `&no_letterhead=1` +
                    `&_lang=en`;

                // Auto-download PDF
                window.open(url, '_blank');
            });
        }
    }
});

function enforce_purchase_invoice_button_policy(frm) {
    if (!frm.page) {
        return;
    }

    // Remove standard inner buttons, then re-add only the allowed ones.
    frm.page.clear_inner_toolbar();

    if (frm.cscript && typeof frm.cscript.setup_quality_inspection === "function") {
        frm.cscript.setup_quality_inspection();
    }
}
