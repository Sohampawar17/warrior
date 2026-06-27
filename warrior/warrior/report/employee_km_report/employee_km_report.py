# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()

    data = get_data(filters)

    report_summary = get_report_summary(data)

    chart = None

    skip_total_rows = 1

    return columns, data, None, chart, report_summary, skip_total_rows


def get_columns():
    return [
        {
            "label": "Employee",
            "fieldname": "employee",
            "fieldtype": "Data",
            "width": 140
        },
        {
            "label": "Employee Name",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 180
        },
        {
            "label": "Date",
            "fieldname": "date",
            "fieldtype": "Date",
            "width": 110
        },
        {
            "label": "In Time",
            "fieldname": "in_time",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": "In Meter Reading",
            "fieldname": "in_meter_reading",
            "fieldtype": "Int",
            "width": 150
        },
        {
            "label": "Out Time",
            "fieldname": "out_time",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": "Out Meter Reading",
            "fieldname": "out_meter_reading",
            "fieldtype": "Int",
            "width": 150
        },
        {
            "label": "Total KM",
            "fieldname": "total_km",
            "fieldtype": "Float",
            "width": 120
        }
    ]


def get_data(filters):

    conditions = []
    values = {}

    if filters.get("company"):
        conditions.append("emp.company = %(company)s")
        values["company"] = filters.get("company")

    if filters.get("employee"):
        conditions.append("ec.employee = %(employee)s")
        values["employee"] = filters.get("employee")

    if filters.get("from_date"):
        conditions.append("DATE(ec.time) >= %(from_date)s")
        values["from_date"] = filters.get("from_date")

    if filters.get("to_date"):
        conditions.append("DATE(ec.time) <= %(to_date)s")
        values["to_date"] = filters.get("to_date")

    condition_sql = ""

    if conditions:
        condition_sql = "WHERE " + " AND ".join(conditions)

    raw_data = frappe.db.sql(f"""
        SELECT

            ec.employee,
            emp.employee_name,

            DATE(ec.time) AS date,

            MIN(
                CASE
                    WHEN ec.log_type = 'IN'
                    THEN DATE_FORMAT(ec.time, '%%h:%%i %%p')
                END
            ) AS in_time,

            MIN(
                CASE
                    WHEN ec.log_type = 'IN'
                    THEN ec.custom_enter_km
                END
            ) AS in_meter_reading,

            MAX(
                CASE
                    WHEN ec.log_type = 'OUT'
                    THEN DATE_FORMAT(ec.time, '%%h:%%i %%p')
                END
            ) AS out_time,

            MAX(
                CASE
                    WHEN ec.log_type = 'OUT'
                    THEN ec.custom_enter_km
                END
            ) AS out_meter_reading,

			CASE
				WHEN MAX(
					CASE
						WHEN ec.log_type = 'OUT'
						THEN ec.custom_enter_km
					END
				) IS NULL
				THEN 0

				ELSE (
					IFNULL(
						MAX(
							CASE
								WHEN ec.log_type = 'OUT'
								THEN ec.custom_enter_km
							END
						), 0
					)
					-
					IFNULL(
						MIN(
							CASE
								WHEN ec.log_type = 'IN'
								THEN ec.custom_enter_km
							END
						), 0
					)
				)
			END AS total_km

        FROM `tabEmployee Checkin` ec

        INNER JOIN `tabEmployee` emp
            ON emp.name = ec.employee
            AND emp.status = 'Active'

        WHERE
            ec.custom_enter_km > 0
            {f"AND {' AND '.join(conditions)}" if conditions else ""}

        GROUP BY
            ec.employee,
            DATE(ec.time)

        ORDER BY
            emp.employee_name,
            DATE(ec.time) DESC

    """, values, as_dict=True)

    data = []

    employee_map = {}

    for row in raw_data:

        employee = row.employee

        if employee not in employee_map:

            employee_total_km = sum(
                d.total_km or 0
                for d in raw_data
                if d.employee == employee
            )

            parent_row = {
                "employee": employee,
                "employee_name": row.employee_name,
                "total_km": employee_total_km,
                "indent": 0,
                "is_group": 1
            }

            data.append(parent_row)

            employee_map[employee] = True

        child_row = row.copy()

        child_row["indent"] = 1

        data.append(child_row)

    return data


def get_report_summary(data):

    total_km = sum(
        d.get("total_km", 0) or 0
        for d in data
        if not d.get("is_group")
    )

    return [
        {
            "label": "Total KM",
            "value": total_km,
            "indicator": "Green",
            "datatype": "Float"
        }
    ]