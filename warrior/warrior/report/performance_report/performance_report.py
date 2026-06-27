import frappe
from frappe.utils import getdate, nowdate, is_invalid_date_string, flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    from_date, to_date = get_date_range(filters)
    columns = get_columns()
    data = get_data(from_date, to_date)
    chart = get_chart(data)
    report_summary = get_report_summary(data)
    return columns, data, None, chart, report_summary


def get_columns():
    return [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 180},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Level", "fieldname": "hierarchy_level", "fieldtype": "Int", "width": 70},
        {"label": "From Date", "fieldname": "from_date", "fieldtype": "Date", "width": 100},
        {"label": "To Date", "fieldname": "to_date", "fieldtype": "Date", "width": 100},
        {"label": "No. of Orders", "fieldname": "no_of_orders", "fieldtype": "Int", "width": 110},
        {"label": "Order Amount", "fieldname": "order_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Receipt Amount", "fieldname": "receipt_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Invoice Amount", "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Salary", "fieldname": "salary_amount", "fieldtype": "Currency", "width": 120},
        {"label": "Fuel Expense", "fieldname": "fuel_expense", "fieldtype": "Currency", "width": 120},
        {"label": "Other Expense", "fieldname": "other_expense", "fieldtype": "Currency", "width": 120},
        {"label": "Expense Sanction Amount", "fieldname": "expense_sanction_amount", "fieldtype": "Currency", "width": 170},
        {"label": "Expense %", "fieldname": "expense_percent", "fieldtype": "Percent", "width": 100},
    ]


def get_date_range(filters):
    from_date = parse_date(filters.get("from_date"))
    to_date = parse_date(filters.get("to_date"))

    if not from_date and not to_date:
        today = getdate(nowdate())
        return today, today

    if not from_date:
        from_date = to_date
    if not to_date:
        to_date = from_date
    if from_date > to_date:
        from_date, to_date = to_date, from_date

    return from_date, to_date


def parse_date(value):
    if not value or is_invalid_date_string(value):
        return None
    return getdate(value)


def get_summary_base_rows(data):
    manager_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if manager_employee:
        manager_rows = [row for row in data if row.get("employee") == manager_employee]
        if manager_rows:
            return manager_rows
    return [row for row in data if int(row.get("indent") or 0) == 0]


def get_report_summary(data):
    top_rows = get_summary_base_rows(data)

    total_orders = sum(int(row.get("no_of_orders") or 0) for row in top_rows)
    total_order_amount = sum(flt(row.get("order_amount") or 0) for row in top_rows)
    total_receipt_amount = sum(flt(row.get("receipt_amount") or 0) for row in top_rows)
    total_invoice_amount = sum(flt(row.get("invoice_amount") or 0) for row in top_rows)

    return [
        {
            "label": "Orders",
            "value": total_orders,
            "datatype": "Int",
            "indicator": "Blue",
        },
        {
            "label": "Order Amount",
            "value": total_order_amount,
            "datatype": "Currency",
            "indicator": "Green",
        },
        {
            "label": "Receipt Amount",
            "value": total_receipt_amount,
            "datatype": "Currency",
            "indicator": "Orange",
        },
        {
            "label": "Invoice Amount",
            "value": total_invoice_amount,
            "datatype": "Currency",
            "indicator": "Red",
        },
    ]


def get_chart(data):
    top_rows = get_summary_base_rows(data)
    if not top_rows:
        return None

    total_order_amount = sum(flt(row.get("order_amount") or 0) for row in top_rows)
    total_receipt_amount = sum(flt(row.get("receipt_amount") or 0) for row in top_rows)
    total_invoice_amount = sum(flt(row.get("invoice_amount") or 0) for row in top_rows)

    return {
        "data": {
            "labels": ["Order Amount", "Receipt Amount", "Invoice Amount"],
            "datasets": [
                {
                    "name": "Amount",
                    "values": [total_order_amount, total_receipt_amount, total_invoice_amount],
                }
            ],
        },
        "type": "bar",
        "colors": ["#4C78A8"],
    }


