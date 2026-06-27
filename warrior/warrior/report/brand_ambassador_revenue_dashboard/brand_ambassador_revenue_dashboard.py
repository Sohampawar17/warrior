import frappe
from frappe.utils import flt, getdate, nowdate, is_invalid_date_string



def execute(filters=None):
    filters = frappe._dict(filters or {})
    from_date, to_date = get_date_range(filters)
    columns = get_columns()
    data = get_data(from_date, to_date)
    chart = get_chart(data)
    report_summary = get_report_summary(data)

    return columns, data, None, chart, report_summary

def get_summary_base_rows(data):
      manager_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
      if manager_employee:
          manager_rows = [row for row in data if row.get("employee") == manager_employee]
          if manager_rows:
              return manager_rows
      return [row for row in data if int(row.get("indent") or 0) == 0]


def get_report_summary(data):
    top_rows = get_summary_base_rows(data)

    total_orders = sum(int(row.get("order_count") or 0) for row in top_rows)
    total_order_amount = sum(flt(row.get("order_amount") or 0) for row in top_rows)
    total_received_amount = sum(flt(row.get("received_amount") or 0) for row in top_rows)
    total_invoice_amount = sum(flt(row.get("invoice_amount") or 0) for row in top_rows)
    total_return_amount = sum(flt(row.get("return_invoice_amount") or 0) for row in top_rows)
    total_ba = sum(int(row.get("brand_ambassador_count") or 0) for row in top_rows)
    total_lifetime_ba = sum(int(row.get("total_brand_ambassador_count") or 0) for row in top_rows)

    return [
    {
        "label": "Brand Ambassadors(Date Range)",
        "value": total_ba,
        "datatype": "Int",
        "indicator": "Blue"
    },
    {
        "label": "Brand Ambassadors(Lifetime)",
        "value": total_lifetime_ba,
        "datatype": "Int",
        "indicator": "Orange"
    },
    {
        "label": "Orders",
        "value": total_orders,
        "datatype": "Int",
        "indicator": "Green"
    },
    {
        "label": "Order Amount",
        "value": total_order_amount,
        "datatype": "Currency",
        "indicator": "Cyan"
    },
    {
        "label": "Received Amount",
        "value": total_received_amount,
        "datatype": "Currency",
        "indicator": "Purple"
    },
    {
        "label": "Invoice Amount",
        "value": total_invoice_amount,
        "datatype": "Currency",
        "indicator": "Pink"
    },
    {
        "label": "Return Amount",
        "value": total_return_amount,
        "datatype": "Currency",
        "indicator": "Red"
    },
]


def get_chart(data):
    top_rows = get_summary_base_rows(data)
    if not top_rows:
        return None

    total_order_amount = sum(flt(row.get("order_amount") or 0) for row in top_rows)
    total_received_amount = sum(flt(row.get("received_amount") or 0) for row in top_rows)
    total_invoice_amount = sum(flt(row.get("invoice_amount") or 0) for row in top_rows)
    total_return_amount = sum(flt(row.get("return_invoice_amount") or 0) for row in top_rows)

    return {
        "data": {
            "labels": ["Order Amount", "Received Amount", "Invoice Amount", "Return Invoice Amount"],
            "datasets": [
                {
                    "name": "Amount",
                    "values": [
                        total_order_amount,
                        total_received_amount,
                        total_invoice_amount,
                        total_return_amount,
                    ],
                }
            ],
        },
        "type": "bar",
        "colors": ["#4C78A8"],
    }

def get_date_range(filters):
    if not filters.get("from_date") and not filters.get("to_date"):
        today = getdate(nowdate())
        return today, today
    return getdate(filters.from_date), getdate(filters.to_date)


