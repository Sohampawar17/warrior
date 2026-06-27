import frappe
from frappe.utils import getdate, nowdate, flt


# ----------------------------------------
# 🚀 MAIN
# ----------------------------------------
def execute(filters=None):
    filters = frappe._dict(filters or {})

    from_date, to_date = get_date_range(filters)
    stages = get_lead_stages()

    columns = get_columns(stages)
    data = get_data(from_date, to_date, stages)

    return columns, data


# ----------------------------------------
# 📅 DATE RANGE
# ----------------------------------------
def get_date_range(filters):
    if not filters.get("from_date") and not filters.get("to_date"):
        today = getdate(nowdate())
        return today, today

    return getdate(filters.from_date), getdate(filters.to_date)


# ----------------------------------------
# 📊 COLUMNS
# ----------------------------------------
def get_columns(stages):
    cols = [
        {"label": "Employee", "fieldname": "employee_name", "width": 300},
        {"label": "Leads", "fieldname": "leads", "fieldtype": "Int", "width": 100},
        {"label": "Lead Cost", "fieldname": "lead_cost", "fieldtype": "Currency", "width": 120},
        {"label": "Orders", "fieldname": "orders", "fieldtype": "Int", "width": 100},
        {"label": "Order Amount", "fieldname": "order_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Receipt Amount", "fieldname": "receipt", "fieldtype": "Currency", "width": 130},
        {"label": "Pending Amount", "fieldname": "pending_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Invoice Amount", "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Return Amount", "fieldname": "return_amount_crn", "fieldtype": "Currency", "width": 130},
        {"label": "ROI %", "fieldname": "roi", "fieldtype": "Percent", "width": 100},
    ]

    for stage in stages:
        cols.append({
            "label": stage,
            "fieldname": f"stage_{frappe.scrub(stage)}",
            "fieldtype": "Int",
            "width": 120
        })

    return cols


# ----------------------------------------
# 🧠 MAIN DATA
# ----------------------------------------
def get_data(from_date, to_date, stages):

    manager = get_manager()
    if not manager:
        return []

    report_employees = get_hierarchy_scope_for_user(manager)
    if not report_employees:
        return []

    employee_map = {emp.name: emp for emp in report_employees}

    children_map = {}
    for emp in report_employees:
        parent = emp.reports_to or ""
        children_map.setdefault(parent, []).append(emp.name)

    emp_ids = [emp.name for emp in report_employees]
    kpi_map = get_kpi(from_date, to_date, emp_ids)

    result = []

    def add_node(emp_id, level=0):
        emp = employee_map[emp_id]
        metric = kpi_map.get(emp_id, {})

        row = {
            "employee_name": f"{emp.name} : {emp.employee_name}",
            "parent_employee": emp.reports_to or "",
            "indent": level,
            "is_group": 1 if children_map.get(emp_id) else 0,

            "leads": metric.get("leads", 0),
            "lead_cost": metric.get("lead_cost", 0),
            "orders": metric.get("orders", 0),
            "order_amount": metric.get("order_amount", 0),
            "receipt": metric.get("receipt", 0),
            "pending_amount": max(flt(metric.get("order_amount", 0)) - flt(metric.get("receipt", 0)), 0),
            "invoice_amount": metric.get("invoice_amount", 0),
            "return_amount_crn": metric.get("return_amount_crn", 0),
        }

        # Stage values
        for s in stages:
            key = f"stage_{frappe.scrub(s)}"
            row[key] = metric.get(s, 0)

        # Aggregate children
        for child in children_map.get(emp_id, []):
            child_row = add_node(child, level + 1)

            row["leads"] += child_row["leads"]
            row["lead_cost"] += child_row["lead_cost"]
            row["orders"] += child_row["orders"]
            row["order_amount"] += child_row["order_amount"]
            row["receipt"] += child_row["receipt"]
            row["pending_amount"] += child_row["pending_amount"]
            row["invoice_amount"] += child_row["invoice_amount"]
            row["return_amount_crn"] += child_row["return_amount_crn"]

            for s in stages:
                key = f"stage_{frappe.scrub(s)}"
                row[key] += child_row.get(key, 0)

        row["roi"] = (row["lead_cost"] / row["order_amount"] * 100) if row["order_amount"] else 0

        result.append(row)
        return row

    add_node(manager, 0)

    result.reverse()
    return result


# ----------------------------------------
# 👤 GET MANAGER
# ----------------------------------------
def get_manager():
    return frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user},
        "name"
    )


# ----------------------------------------
# 🌳 HIERARCHY
# ----------------------------------------
def get_hierarchy_scope_for_user(manager_employee):

    all_employees = frappe.get_all(
        "Employee",
        filters={"status":"Active"},
        fields=["name", "employee_name", "reports_to"],
        limit_page_length=0,
    )

    employee_map = {emp.name: emp for emp in all_employees}

    children_map = {}
    for emp in all_employees:
        parent = emp.reports_to or ""
        children_map.setdefault(parent, []).append(emp.name)

    result = []

    def collect(emp):
        result.append(employee_map[emp])
        for child in children_map.get(emp, []):
            collect(child)

    collect(manager_employee)

    return result