# ✅ MAIN FILTER (Sales + Marketing + hierarchy safe)
def filter_tree(report_employees, manager_employee, ceo_employee):
    emp_map = {e.name: e for e in report_employees}

    children_map = {}
    for emp in report_employees:
        parent = emp.reports_to or None
        children_map.setdefault(parent, []).append(emp.name)

    def is_valid(emp):
        role = (getattr(emp, "custom_default_role", "") or "").lower()
        dept = (getattr(emp, "department", "") or "").lower()

        return (
            "sales" in role
            or "marketing" in role
            or "sales" in dept
            or "marketing" in dept
        )

    keep = set()

    def dfs(emp_id):
        emp = emp_map.get(emp_id)
        if not emp:
            return False

        match = is_valid(emp)

        for child in children_map.get(emp_id, []):
            if dfs(child):
                match = True

        # always keep manager & CEO
        if emp_id in {manager_employee, ceo_employee}:
            match = True

        if match:
            keep.add(emp_id)

        return match

    root = ceo_employee or manager_employee
    if root:
        dfs(root)

    return [emp_map[e] for e in keep if e in emp_map]


def get_data(from_date, to_date):
    NO_EMP = "UNMAPPED_ORDERS"

    employee_rows = get_employee_order_rows(from_date, to_date)

    employee_metrics = {
        row.employee: {
            "employee_name": row.employee_name,
            "no_of_orders": int(row.no_of_orders or 0),
            "order_amount": flt(row.order_amount or 0),
            "receipt_amount": flt(row.receipt_amount or 0),
            "invoice_amount": flt(row.invoice_amount or 0),
        }
        for row in employee_rows
        if row.employee
    }
    unmapped = get_unmapped_order_metrics(from_date, to_date)
    if unmapped:
        employee_metrics[NO_EMP] = {
            "employee_name": "Unmapped Orders",
            "no_of_orders": int(unmapped.get("no_of_orders") or 0),
            "order_amount": flt(unmapped.get("order_amount") or 0),
            "receipt_amount": flt(unmapped.get("receipt_amount") or 0),
            "invoice_amount": flt(unmapped.get("invoice_amount") or 0),
        }

    manager_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    if manager_employee:
        report_employees = get_hierarchy_scope_for_user(manager_employee)
    else:
        report_employees = get_employees_with_ancestors(set(employee_metrics.keys()))

    ceo_employee = get_top_ceo(manager_employee) if manager_employee else None

    # ✅ APPLY CLEAN TREE FILTER
    if report_employees:
        report_employees = filter_tree(report_employees, manager_employee, ceo_employee)

    # Hard exclude Founder Office + Default role rows from report output
    if report_employees:
        keep_roots = {x for x in [manager_employee, ceo_employee] if x}
        cleaned = []
        for emp in report_employees:
            dept = (getattr(emp, "department", "") or "").strip().lower()
            role = (getattr(emp, "custom_default_role", "") or "").strip().lower()
            if emp.name not in keep_roots and dept == "founder office - spl" and role == "default":
                continue
            cleaned.append(emp)
        report_employees = cleaned

    # ✅ ADD MISSING EMPLOYEES (IMPORTANT FIX)
    if report_employees:
        metric_employees = set(employee_metrics.keys())
        hierarchy_employees = {emp.name for emp in report_employees}
        missing_metric_employees = metric_employees - hierarchy_employees

        if missing_metric_employees:
            report_employees.extend(
                get_employees_with_ancestors(missing_metric_employees)
            )

        # remove duplicates
        unique = {}
        for emp in report_employees:
            unique[emp.name] = emp

        report_employees = list(unique.values())

    unmapped_parent = ceo_employee or manager_employee or ""
    if NO_EMP in employee_metrics and unmapped_parent:
        employee_names = {emp.name for emp in report_employees}
        if unmapped_parent not in employee_names:
            parent_doc = frappe.db.get_value(
                "Employee",
                unmapped_parent,
                ["name", "employee_name", "reports_to", "department"],
                as_dict=1,
            )
            if parent_doc:
                report_employees.append(frappe._dict(parent_doc))
                employee_names.add(parent_doc.name)
        if NO_EMP not in employee_names:
            report_employees.append(
                frappe._dict(
                    {
                        "name": NO_EMP,
                        "employee_name": "Unmapped Orders",
                        "reports_to": unmapped_parent,
                        "department": "",
                    }
                )
            )

    if not report_employees:
        return []

    # ---------------- REMAINING LOGIC SAME ----------------
    employee_map = {emp.name: emp for emp in report_employees}
    employee_ids = list(employee_map.keys())
    salary_map = get_salary_map(employee_ids, from_date, to_date) if employee_ids else {}
    expense_map = get_expense_map(employee_ids, from_date, to_date) if employee_ids else {}

    children_map = {}
    for emp in report_employees:
        parent = emp.reports_to or ""
        children_map.setdefault(parent, []).append(emp.name)

    result = []

    def add_node(emp_id, level=0):
        emp = employee_map[emp_id]
        metric = employee_metrics.get(emp_id, {})
        salary_amount = flt(salary_map.get(emp_id) or 0)
        fuel_expense = flt((expense_map.get(emp_id) or {}).get("fuel") or 0)
        other_expense = flt((expense_map.get(emp_id) or {}).get("other") or 0)
        expense_sanction_amount = fuel_expense + other_expense
        order_amount=flt(metric.get("order_amount") or 0)
        agg = {
            "no_of_orders": int(metric.get("no_of_orders") or 0),
            "order_amount": flt(metric.get("order_amount") or 0),
            "receipt_amount": flt(metric.get("receipt_amount") or 0),
            "invoice_amount": flt(metric.get("invoice_amount") or 0),
            "salary_amount" :salary_amount,
            "fuel_expense" : fuel_expense,
            "other_expense" : other_expense,
            "expense_sanction_amount" : expense_sanction_amount,
        "expense_percent" : ((expense_sanction_amount / order_amount) * 100 if order_amount else 0.0)
        }

        for child in children_map.get(emp_id, []):
            if child not in employee_map:
                continue
            child_vals = add_node(child, level + 1)
            for k in agg:
                agg[k] += child_vals[k]

        result.append({
            "employee": emp_id,
            "employee_name": emp.employee_name,
            "hierarchy_level": level,
            "reports_to": emp.reports_to or "",
            "indent": level,
            "is_group": 1 if children_map.get(emp_id) else 0,
            "from_date": from_date,
            "to_date": to_date,
            **agg
        })

        return agg

    roots = []

    is_ceo_login = manager_employee and ceo_employee and manager_employee == ceo_employee

    if is_ceo_login:
        # CEO → normal hierarchy
        roots = [ceo_employee]

    else:
        # ✅ NON-CEO → UNMAPPED FIRST
        if NO_EMP in employee_map:
            roots.append(NO_EMP)

        if manager_employee:
            roots.append(manager_employee)

        elif ceo_employee:
            roots.append(ceo_employee)

    for root in roots:
        if root:
            add_node(root)
    result.reverse()
    return result

