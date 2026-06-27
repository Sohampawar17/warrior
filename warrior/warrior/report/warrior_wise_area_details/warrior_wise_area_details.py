import frappe


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": "Warrior",
            "fieldname": "sales_person_name",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "User",
            "fieldname": "custom_user",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120,
        },
        {
            "label": "State",
            "fieldname": "state",
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "label": "District",
            "fieldname": "district_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": "Tehsil",
            "fieldname": "tahshil",
            "fieldtype": "Data",
            "width": 200,
        },
    ]


def get_data(filters):
    data = []

    warrior_filters = {
        "is_group": 0,
        "enabled": 1,
         "custom_user": ["is", "set"],
    }

    if filters.get("employee"):
        warrior_filters["employee"] = filters.get("employee")

    warriors = frappe.get_all(
        "Sales Person",
        filters=warrior_filters,
        fields=[
            "name",
            "sales_person_name",
            "custom_user",
            "employee",
        ],
        order_by="sales_person_name",
    )

    for warrior in warriors:

        states = frappe.get_all(
            "User Permission State",
            filters={"parent": warrior.name},
            pluck="state",
        )
        if not states:
                continue
        # State filter
        if filters.get("state"):
            states = [s for s in states if s == filters.get("state")]

            if not states:
                continue

        districts = frappe.db.sql(
            """
            SELECT d.district_name
            FROM `tabUser Permission District` upd
            INNER JOIN `tabDistrict` d
                ON d.name = upd.district
            WHERE upd.parent = %s
            ORDER BY d.district_name
            """,
            warrior.name,
            as_dict=True,
        )

        tehsils = frappe.db.sql(
            """
            SELECT t.tahshil
            FROM `tabUser Permission Tehsil` upt
            INNER JOIN `tabTahshil` t
                ON t.name = upt.tehsil
            WHERE upt.parent = %s
            ORDER BY t.tahshil
            """,
            warrior.name,
            as_dict=True,
        )

        max_rows = max(
            len(states) if states else 1,
            len(districts) if districts else 1,
            len(tehsils) if tehsils else 1,
        )

        for i in range(max_rows):
            data.append(
                {
                    "sales_person_name": warrior.sales_person_name if i == 0 else "",
                    "custom_user": warrior.custom_user if i == 0 else "",
                    "employee": warrior.employee if i == 0 else "",
                    "state": states[i] if i < len(states) else "",
                    "district_name": districts[i].district_name if i < len(districts) else "",
                    "tahshil": tehsils[i].tahshil if i < len(tehsils) else "",
                }
            )

    return data