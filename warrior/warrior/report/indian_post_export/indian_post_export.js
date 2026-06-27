frappe.query_reports["Indian Post Export"] = {
    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.month_start()
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.get_today()
        }
    ],

    onload: function(report) {

        let html = `
            <div style="padding:10px; background:#f5f5f5; border-radius:6px; margin-bottom:10px;">
                <b>CUSTOMER NAME :-</b> Shoption Pvt Ltd<br>
                <b>CUSTOMER ID :-</b> Sptn9114151617<br>
                <b>MOBILE NUMBER :-</b> 9114151617 / 9114151617<br>
                <b>CONTRACT NO :-</b><br>
                <b>DATE :-</b> ${frappe.datetime.str_to_user(frappe.datetime.get_today())}
            </div>
        `;

        // ✅ safest way
        $(report.page.body).prepend(html);
    }
};