def get_employee_order_rows(from_date, to_date):
    return frappe.db.sql(
        """
        SELECT
            x.employee,
            x.employee_name,
            COUNT(x.sales_order) AS no_of_orders,
            SUM(x.order_amount) AS order_amount,
            SUM(x.invoice_amount) AS invoice_amount,
            SUM(x.receipt_amount) AS receipt_amount

        FROM (

            SELECT
                sp.employee AS employee,
                e.employee_name AS employee_name,
                so.name AS sales_order,
                so.grand_total AS order_amount,

                /* ✅ Invoice (NO DOUBLE COUNT) */
                COALESCE(inv.invoice_amount, 0) AS invoice_amount,

                /* ✅ Receipt = advance_paid */
                COALESCE(so.advance_paid, 0) AS receipt_amount

            FROM `tabSales Team` st

            INNER JOIN `tabSales Order` so
                ON so.name = st.parent
                AND st.parenttype = 'Sales Order'
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
                          AND btr.transfer_type ="Bank Transfer"
                          AND btr.status = 'Unsettled'
                    )
                )
            INNER JOIN `tabSales Person` sp
                ON sp.name = st.sales_person
                AND IFNULL(sp.employee, '') != ''

            INNER JOIN `tabEmployee` e
                ON e.name = sp.employee


            /* ✅ FIXED INVOICE (NO DUPLICATION) */
            LEFT JOIN (
                SELECT
                    sales_order,
                    SUM(invoice_amount) AS invoice_amount
                FROM (
                    SELECT
                        sii.sales_order,
                        si.name AS invoice,
                        si.grand_total AS invoice_amount
                    FROM `tabSales Invoice` si
                    INNER JOIN `tabSales Invoice Item` sii
                        ON sii.parent = si.name
                    WHERE si.docstatus = 1
                      AND IFNULL(sii.sales_order, '') != ''
                    GROUP BY si.name, sii.sales_order, si.grand_total
                ) t
                GROUP BY sales_order
            ) inv ON inv.sales_order = so.name


            GROUP BY
                sp.employee,
                e.employee_name,
                so.name,
                so.grand_total,
                inv.invoice_amount,
                so.advance_paid

        ) x

        GROUP BY
            x.employee,
            x.employee_name
        """,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )


