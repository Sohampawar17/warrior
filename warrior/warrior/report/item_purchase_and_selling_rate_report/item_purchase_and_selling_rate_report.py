import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 220},
        {"label": "Generic Name", "fieldname": "generic_name", "fieldtype": "Data", "width": 160},
        {"label": "Brand", "fieldname": "brand", "fieldtype": "Link", "options": "Brand", "width": 140},
        {"label": "Item Tax Template", "fieldname": "item_tax_template", "fieldtype": "Link", "options": "Item Tax Template", "width": 180},
        {"label": "Selling Price List", "fieldname": "selling_price_list", "fieldtype": "Link", "options": "Price List", "width": 160},
        {"label": "Selling Rate", "fieldname": "selling_rate", "fieldtype": "Currency", "width": 120},
        {"label": "Selling Rate With GST", "fieldname": "selling_rate_with_gst", "fieldtype": "Currency", "width": 160},
        {"label": "Purchase Price List", "fieldname": "purchase_price_list", "fieldtype": "Link", "options": "Price List", "width": 160},
        {"label": "Purchase Rate", "fieldname": "purchase_rate", "fieldtype": "Currency", "width": 120},
        {"label": "Purchase Rate With GST", "fieldname": "purchase_rate_with_gst", "fieldtype": "Currency", "width": 170},
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters and filters.get("item_code"):
        conditions.append("i.name = %(item_code)s")
        values["item_code"] = filters.get("item_code")

    if filters and filters.get("brand"):
        conditions.append("i.brand = %(brand)s")
        values["brand"] = filters.get("brand")

    if filters.get("item_status") == "Enabled":
        conditions.append("i.disabled = 0")
    elif filters.get("item_status") == "Disabled":
        conditions.append("i.disabled = 1")
    condition_sql = " AND ".join(conditions)

    return frappe.db.sql(f"""
    SELECT
        i.name AS item_code,
        i.item_name,
        i.custom_genric_name AS generic_name,
        b.brand as brand,

        item_supplier.supplier AS default_supplier,
        sup.default_price_list AS supplier_price_list,

        itt.item_tax_template,
        IFNULL(tax.gst_rate, 0) AS gst_rate,

        selling.price_list AS selling_price_list,
        selling.price_list_rate AS selling_rate,
        ROUND(
            IFNULL(selling.price_list_rate, 0) +
            (IFNULL(selling.price_list_rate, 0) * IFNULL(tax.gst_rate, 0) / 100),
            2
        ) AS selling_rate_with_gst,

        purchase.price_list AS purchase_price_list,
        purchase.price_list_rate AS purchase_rate,
        ROUND(
            IFNULL(purchase.price_list_rate, 0) +
            (IFNULL(purchase.price_list_rate, 0) * IFNULL(tax.gst_rate, 0) / 100),
            2
        ) AS purchase_rate_with_gst

    FROM `tabItem` i
    LEFT JOIN  `tabBrand` b
        ON b.name = i.brand
    LEFT JOIN (
        SELECT
            parent,
            MIN(supplier) AS supplier
        FROM `tabItem Supplier`
        WHERE parenttype = 'Item'
        AND custom_default_supplier = 1
        GROUP BY parent
    ) item_supplier
        ON item_supplier.parent = i.name

    LEFT JOIN `tabSupplier` sup
        ON sup.name = item_supplier.supplier

    LEFT JOIN `tabItem Price` purchase
        ON purchase.item_code = i.name
        AND purchase.buying = 1
        AND purchase.price_list = sup.default_price_list

    LEFT JOIN (
        SELECT
            t1.parent,
            t1.item_tax_template,
            t1.valid_from
        FROM `tabItem Tax` t1
        WHERE
            t1.parenttype = 'Item'
            AND IFNULL(t1.valid_from, '1900-01-01') <= CURDATE()
            AND t1.name = (
                SELECT t2.name
                FROM `tabItem Tax` t2
                WHERE
                    t2.parent = t1.parent
                    AND t2.parenttype = 'Item'
                    AND IFNULL(t2.valid_from, '1900-01-01') <= CURDATE()
                ORDER BY
                    IFNULL(t2.valid_from, '1900-01-01') DESC,
                    t2.creation DESC
                LIMIT 1
            )
    ) itt
        ON itt.parent = i.name

    LEFT JOIN (
        SELECT
            parent,
            MAX(tax_rate) AS gst_rate
        FROM `tabItem Tax Template Detail`
        GROUP BY parent
    ) tax
        ON tax.parent = itt.item_tax_template

    LEFT JOIN `tabItem Price` selling
        ON selling.item_code = i.name
        AND selling.selling = 1

    WHERE {condition_sql}

    ORDER BY
        i.item_name,
        selling.price_list,
        purchase.price_list
""", values, as_dict=True)