# ----------------------------------------
# 🧾 KPI QUERY (🔥 FINAL WITH custom_lead_stage)
# ----------------------------------------
def get_kpi(from_date, to_date, emp_ids):

    if not emp_ids:
        return {}

    data = {
        emp_id: {
            "leads": 0,
            "lead_cost": 0,
            "orders": 0,
            "order_amount": 0,
            "receipt": 0,
            "invoice_amount": 0,
            "return_amount_crn": 0,
        }
        for emp_id in emp_ids
    }

    params = {
        "from_date": from_date,
        "to_date": to_date,
        "employees": tuple(emp_ids),
    }

    lead_rows = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            COALESCE(NULLIF(TRIM(l.custom_lead_stage), ''), 'Unknown') AS stage,
            COUNT(DISTINCT l.name) AS leads,
            SUM(IFNULL(camp.custom_per_lead_cost, 0)) AS lead_cost
        FROM `tabToDo` td
        INNER JOIN `tabEmployee` e
            ON e.user_id = td.allocated_to
            AND e.name IN %(employees)s
        INNER JOIN `tabLead` l
            ON l.name = td.reference_name
            AND td.reference_type = 'Lead'
            AND td.status != 'Cancelled'
        LEFT JOIN `tabCampaign` camp
            ON camp.name = l.campaign_name
        WHERE l.creation BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY e.name, stage
        """,
        params,
        as_dict=True,
    )

    for r in lead_rows:
        emp = r.employee
        if emp not in data:
            continue
        leads = int(r.leads or 0)
        data[emp]["leads"] += leads
        data[emp]["lead_cost"] += flt(r.lead_cost or 0)
        data[emp][r.stage] = data[emp].get(r.stage, 0) + leads

    order_receipt_rows = frappe.db.sql(
        """
        WITH base AS (
            SELECT DISTINCT
                e.name AS employee,
                l.mobile_no
            FROM `tabToDo` td
            INNER JOIN `tabEmployee` e
                ON e.user_id = td.allocated_to
                AND e.name IN %(employees)s
            INNER JOIN `tabLead` l
                ON l.name = td.reference_name
                AND td.reference_type = 'Lead'
                AND td.status != 'Cancelled'
            WHERE l.creation BETWEEN %(from_date)s AND %(to_date)s
        ),
        base_so AS (
            SELECT DISTINCT
                b.employee,
                so.name AS sales_order,
                so.grand_total,
                so.advance_paid
            FROM base b
            INNER JOIN `tabCustomer` cust
                ON cust.mobile_no = b.mobile_no
            INNER JOIN `tabSales Order` so
                ON so.customer = cust.name
                AND so.docstatus = 1
                AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
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
        ),
        receipt AS (
            SELECT
                bs.sales_order,
                SUM(IFNULL(bs.advance_paid, 0)) AS receipt_amount
            FROM base_so bs
            GROUP BY bs.sales_order
        ),
        invoice AS (
            SELECT
                sii.sales_order,
                SUM(CASE WHEN IFNULL(si.is_return, 0) = 0 THEN si.grand_total ELSE 0 END) AS invoice_amount,
                SUM(CASE WHEN IFNULL(si.is_return, 0) = 1 THEN ABS(si.grand_total) ELSE 0 END) AS return_amount_crn
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si
                ON si.name = sii.parent
                AND si.docstatus = 1
            WHERE IFNULL(sii.sales_order, '') != ''
            GROUP BY sii.sales_order
        )
        SELECT
            bs.employee,
            COUNT(DISTINCT bs.sales_order) AS orders,
            SUM(bs.grand_total) AS order_amount,
            SUM(IFNULL(receipt.receipt_amount, 0)) AS receipt,
            SUM(IFNULL(invoice.invoice_amount, 0)) AS invoice_amount,
            SUM(IFNULL(invoice.return_amount_crn, 0)) AS return_amount_crn
        FROM base_so bs
        LEFT JOIN receipt ON receipt.sales_order = bs.sales_order
        LEFT JOIN invoice ON invoice.sales_order = bs.sales_order
        GROUP BY bs.employee
        """,
        params,
        as_dict=True,
    )

    for r in order_receipt_rows:
        emp = r.employee
        if emp not in data:
            continue
        data[emp]["orders"] = int(r.orders or 0)
        data[emp]["order_amount"] = flt(r.order_amount or 0)
        data[emp]["receipt"] = flt(r.receipt or 0)
        data[emp]["invoice_amount"] = flt(r.invoice_amount or 0)
        data[emp]["return_amount_crn"] = flt(r.return_amount_crn or 0)

    return data


# ----------------------------------------
# 🎯 LEAD STAGES
# ----------------------------------------
def get_lead_stages():
    stages = frappe.get_all(
        "Lead Stages",
        pluck="name",
        order_by="creation asc"   # or "creation desc" if you want latest first
    )
    return [s.strip() for s in stages]