def get_employees_with_ancestors(employee_ids):
    required = set(employee_ids)
    frontier = set(employee_ids)

    while frontier:
        rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", list(frontier)],"status":"Active"},
            fields=["name", "reports_to"],
            limit_page_length=0,
        )
        parents = {row.reports_to for row in rows if row.reports_to and row.reports_to not in required}
        frontier = parents
        required.update(parents)

    return frappe.get_all(
        "Employee",
        filters={"name": ["in", list(required)],"status":"Active"},
        fields=["name", "employee_name", "reports_to"],
        limit_page_length=0,
    )


def get_hierarchy_scope_for_user(manager_employee):
    all_employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "reports_to", "department", "custom_default_role"],
        limit_page_length=0,
    )
    employee_map = {emp.name: emp for emp in all_employees}
    if manager_employee not in employee_map:
        return []

    children_map = {}
    for emp in all_employees:
        children_map.setdefault(emp.reports_to or "", []).append(emp.name)

    scoped_ids = []
    seen = set()

    def collect(emp_id):
        if emp_id in seen or emp_id not in employee_map:
            return
        seen.add(emp_id)
        scoped_ids.append(emp_id)
        for child_id in children_map.get(emp_id, []):
            collect(child_id)

    collect(manager_employee)

    # add upward chain so CEO/parents appear above manager in tree
    current = employee_map[manager_employee].reports_to
    while current and current in employee_map and current not in seen:
        seen.add(current)
        scoped_ids.append(current)
        current = employee_map[current].reports_to

    return [employee_map[emp_id] for emp_id in scoped_ids]


def get_manager_chain(manager_employee):
    if not manager_employee:
        return []

    chain = []
    seen = set()
    current = manager_employee

    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        current = frappe.db.get_value("Employee", current, "reports_to")

    return chain


def get_top_ceo(manager_employee):
    if not manager_employee:
        return None

    current = manager_employee
    seen = set()
    top_ceo = None

    while current and current not in seen:
        seen.add(current)
        row = frappe.db.get_value(
            "Employee",
            current,
            ["designation", "reports_to"],
            as_dict=1,
        )
        if not row:
            break
        if row.designation and "ceo" in row.designation.lower():
            top_ceo = current
        current = row.reports_to

    return top_ceo
