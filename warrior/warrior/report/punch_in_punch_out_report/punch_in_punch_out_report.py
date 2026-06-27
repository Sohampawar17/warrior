import frappe
from frappe.utils import add_days, get_datetime, getdate, nowdate, time_diff_in_hours


def execute(filters=None):
    filters = frappe._dict(filters or {})
    from_date, to_date = get_date_range(filters)
    return get_columns(), get_data(filters, from_date, to_date)


def get_columns():
    return [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 160},
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": "Punch In", "fieldname": "punch_in", "fieldtype": "Datetime", "width": 170},
        {"label": "Punch In Selfie", "fieldname": "punch_in_selfie", "fieldtype": "Data", "width": 130},
        {"label": "Punch In KM", "fieldname": "punch_in_km", "fieldtype": "Float", "width": 110},
        {"label": "Punch In KM Photo", "fieldname": "punch_in_km_photo", "fieldtype": "Data", "width": 140},
        {"label": "Today's Agenda", "fieldname": "today_agenda", "fieldtype": "Data", "width": 220},
        {"label": "Punch Out", "fieldname": "punch_out", "fieldtype": "Datetime", "width": 170},
        {"label": "Punch Out Selfie", "fieldname": "punch_out_selfie", "fieldtype": "Data", "width": 130},
        {"label": "Punch Out KM", "fieldname": "punch_out_km", "fieldtype": "Float", "width": 110},
        {"label": "Punch Out KM Photo", "fieldname": "punch_out_km_photo", "fieldtype": "Data", "width": 140},
        {"label": "Working Hours", "fieldname": "working_hours", "fieldtype": "Float", "width": 120},
    ]


def get_date_range(filters):
    from_date = getdate(filters.get("from_date") or nowdate())
    to_date = getdate(filters.get("to_date") or filters.get("from_date") or nowdate())
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    return from_date, to_date


def get_data(filters, from_date, to_date):
    conditions = [
        "ec.time >= %(from_datetime)s",
        "ec.time < %(to_datetime)s",
        "emp.status = 'Active'",
    ]
    values = {
        "from_datetime": get_datetime(from_date),
        "to_datetime": get_datetime(add_days(to_date, 1)),
    }

    if filters.get("company"):
        conditions.append("emp.company = %(company)s")
        values["company"] = filters.company
    if filters.get("department"):
        conditions.append("emp.department = %(department)s")
        values["department"] = filters.department
    if filters.get("employee"):
        conditions.append("ec.employee = %(employee)s")
        values["employee"] = filters.employee

    rows = frappe.db.sql(
        f"""
        SELECT
            ec.name,
            ec.employee,
            emp.employee_name,
            emp.department,
            ec.log_type,
            ec.time,
            DATE(ec.time) AS date,
            ec.custom_upload_selfie,
            ec.custom_km_photo,
            ec.custom_enter_km,
            ec.custom_today_agenda
        FROM `tabEmployee Checkin` ec
        INNER JOIN `tabEmployee` emp ON emp.name = ec.employee
        WHERE {" AND ".join(conditions)}
        ORDER BY emp.employee_name, ec.employee, ec.time
        """,
        values,
        as_dict=True,
    )

    grouped = {}
    for row in rows:
        key = (row.employee, row.date)
        entry = grouped.setdefault(
            key,
            {
                "employee": row.employee,
                "employee_name": row.employee_name,
                "department": row.department,
                "date": row.date,
                "punch_in": None,
                "punch_in_selfie": None,
                "punch_in_km": None,
                "punch_in_km_photo": None,
                "today_agenda": None,
                "punch_out": None,
                "punch_out_selfie": None,
                "punch_out_km": None,
                "punch_out_km_photo": None,
                "working_hours": 0,
            },
        )

        if row.log_type == "IN" and (not entry["punch_in"] or row.time < entry["punch_in"]):
            entry.update(
                {
                    "punch_in": row.time,
                    "punch_in_selfie": row.custom_upload_selfie,
                    "punch_in_km": row.custom_enter_km,
                    "punch_in_km_photo": row.custom_km_photo,
                    "today_agenda": row.custom_today_agenda,
                }
            )
        elif row.log_type == "OUT" and (not entry["punch_out"] or row.time > entry["punch_out"]):
            entry.update(
                {
                    "punch_out": row.time,
                    "punch_out_selfie": row.custom_upload_selfie,
                    "punch_out_km": row.custom_enter_km,
                    "punch_out_km_photo": row.custom_km_photo,
                }
            )

    data = list(grouped.values())
    for row in data:
        if row.get("punch_in") and row.get("punch_out"):
            row["working_hours"] = round(time_diff_in_hours(row["punch_out"], row["punch_in"]), 2)

    return sorted(data, key=lambda d: (d.get("employee_name") or "", d.get("date")), reverse=False)
