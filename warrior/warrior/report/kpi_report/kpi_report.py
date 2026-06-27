import frappe
from frappe.utils import getdate, nowdate, add_days, get_time


def format_time_only(value):
    if not value:
        return None
    try:
        return get_time(value).strftime("%H:%M:%S")
    except Exception:
        return None


def format_seconds_hms(seconds):
    if seconds is None:
        return None
    total_seconds = max(int(seconds), 0)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# --------------------------------------------------
# 🚀 MAIN
# --------------------------------------------------
def execute(filters=None):
    filters = frappe._dict(filters or {})

    from_date, to_date = get_date_range(filters)

    columns = get_columns()
    data = get_data(filters, from_date, to_date)

    return columns, data


# --------------------------------------------------
# 📊 COLUMNS
# --------------------------------------------------
def get_columns():
    return [
        {"label": "Employee", "fieldname": "employee_name", "width": 220},
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": "Punch In", "fieldname": "punch_in", "fieldtype": "Time", "width": 110},
        {"label": "Punch Out", "fieldname": "punch_out", "fieldtype": "Time", "width": 110},
        {"label": "Work Gap", "fieldname": "work_gap", "fieldtype": "Data", "width": 110},
        {"label": "1st Visit Time", "fieldname": "first_visit_time", "fieldtype": "Time", "width": 120},
        {"label": "1st Call Time", "fieldname": "first_call_time", "fieldtype": "Time", "width": 120},
        {"label": "Visits", "fieldname": "total_visits", "fieldtype": "Int", "width": 100},
        {"label": "Calls", "fieldname": "total_calls", "fieldtype": "Int", "width": 100},
        {"label": "Total Call Duration", "fieldname": "total_call_duration", "fieldtype": "Data", "width": 150},
        {"label": "Customer Calls", "fieldname": "customer_calls", "fieldtype": "Int", "width": 120},
        {"label": "Personal Calls", "fieldname": "personal_calls", "fieldtype": "Int", "width": 120},
        {"label": "Success Calls", "fieldname": "success_calls", "fieldtype": "Int", "width": 120},
        {"label": "Orders", "fieldname": "orders", "fieldtype": "Int", "width": 100},
        {"label": "Order Amount", "fieldname": "order_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Receipt Amount", "fieldname": "receipt", "fieldtype": "Currency", "width": 130},
        {"label": "Pending Amount", "fieldname": "pending_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Invoice Amount", "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 130},
        {"label": "Return Amount", "fieldname": "return_amount_crn", "fieldtype": "Currency", "width": 130},
    ]


# --------------------------------------------------
# 📅 DATE RANGE
# --------------------------------------------------
def get_date_range(filters):
    if not filters.get("from_date") and not filters.get("to_date"):
        today = getdate(nowdate())
        return today, today

    return getdate(filters.from_date), getdate(filters.to_date)


def get_all_dates(from_date, to_date):
    dates = []
    d = from_date
    while d <= to_date:
        dates.append(d)
        d = add_days(d, 1)
    return dates


# --------------------------------------------------
# 📊 MAIN DATA
# --------------------------------------------------
def get_data(filters, from_date, to_date):
    dates = get_all_dates(from_date, to_date)
    kpi_map = get_kpi_map(from_date, to_date)
    attendance_map = get_attendance_map(from_date, to_date)
    employee_metrics = {emp_id for (emp_id, _d) in kpi_map.keys() if emp_id}
    manager_employee = get_manager_employee()

    if manager_employee:
        report_employees = get_hierarchy_scope_for_user(manager_employee)
    else:
        report_employees = get_employees_with_ancestors(employee_metrics)

    ceo_employee = get_top_ceo(manager_employee) if manager_employee else None

    if report_employees:
        report_employees = filter_tree(report_employees, manager_employee, ceo_employee)

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

    if report_employees:
        hierarchy_employees = {emp.name for emp in report_employees}
        missing_metric_employees = employee_metrics - hierarchy_employees

        if missing_metric_employees:
            report_employees.extend(get_employees_with_ancestors(missing_metric_employees))

        unique = {}
        for emp in report_employees:
            unique[emp.name] = emp
        report_employees = list(unique.values())

    unmapped_parent = ceo_employee or manager_employee or ""
    if not report_employees:
        return []

    emp_map = {e.name: e for e in report_employees}

    children_map = {}
    for e in report_employees:
        parent = e.reports_to or ""
        children_map.setdefault(parent, []).append(e.name)

    root_employees = []
    if manager_employee and manager_employee in emp_map:
        root_employees = [manager_employee]
    elif ceo_employee and ceo_employee in emp_map:
        root_employees = [ceo_employee]
    elif unmapped_parent and unmapped_parent in emp_map:
        root_employees = [unmapped_parent]
    else:
        root_employees = sorted(children_map.get("", []))
        if not root_employees:
            root_employees = sorted(emp_map.keys())

    result = []

    metric_fields = [
        "total_visits",
        "total_calls",
        "total_call_duration",
        "customer_calls",
        "personal_calls",
        "success_calls",
        "orders",
        "order_amount",
        "receipt",
        "pending_amount",
        "invoice_amount",
        "return_amount_crn",
    ]

    def merge_metrics(base, extra):
        for field in metric_fields:
            base[field] += extra.get(field, 0) or 0
        return base

    def own_metrics_for_date(emp_id, d):
        kpi = kpi_map.get((emp_id, d), get_empty_kpi())
        att = attendance_map.get((emp_id, d), {})
        punch_in = att.get("in_time")
        punch_out = att.get("out_time")
        first_activity = kpi.get("first_visit_time") or kpi.get("first_call_time")
        gap_minutes = 0
        if punch_in and first_activity:
            gap_minutes = int(time_diff_in_seconds(first_activity, punch_in) / 60)

        return {
            "punch_in": punch_in,
            "punch_out": punch_out,
            "work_gap": gap_minutes,
            "first_visit_time": kpi.get("first_visit_time"),
            "first_call_time": kpi.get("first_call_time"),
            "total_visits": kpi.get("total_visits") or 0,
            "total_calls": kpi.get("total_calls") or 0,
            "total_call_duration": kpi.get("total_call_duration") or 0,
            "customer_calls": kpi.get("customer_calls") or 0,
            "personal_calls": kpi.get("personal_calls") or 0,
            "success_calls": kpi.get("success_calls") or 0,
            "orders": kpi.get("orders") or 0,
            "order_amount": kpi.get("order_amount") or 0,
            "receipt": kpi.get("receipt") or 0,
            "pending_amount": max((kpi.get("order_amount") or 0) - (kpi.get("receipt") or 0), 0),
            "invoice_amount": kpi.get("invoice_amount") or 0,
            "return_amount_crn": kpi.get("return_amount_crn") or 0,
        }

    def aggregate_subtree(emp_id):
        aggregated_by_date = {}
        for d in dates:
            own = own_metrics_for_date(emp_id, d)
            aggregated_by_date[d] = own

        for child_id in children_map.get(emp_id, []):
            child_agg = aggregate_subtree(child_id)
            for d in dates:
                merge_metrics(aggregated_by_date[d], child_agg[d])

                child_first_visit = child_agg[d].get("first_visit_time")
                if (
                    child_first_visit
                    and (
                        not aggregated_by_date[d].get("first_visit_time")
                        or child_first_visit < aggregated_by_date[d]["first_visit_time"]
                    )
                ):
                    aggregated_by_date[d]["first_visit_time"] = child_first_visit

                child_first_call = child_agg[d].get("first_call_time")
                if (
                    child_first_call
                    and (
                        not aggregated_by_date[d].get("first_call_time")
                        or child_first_call < aggregated_by_date[d]["first_call_time"]
                    )
                ):
                    aggregated_by_date[d]["first_call_time"] = child_first_call

        return aggregated_by_date

    def build_tree(emp_id, level=0):

        emp = emp_map.get(emp_id)
        if not emp:
            return

        subtree_aggregates = aggregate_subtree(emp_id)

        result.append({
            "employee_name": f"{emp.name} - {emp.employee_name}",
            "indent": level,
            "parent_employee": emp.reports_to or "",
            "is_manager": 1 if emp_id == manager_employee else 0,
        })

        for d in dates:
            kpi = subtree_aggregates[d]
            punch_in_val = kpi.get("punch_in")
            first_activity_val = kpi.get("first_visit_time") or kpi.get("first_call_time")
            work_gap_seconds = 0
            if punch_in_val and first_activity_val:
                work_gap_seconds = int(time_diff_in_seconds(first_activity_val, punch_in_val))

            result.append({
                "employee_name": f"{emp.name} - {emp.employee_name}",
                "date": d,
                "indent": level + 1,
                "parent_employee": emp_id,

                "punch_in": format_time_only(punch_in_val),
                "punch_out": format_time_only(kpi.get("punch_out")),
                "work_gap": format_seconds_hms(work_gap_seconds),

                "first_visit_time": format_time_only(kpi.get("first_visit_time")),
                "first_call_time": format_time_only(kpi.get("first_call_time")),

                "total_visits": kpi.get("total_visits"),
                "total_calls": kpi.get("total_calls"),
                "total_call_duration": format_seconds_hms(kpi.get("total_call_duration")),
                "customer_calls": kpi.get("customer_calls"),
                "personal_calls": kpi.get("personal_calls"),
                "success_calls": kpi.get("success_calls"),
                "orders": kpi.get("orders"),
                "order_amount": kpi.get("order_amount"),
                "receipt": kpi.get("receipt"),
                "pending_amount": kpi.get("pending_amount"),
                "invoice_amount": kpi.get("invoice_amount"),
                "return_amount_crn": kpi.get("return_amount_crn"),
            })

        for child in children_map.get(emp_id, []):
            build_tree(child, level + 1)

    for root in root_employees:
        build_tree(root)

    return result


def get_manager_employee():
    return frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
    )


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