def get_unmapped_order_metrics(from_date, to_date):
    rows = frappe.db.sql(
        """
        SELECT
            COUNT(*) AS no_of_orders,
            SUM(x.order_amount) AS order_amount,
            SUM(x.invoice_amount) AS invoice_amount,
            SUM(x.receipt_amount) AS receipt_amount

        FROM (

            SELECT
                so.name AS sales_order,
                so.grand_total AS order_amount,

                COALESCE(inv.invoice_amount, 0) AS invoice_amount,

                /* ✅ USING advance_paid */
                COALESCE(so.advance_paid, 0) AS receipt_amount

            FROM `tabSales Order` so


            /* SALES TEAM FILTER */
            LEFT JOIN `tabSales Team` st
                ON st.parent = so.name
                AND st.parenttype = 'Sales Order'

            LEFT JOIN `tabSales Person` sp
                ON sp.name = st.sales_person


            /* INVOICE */
            LEFT JOIN (
                SELECT
                    t.sales_order,
                    SUM(t.invoice_amount) AS invoice_amount
                FROM (
                    SELECT
                        sii.sales_order,
                        si.name AS invoice,
                        si.grand_total AS invoice_amount
                    FROM `tabSales Invoice Item` sii
                    INNER JOIN `tabSales Invoice` si
                        ON si.name = sii.parent
                        AND si.docstatus = 1
                    WHERE IFNULL(sii.sales_order, '') != ''
                    GROUP BY si.name, sii.sales_order, si.grand_total
                ) t
                GROUP BY t.sales_order
            ) inv ON inv.sales_order = so.name


            WHERE so.docstatus = 1
              AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s
              AND COALESCE(NULLIF(TRIM(so.custom_dispatch_status), ''), so.status) NOT IN ('CANCELLED', 'REFUNDED')
                AND (
                    COALESCE(so.advance_paid, 0) > 0
                    OR EXISTS (
                        SELECT 1
                        FROM `tabBank Transfer Request` btr
                        WHERE btr.sales_order = so.name
                          AND btr.docstatus = 0
                          AND btr.transfer_type ="Bank Transfer"
                          AND btr.status = 'Unsettled'
                    )
                )
            GROUP BY
                so.name,
                so.grand_total,
                inv.invoice_amount,
                so.advance_paid

            /* UNMAPPED SALES PERSON */
            HAVING MAX(CASE WHEN IFNULL(sp.employee, '') != '' THEN 1 ELSE 0 END) = 0

        ) x
        """,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )

    return rows[0] if rows else None

def get_salary_map(employee_ids, from_date, to_date):
    rows = frappe.db.sql(
        """
        SELECT
            ss.employee,
            SUM(ss.net_pay) AS salary_amount
        FROM `tabSalary Slip` ss
        WHERE ss.docstatus = 1
          AND ss.employee IN %(employees)s
          AND ss.start_date <= %(to_date)s
          AND ss.end_date >= %(from_date)s
        GROUP BY ss.employee
        """,
        {"employees": tuple(employee_ids), "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
    return {row.employee: flt(row.salary_amount or 0) for row in rows}


def get_expense_map(employee_ids, from_date, to_date):
    rows = frappe.db.sql(
        """
        SELECT
            ec.employee,
            ecd.expense_type,
            SUM(ecd.amount) AS amount
        FROM `tabExpense Claim` ec
        INNER JOIN `tabExpense Claim Detail` ecd ON ecd.parent = ec.name
        WHERE ec.docstatus = 1
          AND ec.employee IN %(employees)s
          AND ecd.expense_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY ec.employee, ecd.expense_type
        """,
        {"employees": tuple(employee_ids), "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
    frappe.log_error(message=str(employee_ids),title="Expense employee")
    expense_map = {}
    for row in rows:
        employee = row.employee
        expense_type = (row.expense_type or "").strip().lower()
        amount = flt(row.amount or 0)

        if employee not in expense_map:
            expense_map[employee] = {"fuel": 0.0, "other": 0.0}

        if "fuel" in expense_type:
            expense_map[employee]["fuel"] += amount
        else:
            expense_map[employee]["other"] += amount

    return expense_map
