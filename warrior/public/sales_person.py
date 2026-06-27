import frappe
from frappe.utils import now

UP_DOCTYPE = "User Permission"
STATE_DOCTYPE = "Territory"
CUSTOMER_GROUP_DOCTYPE = "Customer Group"
TEHSIL_DOCTYPE = "Tahshil"
DISTRICT_DOCTYPE = "District"
WAREHOUSE_DOCTYPE = "Warehouse"

# -------------------------
# API (for JS)
# -------------------------
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
def get_districts_by_states(states):
    import json

    if isinstance(states, str):
        states = json.loads(states)

    if not states:
        return []

    return frappe.db.get_all(
        "District",
        filters={"state": ["in", states]},
        pluck="name"
    )

# -------------------------
# BEFORE SAVE (HOOK)
# -------------------------
def before_save(doc, method):

    if not doc.get("custom_user"):
        return

    user = doc.custom_user

    meta = frappe.get_meta(UP_DOCTYPE)
    has_marker = any(df.fieldname == "custom_created_by_utility" for df in meta.fields)

    # OLD
    old_doc = frappe.get_doc(doc.doctype, doc.name) if not doc.is_new() else None
    old_state = {r.state for r in (old_doc.custom_filter_states or [])} if old_doc else set()
    old_tehsils = {r.tehsil for r in (old_doc.custom_tehsils or [])} if old_doc else set()
    old_districts = {r.district for r in (old_doc.custom_districts or [])} if old_doc else set()
    old_cg = {r.customer_group for r in (old_doc.custom_customer_groups or [])} if old_doc else set()
    old_warehouses = {r.warehouse for r in (old_doc.custom_warrior_warehouse or [])} if old_doc else set()
    # NEW
    new_state = {r.state for r in (doc.custom_filter_states or [])}
    new_tehsils = {r.tehsil for r in (doc.custom_tehsils or [])}
    new_districts = {r.district for r in (doc.custom_districts or [])}
    new_cg = {r.customer_group for r in (doc.custom_customer_groups or [])}
    new_warehouses = {r.warehouse for r in (doc.custom_warrior_warehouse or [])}
    # DIFF
    add_state = new_state - old_state
    remove_state = old_state - new_state
    
    add_tehsil = new_tehsils - old_tehsils
    remove_tehsil = old_tehsils - new_tehsils

    add_district = new_districts - old_districts
    remove_district = old_districts - new_districts

    add_cg = new_cg - old_cg
    remove_cg = old_cg - new_cg
    add_warehouses = new_warehouses - old_warehouses
    remove_warehouses = old_warehouses - new_warehouses
    permission_changes = [
        (STATE_DOCTYPE, add_state, remove_state),
        (TEHSIL_DOCTYPE, add_tehsil, remove_tehsil),
        (DISTRICT_DOCTYPE, add_district, remove_district),
        (CUSTOMER_GROUP_DOCTYPE, add_cg, remove_cg),
        (WAREHOUSE_DOCTYPE, add_warehouses, remove_warehouses),
    ]

    changed = False
    for allow, values_to_add, values_to_remove in permission_changes:
        changed |= ensure_permissions(user, allow, values_to_add, has_marker)
        changed |= delete_permissions(user, allow, values_to_remove, has_marker)

    if changed:
        frappe.cache.hdel("user_permissions", user)
        frappe.publish_realtime("update_user_permissions", user=user, after_commit=True)

# -------------------------
# DELETE HOOK
# -------------------------
def on_trash(doc, method):

    if not doc.get("custom_user"):
        return

    meta = frappe.get_meta(UP_DOCTYPE)
    has_marker = any(df.fieldname == "custom_created_by_utility" for df in meta.fields)

    filters = {"user": doc.custom_user}

    if has_marker:
        filters["custom_created_by_utility"] = 1

    frappe.db.delete(UP_DOCTYPE, filters)
    frappe.cache.hdel("user_permissions", doc.custom_user)
    frappe.publish_realtime("update_user_permissions", user=doc.custom_user, after_commit=True)


# -------------------------
# HELPERS
# -------------------------
def chunks(values, size=500):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def ensure_permissions(user, allow, values, has_marker):
    values = sorted(v for v in values if v)
    if not values:
        return False

    existing = set()
    for value_chunk in chunks(values):
        existing.update(
            frappe.db.get_all(
                UP_DOCTYPE,
                filters={
                    "user": user,
                    "allow": allow,
                    "for_value": ["in", value_chunk],
                },
                pluck="for_value",
            )
        )

    values = [value for value in values if value not in existing]
    if not values:
        return False

    timestamp = now()
    session_user = frappe.session.user
    fields = [
        "name",
        "creation",
        "modified",
        "modified_by",
        "owner",
        "docstatus",
        "idx",
        "user",
        "allow",
        "for_value",
        "apply_to_all_doctypes",
        "applicable_for",
        "is_default",
        "hide_descendants",
    ]

    if has_marker:
        fields.append("custom_created_by_utility")

    rows = []
    for value in values:
        row = [
            frappe.generate_hash(length=10),
            timestamp,
            timestamp,
            session_user,
            session_user,
            0,
            0,
            user,
            allow,
            value,
            1,
            "",
            0,
            0,
        ]
        if has_marker:
            row.append(1)
        rows.append(row)

    frappe.db.bulk_insert(UP_DOCTYPE, fields, rows, ignore_duplicates=True)
    return True


def delete_permissions(user, allow, values, has_marker):
    values = sorted(v for v in values if v)
    if not values:
        return False

    deleted = False
    for value_chunk in chunks(values):
        filters = {
            "user": user,
            "allow": allow,
            "for_value": ["in", value_chunk],
        }

        if has_marker:
            filters["custom_created_by_utility"] = 1

        names = frappe.db.get_all(UP_DOCTYPE, filters=filters, pluck="name")
        if names:
            frappe.db.delete(UP_DOCTYPE, {"name": ["in", names]})
            deleted = True

    return deleted


def ensure_permission(user, allow, value, has_marker):

    if not value:
        return

    if frappe.db.exists(UP_DOCTYPE, {
        "user": user,
        "allow": allow,
        "for_value": value
    }):
        return

    up = frappe.get_doc({
        "doctype": UP_DOCTYPE,
        "user": user,
        "allow": allow,
        "for_value": value,
        "apply_to_all_doctypes": 1
    })

    if has_marker:
        up.custom_created_by_utility = 1

    up.insert(ignore_permissions=True)


def delete_permission(user, allow, value, has_marker):

    filters = {
        "user": user,
        "allow": allow,
        "for_value": value
    }

    if has_marker:
        filters["custom_created_by_utility"] = 1

    frappe.db.delete(UP_DOCTYPE, filters)
