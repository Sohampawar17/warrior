import frappe

DEFAULT_WAREHOUSE_NAME = frappe.db.get_value(
    "Warehouse",
    {"custom_is_default_warehouse": 1},
    "name"
)

def _get_link_doctype(doctype, fieldname):
    """Return linked doctype if field is Link, else None."""
    try:
        df = frappe.get_meta(doctype).get_field(fieldname)
        if df and df.fieldtype == "Link" and df.options:
            return df.options
    except Exception:
        pass
    return None

def _resolve_title(doctype, name, cache):
    """Resolve linked record to its title (or name) with caching."""
    if not doctype or not name:
        return name

    key = (doctype, name)
    if key in cache:
        return cache[key]

    try:
        meta = frappe.get_meta(doctype)
        title_field = meta.title_field or "name"
        val = frappe.db.get_value(doctype, name, title_field) or name
    except Exception:
        val = name

    cache[key] = val
    return val

def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "V Type", "fieldname": "v_type", "fieldtype": "Data", "width": 80},
        {"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 100},
        {"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 160},
        {"label": "V name type", "fieldname": "v_name_type", "fieldtype": "Data", "width": 120},
        {"label": "Debit/Credit", "fieldname": "dr_cr", "fieldtype": "Data", "width": 95},
        {"label": "QTY", "fieldname": "qty", "fieldtype": "Float", "width": 70},
        {"label": "Item", "fieldname": "item", "fieldtype": "Data", "width": 160},
        {"label": "Type of Ref", "fieldname": "type_of_ref", "fieldtype": "Data", "width": 110},
        {"label": "Inv No", "fieldname": "inv_no", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
        {"label": "Inv Amt", "fieldname": "inv_amt", "fieldtype": "Currency", "width": 110},
        {"label": "Dealer GST No", "fieldname": "dealer_gst_no", "fieldtype": "Data", "width": 150},
        {"label": "Dealer Address", "fieldname": "dealer_address", "fieldtype": "Data", "width": 260},
        {"label": "Order Id", "fieldname": "order_id", "fieldtype": "Data", "width": 200},
        {"label": "Location", "fieldname": "location", "fieldtype": "Data", "width": 200},
    ]

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not from_date or not to_date:
        return columns, []

    where_sql = """si.docstatus = 1 AND IFNULL(si.is_return, 0) = 0 AND si.posting_date BETWEEN %s AND %s"""
    params = [from_date, to_date]

    if filters.get("invoice_no"):
        where_sql += " AND si.name = %s"
        params.append(filters["invoice_no"])

    if filters.get("customer"):
        where_sql += " AND si.customer = %s"
        params.append(filters["customer"])
    if filters.get("location"):
        where_sql += " AND IFNULL(si.set_warehouse,'') = %s"
        params.append(filters["location"])
    # We fetch raw location IDs separately and build dealer_address in Python
    # so you get names instead of IDs.
    sql = fsql = f"""
    /* 1) DR row */
    SELECT
        'Sales' AS v_type,
        si.posting_date AS date,
        si.customer AS customer_name,
        'Item Invoice' AS v_name_type,
        'DR' AS dr_cr,
        NULL AS qty,
        NULL AS item,
        'New ref' AS type_of_ref,
        si.name AS inv_no,
        si.rounded_total AS inv_amt,

        COALESCE(addr.gstin, cust.gstin, 'no gst number found') AS dealer_gst_no,
        '' AS dealer_address,

        (
            SELECT CONCAT('#', soi0.sales_order, ' _ ', si.customer_name)
            FROM `tabSales Invoice Item` soi0
            WHERE soi0.parent = si.name AND IFNULL(soi0.sales_order,'') != ''
            LIMIT 1
        ) AS order_id,

        CASE
            WHEN IFNULL(si.set_warehouse, '') = %s THEN 'Main Location'
            ELSE si.set_warehouse
        END AS location,

        addr.address_line1 AS _addr1,
        addr.address_line2 AS _addr2,
        addr.city AS _city_id,
        addr.custom_tahshil AS _tahsil_id,
        addr.custom_district AS _district_id,
        addr.state AS _state,
        addr.pincode AS _pincode

    FROM `tabSales Invoice` si
    LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
    LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
    WHERE {where_sql}

    UNION ALL

    /* 2) CR Item */
    SELECT
        'Sales',
        si.posting_date,

        CASE
    WHEN (IFNULL(soi.igst_rate,0) +
          IFNULL(soi.cgst_rate,0) +
          IFNULL(soi.sgst_rate,0)) = 0
    THEN 'Sales Exempted'
    ELSE CONCAT(
        'Sales GST ',
        CAST(
            (IFNULL(soi.igst_rate,0) +
             IFNULL(soi.cgst_rate,0) +
             IFNULL(soi.sgst_rate,0)) AS UNSIGNED
        ),
        CHAR(37)
    )
END,

        'Item Invoice',
        'CR',
        soi.qty,
        soi.item_code,
        'New ref',
        si.name,
        ROUND(soi.net_amount, 2),
        COALESCE(addr.gstin, cust.gstin, 'no gst number found'),
        '',

        (
            SELECT CONCAT('#', soi2.sales_order, ' _ ', si.customer_name)
            FROM `tabSales Invoice Item` soi2
            WHERE soi2.parent = si.name AND IFNULL(soi2.sales_order,'') != ''
            LIMIT 1
        ),

        CASE
            WHEN IFNULL(si.set_warehouse, '') = %s THEN 'Main Location'
            ELSE si.set_warehouse
        END,

        addr.address_line1,
        addr.address_line2,
        addr.city,
        addr.custom_tahshil,
        addr.custom_district,
        addr.state,
        addr.pincode

    FROM `tabSales Invoice` si
    INNER JOIN `tabSales Invoice Item` soi ON soi.parent = si.name
    LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
    LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
    WHERE {where_sql}

    UNION ALL

    /* 3) Round Off */
    SELECT
        'Sales',
        si.posting_date,
        'Round Off',
        'Item Invoice',
        'CR',
        NULL,
        NULL,
        'New ref',
        si.name,
      ROUND(
    si.rounded_total
    - (
        SELECT 
            ROUND(SUM(soi.net_amount), 2)
        FROM `tabSales Invoice Item` soi
        WHERE soi.parent = si.name
    )
    - (
        SELECT 
            ROUND(SUM(soi.cgst_amount + soi.sgst_amount + soi.igst_amount), 2)
        FROM `tabSales Invoice Item` soi
        WHERE soi.parent = si.name
    ),
2),

        COALESCE(addr.gstin, cust.gstin, 'no gst number found'),
        '',

        (
            SELECT CONCAT('#', soi4.sales_order, ' _ ', si.customer_name)
            FROM `tabSales Invoice Item` soi4
            WHERE soi4.parent = si.name AND IFNULL(soi4.sales_order,'') != ''
            LIMIT 1
        ),

        CASE
            WHEN IFNULL(si.set_warehouse, '') = %s THEN 'Main Location'
            ELSE si.set_warehouse
        END,

        addr.address_line1,
        addr.address_line2,
        addr.city,
        addr.custom_tahshil,
        addr.custom_district,
        addr.state,
        addr.pincode

    FROM `tabSales Invoice` si
    LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
    LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
    WHERE {where_sql}

    UNION ALL
/* 4) CGST */
SELECT
    'Sales',
    si.posting_date,
       CONCAT(
    'Output CGST @',
    TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM CAST(IFNULL(soi.cgst_rate,0) AS CHAR))),
    '%%'
),
    'Item Invoice',
    'CR',
    NULL,
    NULL,
    'New ref',
    si.name,
    ROUND(SUM(soi.cgst_amount),2),
    COALESCE(addr.gstin, cust.gstin, 'no gst number found'),
    '',
    (
        SELECT CONCAT('#', soi3.sales_order, ' _ ', si.customer_name)
        FROM `tabSales Invoice Item` soi3
        WHERE soi3.parent = si.name
        LIMIT 1
    ),
    CASE
        WHEN IFNULL(si.set_warehouse,'') = %s THEN 'Main Location'
        ELSE si.set_warehouse
    END,
    addr.address_line1,
    addr.address_line2,
    addr.city,
    addr.custom_tahshil,
    addr.custom_district,
    addr.state,
    addr.pincode
FROM `tabSales Invoice` si
JOIN `tabSales Invoice Item` soi ON soi.parent = si.name
LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
WHERE {where_sql}
AND IFNULL(soi.cgst_rate,0) > 0
GROUP BY si.name, soi.cgst_rate

UNION ALL

/* 5) SGST */
SELECT
    'Sales',
    si.posting_date,
    CONCAT(
    'Output SGST @',
    TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM CAST(IFNULL(soi.sgst_rate,0) AS CHAR))),
    '%%'
),
    'Item Invoice',
    'CR',
    NULL,
    NULL,
    'New ref',
    si.name,
    ROUND(SUM(soi.sgst_amount),2),
    COALESCE(addr.gstin, cust.gstin, 'no gst number found'),
    '',
    (
        SELECT CONCAT('#', soi3.sales_order, ' _ ', si.customer_name)
        FROM `tabSales Invoice Item` soi3
        WHERE soi3.parent = si.name
        LIMIT 1
    ),
    CASE
        WHEN IFNULL(si.set_warehouse, '') = %s THEN 'Main Location'
        ELSE si.set_warehouse
    END,
    addr.address_line1,
    addr.address_line2,
    addr.city,
    addr.custom_tahshil,
    addr.custom_district,
    addr.state,
    addr.pincode
FROM `tabSales Invoice` si
JOIN `tabSales Invoice Item` soi ON soi.parent = si.name
LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
WHERE {where_sql}
AND IFNULL(soi.sgst_rate,0) > 0
GROUP BY si.name, soi.sgst_rate
UNION ALL

/* 6) IGST */
SELECT
    'Sales',
    si.posting_date,
  CONCAT(
    'Output IGST @',
    TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM CAST(IFNULL(soi.igst_rate,0) AS CHAR))),
    '%%'
),
    'Item Invoice',
    'CR',
    NULL,
    NULL,
    'New ref',
    si.name,
    ROUND(SUM(soi.igst_amount),2),
    COALESCE(addr.gstin, cust.gstin, 'no gst number found'),
    '',
    (
        SELECT CONCAT('#', soi3.sales_order, ' _ ', si.customer_name)
        FROM `tabSales Invoice Item` soi3
        WHERE soi3.parent = si.name
        LIMIT 1
    ),
    CASE
        WHEN IFNULL(si.set_warehouse, '') = %s THEN 'Main Location'
        ELSE si.set_warehouse
    END,
    addr.address_line1,
    addr.address_line2,
    addr.city,
    addr.custom_tahshil,
    addr.custom_district,
    addr.state,
    addr.pincode
FROM `tabSales Invoice` si
JOIN `tabSales Invoice Item` soi ON soi.parent = si.name
LEFT JOIN `tabCustomer` cust ON cust.name = si.customer
LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
WHERE {where_sql}
AND IFNULL(soi.igst_rate,0) > 0
GROUP BY si.name, soi.igst_rate
    ORDER BY
    inv_no,
    (dr_cr = 'DR') DESC,
    (customer_name = 'Round Off') ASC,
    (qty IS NULL) ASC,
    customer_name,
    item
"""

    # DEFAULT_WAREHOUSE_NAME used 4 times (one per UNION)
    all_params = (
        ([DEFAULT_WAREHOUSE_NAME] + params) +   # 1
        ([DEFAULT_WAREHOUSE_NAME] + params) +   # 2
        ([DEFAULT_WAREHOUSE_NAME] + params) +   # 3
        ([DEFAULT_WAREHOUSE_NAME] + params) +   # 4
        ([DEFAULT_WAREHOUSE_NAME] + params) +   # 5
        ([DEFAULT_WAREHOUSE_NAME] + params)     # 6
    )
    data = frappe.db.sql(sql, all_params, as_dict=True)

    # ---- Convert Address link IDs -> names ----
    city_dt = _get_link_doctype("Address", "city")
    tahsil_dt = _get_link_doctype("Address", "custom_tahshil")
    mp_dt = _get_link_doctype("Address", "custom_district")

    cache = {}

    for row in data:
        addr1 = (row.get("_addr1") or "").strip()
        addr2 = (row.get("_addr2") or "").strip()

        city_id = row.get("_city_id")
        tahsil_id = row.get("_tahsil_id")
        district_id = row.get("_district_id")
        pincode = (row.get("_pincode") or "").strip()

        city_name = _resolve_title(city_dt, city_id, cache) if city_id else ""
        tahsil_name = _resolve_title(tahsil_dt, tahsil_id, cache) if tahsil_id else ""
        district_name = _resolve_title(mp_dt, district_id, cache) if district_id else ""

        state = (row.get("_state") or "").strip()

        parts = []
        for p in [addr1, addr2, city_name, tahsil_name, district_name, state, pincode]:
            if p:
                parts.append(str(p).strip())

        row["dealer_address"] = ", ".join(parts)

        # cleanup
        row.pop("_addr1", None)
        row.pop("_addr2", None)
        row.pop("_city_id", None)
        row.pop("_tahsil_id", None)
        row.pop("_district_id", None)
        row.pop("_state", None)
        row.pop("_pincode", None)

    return columns, data