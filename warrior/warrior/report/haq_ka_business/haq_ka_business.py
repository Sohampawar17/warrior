import frappe
from frappe.utils import cint, flt, getdate, nowdate

def execute(filters=None):
    filters = frappe._dict(filters or {})
    view = (filters.get("view") or "Customer-wise").lower()

    columns = get_columns(view)
    data = get_data(filters, view)

    summary = get_report_summary(data)
    chart = get_chart(data, filters)

    return columns, data, None, chart, summary


def get_columns(view):
    base = [
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
        {"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 90},

        {"label": "Target", "fieldname": "target", "fieldtype": "Currency", "width": 120},
        {"label": "Orders", "fieldname": "orders_amount", "fieldtype": "Currency", "width": 120},
        {"label": "Collected", "fieldname": "collected_amount", "fieldtype": "Currency", "width": 120},
        {"label": "Invoiced", "fieldname": "invoiced_amount", "fieldtype": "Currency", "width": 120},
        {"label": "Shortfall", "fieldname": "shortfall", "fieldtype": "Currency", "width": 120},

        {"label": "Units", "fieldname": "units", "fieldtype": "Int", "width": 90},
        {"label": "Collection %", "fieldname": "collection_percent", "fieldtype": "Percent", "width": 110},
        {"label": "Invoice %", "fieldname": "invoice_percent", "fieldtype": "Percent", "width": 90},
    ]

    if view == "order-wise":
        base.insert(2, {"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140})
        base.insert(3, {"label": "Order Date", "fieldname": "order_date", "fieldtype": "Date", "width": 100})

    return base


def get_data(filters, view):
    where_so, where_si, params = build_where(filters)
    addr_join = "LEFT JOIN `tabAddress` addr ON addr.name = c.customer_primary_address"
    only_with_target = cint(filters.get("only_with_target") or 1)

    # ---------- ORDER-WISE ----------
    if view == "order-wise":
        rows = frappe.db.sql(
            f"""
            SELECT
                so.customer,
                so.customer_name,
                c.custom_document_value AS dealer_id,
                so.name AS sales_order,
                so.transaction_date AS order_date,
                IFNULL(c.disabled,0) AS disabled,
                so.grand_total AS orders_amount,
                IFNULL(u.units,0) AS units,
                IFNULL(inv.invoiced_amount,0) AS invoiced_amount,
                IFNULL(pay.collected_amount,0) AS collected_amount

            FROM `tabSales Order` so
            JOIN `tabCustomer` c ON c.name = so.customer
            {addr_join}

           LEFT JOIN (
                SELECT parent AS sales_order, CAST(SUM(qty) AS UNSIGNED) AS units
                FROM `tabSales Order Item`
                GROUP BY parent
            ) u ON u.sales_order = so.name

            LEFT JOIN (
                SELECT sii.sales_order, SUM(si.grand_total) AS invoiced_amount
                FROM `tabSales Invoice Item` sii
                JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
                WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
                GROUP BY sii.sales_order
            ) inv ON inv.sales_order = so.name

            -- ✅ COLLECTED = Invoice Payments + Sales Order Advances
            LEFT JOIN (
                SELECT
                    p.sales_order,
                    SUM(p.amount) AS collected_amount
                FROM (
                    -- A) Payments allocated directly to Sales Order (Advance)
                    SELECT
                        per.reference_name AS sales_order,
                        per.allocated_amount AS amount
                    FROM `tabPayment Entry Reference` per
                    JOIN `tabPayment Entry` pe
                        ON pe.name = per.parent
                       AND pe.docstatus = 1
                       AND pe.party_type = 'Customer'
                    WHERE per.reference_doctype = 'Sales Order'

                    UNION ALL

                    -- B) Payments allocated to Sales Invoice mapped back to Sales Order
                    SELECT
                        x.sales_order,
                        per.allocated_amount AS amount
                    FROM (
                        SELECT DISTINCT sii.sales_order, sii.parent AS sales_invoice
                        FROM `tabSales Invoice Item` sii
                        WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
                    ) x
                    JOIN `tabPayment Entry Reference` per
                        ON per.reference_doctype='Sales Invoice'
                       AND per.reference_name=x.sales_invoice
                    JOIN `tabPayment Entry` pe
                        ON pe.name=per.parent
                       AND pe.docstatus=1
                       AND pe.party_type='Customer'
                ) p
                GROUP BY p.sales_order
            ) pay ON pay.sales_order = so.name

            WHERE so.docstatus=1 AND {where_so}
            ORDER BY so.transaction_date DESC, so.name DESC
            """,
            params,
            as_dict=True
        )

        target_map = get_apply_dealership_target_map(rows, filters)

        for r in rows:
            target = flt(target_map.get(r.get("dealer_id")) or 0)
            r["target"] = target
            r["status"] = "BLOCKED" if r.get("disabled") else "ACTIVE"
            r["shortfall"] = max(target - flt(r["invoiced_amount"]), 0)
            r["collection_percent"] = round((flt(r["collected_amount"]) / flt(r["orders_amount"]) * 100), 2) if flt(r["orders_amount"]) else 0
            r["invoice_percent"] = round((flt(r["invoiced_amount"]) / flt(r["orders_amount"]) * 100), 2) if flt(r["orders_amount"]) else 0

        if only_with_target:
            rows = [r for r in rows if flt(r.get("target")) > 0]

        return rows

    # ---------- CUSTOMER-WISE ----------
    rows = frappe.db.sql(
        f"""
        SELECT
            c.name AS customer,
            c.customer_name,
            c.custom_document_value AS dealer_id,
            IFNULL(c.disabled,0) AS disabled,
            IFNULL(SUM(so.grand_total),0) AS orders_amount,
            CAST(IFNULL(SUM(soi.qty),0) AS UNSIGNED) AS units
        FROM `tabCustomer` c
        JOIN `tabSales Order` so ON so.customer=c.name AND so.docstatus=1
        {addr_join}
        LEFT JOIN `tabSales Order Item` soi ON soi.parent=so.name
        WHERE {where_so}
        GROUP BY c.name
        ORDER BY orders_amount DESC
        """,
        params,
        as_dict=True
    )

    inv_map = dict(frappe.db.sql(
    f"""
    SELECT si.customer, SUM(si.grand_total) AS invoiced_amount
    FROM `tabSales Invoice` si
    JOIN `tabCustomer` c ON c.name = si.customer
    {addr_join}
    WHERE si.docstatus=1
      AND {where_si}
    GROUP BY si.customer
    """,
    params,
    as_list=True
))


    # ✅ COLLECTED customer-wise = SO Advances + Invoice Payments
    col_map = dict(frappe.db.sql(
        f"""
        SELECT customer, SUM(amount) AS collected_amount
        FROM (
            -- A) Payments against Sales Order
            SELECT
                so.customer,
                per.allocated_amount AS amount
            FROM `tabPayment Entry Reference` per
            JOIN `tabPayment Entry` pe
                ON pe.name = per.parent
               AND pe.docstatus = 1
               AND pe.party_type = 'Customer'
            JOIN `tabSales Order` so
                ON so.name = per.reference_name
               AND so.docstatus = 1
            JOIN `tabCustomer` c ON c.name = so.customer
            {addr_join}
            WHERE per.reference_doctype = 'Sales Order'
            AND {where_so}
            UNION ALL
            -- B) Payments against Sales Invoice
            SELECT
                si.customer,
                per.allocated_amount AS amount
            FROM `tabPayment Entry Reference` per
            JOIN `tabPayment Entry` pe
                ON pe.name = per.parent
               AND pe.docstatus = 1
               AND pe.party_type = 'Customer'
            JOIN `tabSales Invoice` si
                ON si.name = per.reference_name
               AND si.docstatus = 1
            JOIN `tabCustomer` c ON c.name = si.customer
            {addr_join}
            WHERE per.reference_doctype = 'Sales Invoice'
              AND {where_si}
        ) t
        GROUP BY customer
        """,
        params,
        as_list=True
    ))

    target_map = get_apply_dealership_target_map(rows, filters)

    for r in rows:
        cust = r["customer"]
        target = flt(target_map.get(r.get("dealer_id")) or 0)
        r["invoiced_amount"] = flt(inv_map.get(cust) or 0)
        r["collected_amount"] = flt(col_map.get(cust) or 0)
        r["target"] = target
        r["shortfall"] = max(target - flt(r["invoiced_amount"]), 0)
        r["status"] = "BLOCKED" if r.get("disabled") else "ACTIVE"
        r["collection_percent"] = round((flt(r["collected_amount"]) / flt(r["orders_amount"]) * 100), 2) if flt(r["orders_amount"]) else 0
        r["invoice_percent"] = round((flt(r["invoiced_amount"]) / flt(r["orders_amount"]) * 100), 2) if flt(r["orders_amount"]) else 0

    if only_with_target:
        rows = [r for r in rows if flt(r.get("target")) > 0]

    return rows


def get_apply_dealership_target_map(rows, filters):
    dealer_ids = sorted({r.get("dealer_id") for r in rows if r.get("dealer_id")})
    if not dealer_ids:
        return {}

    from_dt = getdate(filters.get("from_date")) if filters.get("from_date") else getdate(nowdate())
    to_dt = getdate(filters.get("to_date")) if filters.get("to_date") else getdate(nowdate())
    if from_dt and to_dt and from_dt > to_dt:
        from_dt, to_dt = to_dt, from_dt

    ad_rows = frappe.db.sql(
        """
        SELECT
            ad.dealer_id,
            ad.dealership_target,
            DATE(ad.valid_from) AS valid_from,
            DATE(ad.valid_to) AS valid_to
        FROM `tabApply Dealership` ad
        WHERE ad.docstatus = 1
          AND ad.dealer_id IN %(dealer_ids)s
          AND ad.valid_from IS NOT NULL
          AND ad.valid_to IS NOT NULL
          AND DATE(ad.valid_from) <= %(to_dt)s
          AND DATE(ad.valid_to) >= %(from_dt)s
        """,
        {
            "dealer_ids": tuple(dealer_ids),
            "from_dt": from_dt,
            "to_dt": to_dt,
        },
        as_dict=True,
    )

    target_map = {}
    for r in ad_rows:
        did = r.get("dealer_id")
        doc_target = flt(r.get("dealership_target") or 0)
        valid_from = getdate(r.get("valid_from"))
        valid_to = getdate(r.get("valid_to"))

        if not did or doc_target <= 0 or not valid_from or not valid_to or valid_to < valid_from:
            continue

        overlap_start = max(valid_from, from_dt)
        overlap_end = min(valid_to, to_dt)
        if overlap_end < overlap_start:
            continue

        overlap_days = (overlap_end - overlap_start).days + 1
        total_days = (valid_to - valid_from).days + 1
        prorated_target = doc_target * (overlap_days / total_days)
        target_map[did] = flt(target_map.get(did) or 0) + prorated_target

    return target_map

def build_where(filters):
    params = {}

    # common filters (Customer + Address)
    common = ["1=1", "c.customer_group = 'Dealer'"]

    if filters.get("customer"):
        common.append("c.name = %(customer)s")
        params["customer"] = filters["customer"]

    if filters.get("search"):
        common.append("""(
            c.customer_name LIKE %(search)s OR c.name LIKE %(search)s OR c.mobile_no LIKE %(search)s
        )""")
        params["search"] = f"%{filters.search}%"

    if filters.get("state"):
        common.append("addr.state = %(state)s")
        params["state"] = filters["state"]

    if filters.get("district"):
        common.append("addr.custom_district = %(district)s")
        params["district"] = filters["district"]

    if filters.get("tehsil"):
        common.append("addr.custom_tahshil = %(tehsil)s")
        params["tehsil"] = filters["tehsil"]

    # SO date filter
    so_date = []
    if filters.get("from_date") and filters.get("to_date"):
        so_date.append("so.transaction_date BETWEEN %(from_date)s AND %(to_date)s")
        params["from_date"] = filters["from_date"]
        params["to_date"] = filters["to_date"]
    elif filters.get("from_date"):
        so_date.append("so.transaction_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]
    elif filters.get("to_date"):
        so_date.append("so.transaction_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    # SI date filter (same filter values, different column)
    si_date = []
    if filters.get("from_date") and filters.get("to_date"):
        si_date.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
    elif filters.get("from_date"):
        si_date.append("si.posting_date >= %(from_date)s")
    elif filters.get("to_date"):
        si_date.append("si.posting_date <= %(to_date)s")

    where_so = " AND ".join(common + so_date)
    where_si = " AND ".join(common + si_date)

    return where_so, where_si, params


def get_report_summary(data):
    total_target = sum(flt(d.get("target")) for d in data)
    total_orders = sum(flt(d.get("orders_amount")) for d in data)
    total_collected = sum(flt(d.get("collected_amount")) for d in data)
    total_invoiced = sum(flt(d.get("invoiced_amount")) for d in data)
    total_units = sum(flt(d.get("units")) for d in data)
    shortfall = max(total_target - total_invoiced, 0)

    return [
        {
            "label": "Units",
            "value": total_units,
            "datatype": "Int",
            "indicator": "blue",
        },
        {
            "label": "Total Orders",
            "value": total_orders,
            "datatype": "Currency",
            "indicator": "blue",      # 🔵 Orders
        },
        {
            "label": "Total Target",
            "value": total_target,
            "datatype": "Currency",
            "indicator": "orange",
        },
        {
            "label": "Collected",
            "value": total_collected,
            "datatype": "Currency",
            "indicator": "green",     # 🟢 Collected
        },
        {
            "label": "Invoiced",
            "value": total_invoiced,
            "datatype": "Currency",
            "indicator": "purple",    # 🟣 Invoiced
        },
        
        {
            "label": "Shortfall",
            "value": shortfall,
            "datatype": "Currency",
            "indicator": "red",       # 🔴 Shortfall
        },
    ]


def get_chart(data, filters):
    top_n = int(filters.get("top_n") or 10)

    top = sorted(data, key=lambda x: flt(x.get("orders_amount")), reverse=True)[:top_n]

    labels = [(r.get("customer_name") or r.get("customer") or "")[:20] for r in top]
    target = [flt(r.get("target")) for r in top]
    orders = [flt(r.get("orders_amount")) for r in top]
    collected = [flt(r.get("collected_amount")) for r in top]
    invoiced = [flt(r.get("invoiced_amount")) for r in top]
    shortfall = [flt(r.get("shortfall")) for r in top]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Target", "values": target, "chartType": "bar", "stack": 0},
                {"name": "Orders", "values": orders, "chartType": "bar", "stack": 0},
                {"name": "Collected", "values": collected, "chartType": "bar", "stack": 0},
                {"name": "Invoiced", "values": invoiced, "chartType": "bar", "stack": 0},

                # ✅ separate stack to highlight risk
                {"name": "Shortfall", "values": shortfall, "chartType": "bar", "stack": 1},
            ]
        },
        "type": "bar",
        "height": 260,
        "colors": [
            "#FB8C00",  # 🟠 Target
            "#1E88E5",  # 🔵 Orders
            "#43A047",  # 🟢 Collected
            "#8E24AA",  # 🟣 Invoiced
            "#E53935",  # 🔴 Shortfall
        ],
        "barOptions": {"stacked": True},
    }