def get_employees_with_ancestors(employee_ids):
    if not employee_ids:
        return []

    required = set(employee_ids)
    frontier = set(employee_ids)

    while frontier:
        rows = frappe.get_all(
            "Employee",
            filters={"name": ["in", list(frontier)], "status": "Active"},
            fields=["name", "reports_to"],
            limit_page_length=0,
        )
        parents = {row.reports_to for row in rows if row.reports_to and row.reports_to not in required}
        frontier = parents
        required.update(parents)

    return frappe.get_all(
        "Employee",
        filters={"name": ["in", list(required)], "status": "Active"},
        fields=["name", "employee_name", "reports_to", "department", "custom_default_role"],
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

    current = employee_map[manager_employee].reports_to
    while current and current in employee_map and current not in seen:
        seen.add(current)
        scoped_ids.append(current)
        current = employee_map[current].reports_to

    return [employee_map[emp_id] for emp_id in scoped_ids]


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
            {"name": current, "status": "Active"},
            ["designation", "reports_to"],
            as_dict=1,
        )
        if not row:
            break
        if row.designation and "ceo" in row.designation.lower():
            top_ceo = current
        current = row.reports_to

    return top_ceo

from frappe.utils import time_diff_in_seconds

# def own_metrics_for_date(emp_id, d):
#     kpi = kpi_map.get((emp_id, d), get_empty_kpi())
#     att = attendance_map.get((emp_id, d), {})

