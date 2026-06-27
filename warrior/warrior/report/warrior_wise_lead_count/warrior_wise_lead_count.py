# File: lead_stage_summary.py (Script Report)

import frappe


def execute(filters=None):
    if not filters:
        filters = {}

    # ---------------------------------------------------
    # Filters
    # ---------------------------------------------------
    from_date = filters.get("from_date") or "2026-05-01"
    to_date = filters.get("to_date") or frappe.utils.today()
    default_role = filters.get("default_role")

    # ---------------------------------------------------
    # Get all Lead Stages dynamically
    # ---------------------------------------------------
    lead_stages = [
        d.name
        for d in frappe.get_all(
            "Lead Stages",
            fields=["name"],
            order_by="creation asc"
        )
    ]

    # ---------------------------------------------------
    # Columns
    # ---------------------------------------------------
    columns = [
        {
            "label": "Assigned To",
            "fieldname": "assigned_to",
            "fieldtype": "Link",
            "options": "User",
            "width": 180
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "Role",
            "fieldname": "default_role",
            "fieldtype": "Data",
            "width": 150
        },
    ]

    for stage in lead_stages:
        columns.append({
            "label": stage,
            "fieldname": frappe.scrub(stage),
            "fieldtype": "Int",
            "width": 120
        })

    columns.append({
        "label": "Total Leads",
        "fieldname": "total_leads",
        "fieldtype": "Int",
        "width": 120
    })

    # ---------------------------------------------------
    # Role Mapping
    # ---------------------------------------------------
    role_mapping = {
        "VRM B2B": ["Sales Voice", "Sales Field"],
        "VRM B2C": ["VRM B2C","GL – B2C"]
    }

    selected_roles = role_mapping.get(default_role, [])

    # ---------------------------------------------------
    # SQL Query
    # ---------------------------------------------------
    sql = """
        SELECT
            t.allocated_to,
            e.employee_name AS employee_name,
            e.custom_default_role,
            l.custom_lead_stage
        FROM `tabToDo` t
        JOIN `tabLead` l
            ON t.reference_type = 'Lead'
            AND t.reference_name = l.name
        LEFT JOIN `tabUser` u
            ON u.name = t.allocated_to
        LEFT JOIN `tabEmployee` e
            ON e.user_id = t.allocated_to
        WHERE
            DATE(t.creation) BETWEEN %s AND %s
            AND t.status = 'Open'
            AND e.status = "Active"
    """

    params = [from_date, to_date]

    # ---------------------------------------------------
    # Role Filter using Employee.custom_default_role
    # ---------------------------------------------------
    if selected_roles:
        placeholders = ", ".join(["%s"] * len(selected_roles))

        sql += f"""
            AND e.custom_default_role IN ({placeholders})
        """

        params.extend(selected_roles)

    # ---------------------------------------------------
    # Fetch Data
    # ---------------------------------------------------
    todos = frappe.db.sql(sql, params, as_dict=True)

    # ---------------------------------------------------
    # Aggregate Data
    # ---------------------------------------------------
    data = {}

    for todo in todos:
        key = todo["allocated_to"]

        if key not in data:
            data[key] = {
                "assigned_to": key,
                "employee_name": todo["employee_name"],
                "default_role": todo.get("custom_default_role"),
                "total_leads": 0
            }

            for stage in lead_stages:
                data[key][frappe.scrub(stage)] = 0

        stage = todo.get("custom_lead_stage")

        if stage:
            stage_field = frappe.scrub(stage)

            if stage_field in data[key]:
                data[key][stage_field] += 1

        data[key]["total_leads"] += 1

    return columns, list(data.values())