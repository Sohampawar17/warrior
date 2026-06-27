import frappe
from frappe.utils import flt

def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)

    # # Add S.No like your Excel
    # for i, row in enumerate(data, start=1):
    #     row["s_no"] = i

    return columns, data


def get_columns():
    return [
        # {"label": "S.No", "fieldname": "s_no", "fieldtype": "Int", "width": 60},
        {"label": "Invoice Date", "fieldname": "invoice_datetime", "fieldtype": "Datetime", "width": 170},
        {"label": "Invoice ID", "fieldname": "invoice_id", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
        {"label": "Product ID", "fieldname": "product_id", "fieldtype": "Link", "options": "Item", "width": 110},
        {"label": "Product Name", "fieldname": "product_name", "fieldtype": "Data", "width": 240},
        {"label": "User Type", "fieldname": "user_type", "fieldtype": "Data", "width": 110},
        {"label": "HSN Code", "fieldname": "hsn_code", "fieldtype": "Data", "width": 110},
        {"label": "GST %", "fieldname": "gst_percent", "fieldtype": "Data", "width": 70},
        {"label": "Quantity", "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": "Unit Price (Excl Tax)", "fieldname": "unit_price_excl_tax", "fieldtype": "Currency", "width": 140},
        {"label": "CGST Amount", "fieldname": "cgst_amount", "fieldtype": "Currency", "width": 120},
        {"label": "SGST Amount", "fieldname": "sgst_amount", "fieldtype": "Currency", "width": 120},
        {"label": "IGST Amount", "fieldname": "igst_amount", "fieldtype": "Currency", "width": 120},
        {"label": "Taxable Value", "fieldname": "taxable_value", "fieldtype": "Currency", "width": 120},
        {"label": "Total Value", "fieldname": "total_value", "fieldtype": "Currency", "width": 120},
    ]


def get_data(filters):
    conditions = ["si.docstatus = 1"]
    values = {}

    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("customer_group"):
        conditions.append("si.customer_group = %(customer_group)s")
        values["customer_group"] = filters["customer_group"]

    if filters.get("company"):
        conditions.append("si.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("invoice"):
        conditions.append("si.name = %(invoice)s")
        values["invoice"] = filters["invoice"]

    if filters.get("item_code"):
        conditions.append("sii.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]

    # HSN filtering: prefer Sales Invoice Item gst_hsn_code, fallback to Item.gst_hsn_code
    if filters.get("gst_hsn_code"):
        conditions.append("(sii.gst_hsn_code = %(gst_hsn_code)s OR it.gst_hsn_code = %(gst_hsn_code)s)")
        values["gst_hsn_code"] = (filters["gst_hsn_code"] or "").strip()

    where_clause = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            -- invoice datetime
            CONCAT(si.posting_date, ' ', IFNULL(si.posting_time, '00:00:00')) AS invoice_datetime,
            si.name AS invoice_id,

            sii.item_code AS product_id,
            sii.item_name AS product_name,

            si.customer_group AS user_type,

            COALESCE(NULLIF(sii.gst_hsn_code, ''), NULLIF(it.gst_hsn_code, ''), '') AS hsn_code,

            -- GST Percent: in India GST, ERPNext stores rates on item row
            (IFNULL(sii.igst_rate, 0) + IFNULL(sii.cgst_rate, 0) + IFNULL(sii.sgst_rate, 0)) AS gst_percent,

            sii.qty AS qty,

            -- Unit Price (Excl Tax): net_rate is price after discount, excluding tax
            sii.net_rate AS unit_price_excl_tax,

            IFNULL(sii.cgst_amount, 0) AS cgst_amount,
            IFNULL(sii.sgst_amount, 0) AS sgst_amount,
            IFNULL(sii.igst_amount, 0) AS igst_amount,

            -- Taxable Value: net_amount = net_rate * qty (excluding tax)
            sii.net_amount AS taxable_value,

            -- Total Value: taxable + all GST amounts
            (sii.net_amount + IFNULL(sii.cgst_amount, 0) + IFNULL(sii.sgst_amount, 0) + IFNULL(sii.igst_amount, 0)) AS total_value

        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabItem` it ON it.name = sii.item_code
        WHERE {where_clause}
        ORDER BY si.posting_date, si.posting_time, si.name, sii.idx
        """,
        values=values,
        as_dict=True,
    )

    # Safety: ensure numeric formatting
    for r in rows:
        r["gst_percent"] = flt(r.get("gst_percent"))
        r["qty"] = flt(r.get("qty"))
        r["unit_price_excl_tax"] = flt(r.get("unit_price_excl_tax"))
        r["cgst_amount"] = flt(r.get("cgst_amount"))
        r["sgst_amount"] = flt(r.get("sgst_amount"))
        r["igst_amount"] = flt(r.get("igst_amount"))
        r["taxable_value"] = flt(r.get("taxable_value"))
        r["total_value"] = flt(r.get("total_value"))

    return rows