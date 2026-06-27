import frappe
from frappe.utils import flt

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "PO", "fieldname": "name", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
        {"label": "Date", "fieldname": "transaction_date", "fieldtype": "Date", "width": 95},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 120},
        {"label": "Supplier Name", "fieldname": "supplier_name", "fieldtype": "Data", "width": 220},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 130},
         {"label": "PO Stage", "fieldname": "po_stage", "fieldtype": "Data", "width": 130},
        {"label": "Currency", "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 80},
        {"label": "Base Net Total", "fieldname": "base_net_total", "fieldtype": "Currency", "width": 120},
        {"label": "Taxes and Charges", "fieldname": "total_taxes_and_charges", "fieldtype": "Currency", "width": 120},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
        {"label": "Billed Amount (Base)", "fieldname": "billed_amount", "fieldtype": "Currency", "width": 140},
        {"label": "Outstanding To Bill (Base)", "fieldname": "outstanding_to_bill", "fieldtype": "Currency", "width": 170},
        {"label": "% Received", "fieldname": "per_received", "fieldtype": "Percent", "width": 90},
        {"label": "% Billed", "fieldname": "per_billed", "fieldtype": "Percent", "width": 80},
        {"label": "Owner", "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 140},
                {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},

    ]


def get_data(filters):
    conditions = []
    values = {}

    # Date filters
    if filters.get("from_date"):
        conditions.append("po.transaction_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("po.transaction_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    # Core filters
    if filters.get("company"):
        conditions.append("po.company = %(company)s")
        values["company"] = filters["company"]

    if filters.get("supplier"):
        conditions.append("po.supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]

    if filters.get("purchase_order"):
        conditions.append("po.name = %(purchase_order)s")
        values["purchase_order"] = filters["purchase_order"]

    if filters.get("status"):
        conditions.append("po.status = %(status)s")
        values["status"] = filters["status"]
   
    # conditions.append("po.docstatus = 1")

    # Item filter requires joining PO Item
    join_poi = ""
    if filters.get("item_code"):
        join_poi = " INNER JOIN `tabPurchase Order Item` poi ON poi.parent = po.name "
        conditions.append("poi.item_code = %(item_code)s")
        values["item_code"] = filters["item_code"]

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    # Pull Purchase Orders
    pos = frappe.db.sql(
        f"""
        SELECT
            po.name,
            po.transaction_date,
            po.supplier,
            po.supplier_name,
            po.docstatus,
            po.company,
            CASE
        WHEN po.docstatus = 2 THEN 'Cancelled'
        ELSE po.workflow_state
    END AS po_stage,
    po.status,
            po.currency,
            po.grand_total,
            po.base_net_total,
            po.total_taxes_and_charges,
            po.per_received,
            po.per_billed,
            po.owner
        FROM `tabPurchase Order` po
        {join_poi}
        {where_clause}
        GROUP BY po.name
        ORDER BY po.transaction_date DESC, po.name DESC
        """,
        values,
        as_dict=True,
    )

    if not pos:
        return []

    po_names = [d["name"] for d in pos]

    # Compute billed amount (Base) from Purchase Invoices linked to PO items
    # Works when PI Items have purchase_order + po_detail filled (standard mapping).
    billed_map = {}
    billed_rows = frappe.db.sql(
        """
        SELECT
            pii.purchase_order AS po,
            SUM(pii.base_net_amount) AS billed_amount
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE
            pi.docstatus = 1
            AND pii.purchase_order IN %(po_names)s
        GROUP BY pii.purchase_order
        """,
        {"po_names": tuple(po_names)},
        as_dict=True,
    )

    for r in billed_rows:
        billed_map[r["po"]] = flt(r["billed_amount"])

    # Final output rows
    out = []
    for r in pos:
        base_net_total = flt(r.get("base_net_total"))
        billed_amount = flt(billed_map.get(r["name"], 0))
        outstanding_to_bill = flt(base_net_total - billed_amount)

        # handle float noise
        if abs(outstanding_to_bill) < 0.0001:
            outstanding_to_bill = 0

        out.append({
            **r,
            "billed_amount": billed_amount,
            "outstanding_to_bill": outstanding_to_bill,
        })

    return out