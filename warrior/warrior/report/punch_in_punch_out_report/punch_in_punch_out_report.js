frappe.query_reports["Punch In Punch Out Report"] = {
    filters: [
        {
            fieldname: "company",
            label: "Company",
            fieldtype: "Link",
            options: "Company",
            default: frappe.defaults.get_user_default("Company"),
        },
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "department",
            label: "Department",
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "employee",
            label: "Employee",
            fieldtype: "Link",
            options: "Employee",
            get_query: function () {
                return { filters: { status: "Active" } };
            },
        },
    ],
    formatter: function (value, row, column, data, default_formatter) {
        const photo_fields = [
            "punch_in_selfie",
            "punch_in_km_photo",
            "punch_out_selfie",
            "punch_out_km_photo",
        ];

        if (photo_fields.includes(column.fieldname) && value) {
            const safe_url = frappe.utils.escape_html(value);
            return `
                <a href="${safe_url}" target="_blank" rel="noopener noreferrer">
                    <img src="${safe_url}" style="height:42px;width:42px;object-fit:cover;border-radius:4px;border:1px solid #d1d8dd;">
                </a>
            `;
        }

        return default_formatter(value, row, column, data);
    },
};
