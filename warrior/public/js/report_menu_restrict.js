frappe.views.QueryReport = class CustomQueryReport extends frappe.views.QueryReport {
    refresh() {
        super.refresh();

        // Allow all for Administrator & System Manager
        if (
            frappe.session.user === "Administrator" ||
            frappe.user.has_role("System Manager")
        ) {
            return;
        }

        const restrict_menu = () => {

            // Allowed menu items
            const allowed_labels = [
                "Print",
                "PDF",
                "Export",
                "Export as CSV",
                "Excel"
            ];

            // Remove unwanted menu items
            this.page.menu.find(".dropdown-item").each(function () {

                const label = $(this).text().trim();

                const allowed = allowed_labels.some(
                    item => label.toLowerCase().includes(item.toLowerCase())
                );

                if (!allowed) {
                    $(this).remove();
                }
            });

            // Remove inner buttons
            this.page.remove_inner_button("Edit");
            this.page.remove_inner_button("Add Column");
            this.page.remove_inner_button("User Permissions");
        };

        // Run multiple times because frappe loads menu dynamically
        setTimeout(restrict_menu, 500);
        setTimeout(restrict_menu, 1200);
        setTimeout(restrict_menu, 2500);
    }
};