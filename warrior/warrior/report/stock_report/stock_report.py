import frappe

def execute(filters=None):
    conditions = ""

    if filters.get("warehouse"):
        conditions += " AND bin.warehouse = %(warehouse)s"

    if filters.get("item"):
        conditions += " AND i.item_code = %(item)s"

    if filters.get("brand"):
        conditions += " AND i.brand = %(brand)s"

    columns = [
        {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Data", "width": 150},
        {"label": "Brand ID", "fieldname": "brand_id", "fieldtype": "Data", "width": 80},
        {"label": "Brand Name", "fieldname": "brand_name", "fieldtype": "Data", "width": 150},
        {"label": "Product ID", "fieldname": "item_code", "fieldtype": "Data", "width": 150},
        {"label": "Product Name", "fieldname": "item_name", "fieldtype": "Data", "width": 280},
        {"label": "Generic Name", "fieldname": "generic_name", "fieldtype": "Data", "width": 180},
        {"label": "Warehouse Qty", "fieldname": "actual_qty", "fieldtype": "Int", "width": 130},
        {"label": "Reserved Qty", "fieldname": "reserved_qty", "fieldtype": "Int", "width": 130},
        {"label": "Available Qty", "fieldname": "available_qty", "fieldtype": "Int", "width": 130},
        {"label": "MSL Qty", "fieldname": "msl_qty", "fieldtype": "Int", "width": 120},
        {"label": "Sales Rate", "fieldname": "sales_rate", "fieldtype": "Currency", "width": 120},
        {"label": "Sales Valuation", "fieldname": "sales_valuation", "fieldtype": "Currency", "width": 140},
    ]

    data = frappe.db.sql(f"""
    SELECT
        report_data.*,
        (report_data.actual_qty * report_data.sales_rate) AS sales_valuation
    FROM (
        SELECT
            bin.warehouse AS warehouse,
            i.brand AS brand_id,
            b.brand AS brand_name,
            i.item_code,
            i.item_name,
            i.custom_genric_name AS generic_name,
            bin.actual_qty,
            bin.reserved_stock AS reserved_qty,
            (bin.actual_qty - bin.reserved_stock) AS available_qty,
            COALESCE(ir.warehouse_reorder_level, 0) AS msl_qty,
            COALESCE(
                (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    INNER JOIN `tabPrice List` pl ON pl.name = ip.price_list
                    WHERE ip.item_code = i.item_code
                      AND IFNULL(ip.selling, 0) = 1
                      AND IFNULL(pl.selling, 0) = 1
                      AND IFNULL(pl.enabled, 0) = 1
                      AND pl.custom_customer_group = 'Dealer'
                      AND pl.custom_brand = i.brand
                    ORDER BY ip.valid_from DESC, ip.modified DESC
                    LIMIT 1
                ),
                (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    WHERE ip.item_code = i.item_code
                      AND IFNULL(ip.selling, 0) = 1
                      AND ip.price_list = '1-A G Sales-Dealer'
                    ORDER BY ip.valid_from DESC, ip.modified DESC
                    LIMIT 1
                ),
                0
            ) AS sales_rate
        FROM
            `tabItem` i
        LEFT JOIN
            `tabBin` bin ON bin.item_code = i.item_code
        LEFT JOIN
            `tabBrand` b ON i.brand = b.name
        LEFT JOIN
            `tabItem Reorder` ir
            ON ir.parent = i.name AND ir.warehouse = bin.warehouse
        WHERE
            1=1 {conditions}
            AND i.disabled = 0
            AND bin.actual_qty > 0
    ) report_data
""", filters, as_dict=1)

    return columns, data
