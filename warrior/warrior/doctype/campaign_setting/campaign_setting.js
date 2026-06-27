// Copyright (c) 2026, Abhishek Dubey and contributors
// For license information, please see license.txt

frappe.ui.form.on("Campaign Setting", {
    refresh(frm) {
        frm.add_custom_button(__("Import Leads from Google Sheet"), function () {
            frappe.call({
                method: "warrior.warrior.doctype.campaign_setting.campaign_setting.import_leads_from_google_sheet",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint(r.message);
                    }
                }
            });
        });
    },
});