#     punch_in = att.get("in_time")
#     punch_out = att.get("out_time")

#     first_activity = kpi.get("first_visit_time") or kpi.get("first_call_time")

#     gap_minutes = 0
#     if punch_in and first_activity:
#         gap_minutes = int(time_diff_in_seconds(first_activity, punch_in) / 60)

#     return {
#         "first_visit_time": kpi.get("first_visit_time"),
#         "first_call_time": kpi.get("first_call_time"),

#         "punch_in": punch_in,
#         "punch_out": punch_out,
#         "work_gap": gap_minutes,

#         "total_visits": kpi.get("total_visits") or 0,
#         "total_calls": kpi.get("total_calls") or 0,
#         "success_calls": kpi.get("success_calls") or 0,
#         "orders": kpi.get("orders") or 0,
#         "order_amount": kpi.get("order_amount") or 0,
#         "receipt": kpi.get("receipt") or 0,
#     }


def get_attendance_map(from_date, to_date):

    rows = frappe.db.sql("""
        SELECT
            ec.employee,
            DATE(ec.time) AS attendance_date,

            MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS in_time,
            MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS out_time

        FROM `tabEmployee Checkin` ec

        WHERE ec.time >= %(from_date)s
          AND ec.time < DATE_ADD(%(to_date)s, INTERVAL 1 DAY)

        GROUP BY ec.employee, DATE(ec.time)
    """, {
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    return {(r.employee, r.attendance_date): r for r in rows}


def get_kpi_map(from_date, to_date):

    to_date_next = add_days(to_date, 1)

    rows = frappe.db.sql("""
        SELECT
            t.employee,
            t.date,

            MIN(t.visit_time) AS first_visit_time,
            MIN(t.call_time) AS first_call_time,

            COUNT(DISTINCT t.visit_id) AS total_visits,
            COUNT(DISTINCT t.call_id) AS total_calls,
            SUM(t.call_duration) AS total_call_duration,
            COUNT(DISTINCT CASE
                WHEN t.call_belongs_to = 'Customer' THEN t.call_id
            END) AS customer_calls,
            COUNT(DISTINCT CASE
                WHEN t.call_belongs_to = 'Personal' THEN t.call_id
            END) AS personal_calls,

            COUNT(DISTINCT CASE
                WHEN t.call_status = 'SUCCESS' AND t.call_belongs_to = 'Customer' THEN t.call_id
            END) AS success_calls,

            COUNT(DISTINCT t.sales_order) AS orders,
            SUM(t.order_amount) AS order_amount,
            SUM(t.invoice_amount) AS invoice_amount,
            SUM(t.receipt_amount) AS receipt,
            SUM(t.return_amount_crn) AS return_amount_crn

        FROM (

            -- ✅ VISITS
            SELECT
                e.name AS employee,
                DATE(cv.visit_date) AS date,
                cv.name AS visit_id,
                NULL AS call_id,
                NULL AS call_status,
                NULL AS call_belongs_to,
                CONCAT(cv.visit_date, ' ', cv.visit_time) AS visit_time,
                NULL AS call_time,
                0 AS call_duration,
                NULL AS sales_order,
                0 AS order_amount,
                0 AS invoice_amount,
                0 AS receipt_amount,
                0 AS return_amount_crn
            FROM `tabVisit` cv
            INNER JOIN `tabEmployee` e ON e.user_id = cv.owner
                AND e.status = 'Active'
            WHERE cv.visit_date >= %(from_date)s
              AND cv.visit_date < %(to_date_next)s

            UNION ALL

            -- ✅ CALLS
            SELECT
                e.name,
                DATE(cc.posting_datetime),
                NULL,
                cc.name,
                cc.call_status,
                cc.call_belongs_to,
                NULL,
                cc.posting_datetime,
                COALESCE(cc.call_duration, 0),
                NULL,
                0,
                0,
                0,
                0
            FROM `tabCall Detail Entry` cc
            INNER JOIN `tabEmployee` e ON e.user_id = cc.owner
                AND e.status = 'Active'
            WHERE cc.posting_datetime >= %(from_date)s
              AND cc.posting_datetime < %(to_date_next)s

            UNION ALL

            -- ✅ ORDERS + INVOICE + RECEIPT (MERGED CLEANLY)
            SELECT
                sp.employee,
                DATE(so.transaction_date),
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                NULL,
                0,
                so.name,
                so.grand_total,

                /* ✅ INVOICE (NO DUPLICATION) */
                COALESCE(inv.invoice_amount, 0),

                /* ✅ RECEIPT = advance_paid */
                COALESCE(so.advance_paid, 0),

                /* ✅ RETURN AMOUNT (CRN) */
                COALESCE(inv.return_amount_crn, 0)

            FROM `tabSales Order` so

            INNER JOIN `tabSales Team` st ON st.parent = so.name
            INNER JOIN `tabSales Person` sp ON sp.name = st.sales_person

            LEFT JOIN (
                SELECT
                    sales_order,
                    SUM(invoice_amount) AS invoice_amount,
                    SUM(return_amount_crn) AS return_amount_crn
                FROM (
                    SELECT DISTINCT
                        si.name AS invoice,
                        sii.sales_order,
                        CASE WHEN IFNULL(si.is_return, 0) = 0 THEN si.grand_total ELSE 0 END AS invoice_amount,
                        CASE WHEN IFNULL(si.is_return, 0) = 1 THEN ABS(si.grand_total) ELSE 0 END AS return_amount_crn
                    FROM `tabSales Invoice` si
                    INNER JOIN `tabSales Invoice Item` sii
                        ON sii.parent = si.name
                    WHERE si.docstatus = 1
                      AND IFNULL(sii.sales_order, '') != ''
                ) t
                GROUP BY sales_order
            ) inv ON inv.sales_order = so.name

            WHERE so.docstatus = 1
              AND sp.employee IS NOT NULL
              AND so.transaction_date >= %(from_date)s
              AND so.transaction_date < %(to_date_next)s
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
        ) t
        GROUP BY t.employee, t.date
        ORDER BY t.employee, t.date
    """, {
        "from_date": from_date,
        "to_date_next": to_date_next
    }, as_dict=True)

    return {(r.employee, r.date): r for r in rows}
# --------------------------------------------------
# 🧱 DEFAULT KPI
# --------------------------------------------------
def get_empty_kpi():
    return {
        "first_visit_time": None,
        "first_call_time": None,
        "total_visits": 0,
        "total_calls": 0,
        "total_call_duration": 0,
        "customer_calls": 0,
        "personal_calls": 0,
        "success_calls": 0,
        "orders": 0,
        "order_amount": 0,
        "receipt": 0,
        "pending_amount": 0,
        "invoice_amount": 0,
        "return_amount_crn": 0,
    }
