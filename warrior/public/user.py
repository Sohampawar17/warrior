import frappe


def remove_disabled_user_from_campaign(doc, method=None):

    if doc.enabled:
        return
    frappe.set_user("Administrator")

    rows = frappe.get_all(
        "Campaign Warriors",
        filters={
            "warrior": doc.name
        },
        fields=["name", "parent"]
    )

    affected_campaigns = set()
    for row in rows:

        affected_campaigns.add(row.parent)

        frappe.db.delete(
            "Campaign Warriors",
            {"name": row.name}
        )

    # Update parent modified timestamp
    for campaign in affected_campaigns:

        frappe.db.set_value(
            "Campaign",
            campaign,
            "modified",
            frappe.utils.now(),
            update_modified=False
        )