def get_columns():
    return [
        # {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 180},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "From Date", "fieldname": "from_date", "fieldtype": "Date", "width": 100},
        {"label": "To Date", "fieldname": "to_date", "fieldtype": "Date", "width": 100},
        {"label": "Brand Ambassador Count (Date Range)", "fieldname": "brand_ambassador_count", "fieldtype": "Int", "width": 220},
        {"label": "Total Brand Ambassador Count (Lifetime)", "fieldname": "total_brand_ambassador_count", "fieldtype": "Int", "width": 250},
        {"label": "Order Count", "fieldname": "order_count", "fieldtype": "Int", "width": 120},
        {"label": "Order Amount", "fieldname": "order_amount", "fieldtype": "Currency", "width": 150},
        {"label": "Receipt Amount", "fieldname": "received_amount", "fieldtype": "Currency", "width": 150},
        {"label": "Pending Amount", "fieldname": "pending_amount", "fieldtype": "Currency", "width": 150},
        {"label": "Invoice Amount", "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 150},
        {"label": "Return Amount", "fieldname": "return_invoice_amount", "fieldtype": "Currency", "width": 180},
    ]


def get_data(from_date, to_date):
    manager = get_manager()
    if not manager:
        return []

    report_employees = get_hierarchy_scope_for_user(manager)
    if not report_employees:
        return []

    employee_map = {emp.name: emp for emp in report_employees}
    metrics = get_employee_metrics(from_date, to_date, set(employee_map.keys()))
    lifetime = get_total_brand_ambassador_count()

    children_map = {}
    for emp in report_employees:
        parent = emp.reports_to or ""
        children_map.setdefault(parent, []).append(emp.name)

    result = []

    def add_node(emp_id, level=0):
        emp = employee_map[emp_id]
        metric = metrics.get(emp_id, {})
        row = {
            "employee": emp_id,
            "employee_name": emp.employee_name,
            "parent_employee": (f"{emp.reports_to} : {employee_map[emp.reports_to].employee_name}" if emp.reports_to and emp.reports_to in employee_map else ""),
            "indent": level,
            "is_group": 1 if children_map.get(emp_id) else 0,
            "from_date": from_date,
            "to_date": to_date,
            "brand_ambassador_count": int(metric.get("brand_ambassador_count") or 0),
            "total_brand_ambassador_count": int(lifetime.get(emp_id, 0)),
            "order_count": int(metric.get("order_count") or 0),
            "order_amount": flt(metric.get("order_amount") or 0),
            "invoice_amount": flt(metric.get("invoice_amount") or 0),
            "received_amount": flt(metric.get("received_amount") or 0),
            "pending_amount": max(flt(metric.get("order_amount") or 0) - flt(metric.get("received_amount") or 0), 0),
            "return_invoice_amount": flt(metric.get("return_invoice_amount") or 0),
        
        }

        for child in children_map.get(emp_id, []):
            child_row = add_node(child, level + 1)
            row["brand_ambassador_count"] += int(child_row.get("brand_ambassador_count") or 0)
            row["total_brand_ambassador_count"] += int(child_row.get("total_brand_ambassador_count") or 0)
            row["order_count"] += int(child_row.get("order_count") or 0)
            row["order_amount"] += flt(child_row.get("order_amount") or 0)
            row["invoice_amount"] += flt(child_row.get("invoice_amount") or 0)
            row["received_amount"] += flt(child_row.get("received_amount") or 0)
            row["pending_amount"] += flt(child_row.get("pending_amount") or 0)
            row["return_invoice_amount"] += flt(child_row.get("return_invoice_amount") or 0)

        result.append(row)
        return row

    add_node(manager, 0)
    result.reverse()
    return result


def get_manager():
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def get_hierarchy_scope_for_user(manager_employee):
    all_employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "reports_to"],
        limit_page_length=0,
    )

    employee_map = {emp.name: emp for emp in all_employees}
    if manager_employee not in employee_map:
        return []

    children_map = {}
    for emp in all_employees:
        parent = emp.reports_to or ""
        children_map.setdefault(parent, []).append(emp.name)

    result = []

    def collect(emp_id):
        result.append(employee_map[emp_id])
        for child in children_map.get(emp_id, []):
            collect(child)

    collect(manager_employee)
    return result


