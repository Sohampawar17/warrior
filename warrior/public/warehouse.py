import frappe


@frappe.whitelist()
def get_tehsils_by_districts(districts):
    import json

    if isinstance(districts, str):
        districts = json.loads(districts)

    if not districts:
        return []

    return frappe.db.get_all(
        "Tahshil",
        filters={"district": ["in", districts]},
        pluck="name"
    )
    
@frappe.whitelist()
def get_marketplaces_by_tehsils(tehsils):
    import json

    if isinstance(tehsils, str):
        tehsils = json.loads(tehsils)

    if not tehsils:
        return []

    return frappe.db.get_all(
        "Marketplace",
        filters={"tahshil": ["in", tehsils]},
        pluck="name"
    )