def get_employee_metrics(from_date, to_date, employee_ids):
    if not employee_ids:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            e.employee_name AS employee_name,
            COUNT(DISTINCT so.name) AS order_count,
            IFNULL(SUM(DISTINCT so.grand_total), 0) AS order_amount,
            IFNULL(
                SUM(
                    DISTINCT CASE
                        WHEN si.is_return = 0
                        THEN si.grand_total
                        ELSE 0
                    END
                ),
                0
            ) AS invoice_amount,
            IFNULL(
                SUM(
                    DISTINCT IFNULL(so.advance_paid, 0)
                ),
                0
            ) AS received_amount,
            IFNULL(
                SUM(
                    DISTINCT CASE
                        WHEN si.is_return = 1
                        THEN ABS(si.grand_total)
                        ELSE 0
                    END
                ),
                0
            ) AS return_invoice_amount,
            COUNT(DISTINCT ba.name) AS brand_ambassador_count
        FROM `tabEmployee` e
        LEFT JOIN `tabBrand Ambassador` ba
            ON (
                LOWER(TRIM(IFNULL(ba.warrior, ''))) = LOWER(TRIM(IFNULL(e.user_id, '')))
                OR TRIM(IFNULL(ba.warrior, '')) = TRIM(e.name)
                OR TRIM(IFNULL(ba.warrior, '')) = TRIM(IFNULL(e.employee_number, ''))
                OR TRIM(IFNULL(ba.warrior, '')) = TRIM(IFNULL(e.custom_emp_id, ''))
            )
            AND (
                %(from_date)s IS NULL
                OR %(to_date)s IS NULL
                OR DATE(ba.joining_date) BETWEEN %(from_date)s AND %(to_date)s
            )
        LEFT JOIN `tabSales Order` so
            ON (
                so.custom_brand_ambassador = ba.name
                AND so.docstatus = 1
                AND IFNULL(so.custom_brand_ambassador, '') != ''
                AND COALESCE(NULLIF(TRIM(so.custom_dispatch_status), ''), so.status) NOT IN ('CANCELLED', 'REFUNDED')
                AND (
                    COALESCE(so.advance_paid, 0) > 0
                    OR EXISTS (
                        SELECT 1
                        FROM `tabBank Transfer Request` btr
                        WHERE btr.sales_order = so.name
                          AND btr.docstatus = 0
                          AND btr.transfer_type = 'Bank Transfer'
                          AND btr.status = 'Unsettled'
                    )
                )
                AND (
                    %(from_date)s IS NULL
                    OR %(to_date)s IS NULL
                    OR so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
                )
            )
        LEFT JOIN `tabSales Invoice Item` sii
            ON sii.sales_order = so.name
        LEFT JOIN `tabSales Invoice` si
            ON si.name = sii.parent
            AND si.docstatus = 1
        WHERE e.name IN %(employees)s
        GROUP BY e.name, e.employee_name
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "employees": tuple(employee_ids),
        },
        as_dict=True,
    )

    lifetime_rows = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            COUNT(ba.name) AS total_brand_ambassador_count
        FROM `tabBrand Ambassador` ba
        INNER JOIN `tabEmployee` e ON e.user_id = ba.warrior
        GROUP BY e.name
        """,
        as_dict=True,
    )

    lifetime_map = {row.employee: int(row.total_brand_ambassador_count or 0) for row in lifetime_rows}

    out = {}
    for row in rows:
        out[row.employee] = {
            "employee_name": row.employee_name,
            "brand_ambassador_count": int(row.brand_ambassador_count or 0),
            "total_brand_ambassador_count": lifetime_map.get(row.employee, 0),
            "order_count": int(row.order_count or 0),
            "order_amount": flt(row.order_amount or 0),
            "received_amount": flt(row.received_amount or 0),
            "invoice_amount": flt(row.invoice_amount or 0),
            "return_invoice_amount": flt(row.return_invoice_amount or 0),
        }

    return out


def get_total_brand_ambassador_count():
    rows = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            COUNT(DISTINCT ba.name) AS total_brand_ambassador_count
        FROM `tabEmployee` e
        LEFT JOIN `tabBrand Ambassador` ba
            ON ba.warrior = e.user_id
        GROUP BY e.name
        """,
        as_dict=True,
    )

    return {r.employee: int(r.total_brand_ambassador_count or 0) for r in rows}
