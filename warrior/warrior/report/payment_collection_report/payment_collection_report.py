import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    return columns, data


def get_columns():
    return [
        {"label": _("Transaction Date"), "fieldname": "transaction_date", "fieldtype": "Datetime", "width": 150},
        {"label": _("Order ID"), "fieldname": "order_id", "fieldtype": "Data", "width": 140},
        {"label": _("Customer ID"), "fieldname": "customer_id", "fieldtype": "Data", "width": 140},
        {"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 180},
        {"label": _("Customer Group"), "fieldname": "customer_group", "fieldtype": "Link", "options": "Customer Group", "width": 160},
        {"label": _("Payment Method"), "fieldname": "payment_method", "fieldtype": "Data", "width": 140},
        {"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
        {"label": _("Gateway Reference"), "fieldname": "gateway_reference", "fieldtype": "Data", "width": 180},
        {"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 140},
        {"label": _("Payment Source"), "fieldname": "payment_source", "fieldtype": "Data", "width": 160},
    ]


def get_conditions(filters):
    conditions = []

    if filters.get("status"):
        conditions.append("pg.status = %(status)s")

    if filters.get("order_id"):
        conditions.append("pg.reference_id = %(order_id)s")

    if filters.get("customer"):
        conditions.append("so.customer = %(customer)s")

    if filters.get("customer_group"):
        conditions.append("so.customer_group = %(customer_group)s")

    if filters.get("from_date") and filters.get("to_date"):
        conditions.append("pg.transaction_date BETWEEN %(from_date)s AND %(to_date)s")

    return " AND ".join(conditions)

def get_data(filters):
    conditions = get_conditions(filters)
    where_clause = f"WHERE {conditions}" if conditions else ""

    query = f"""
        SELECT
            pg.transaction_date,
            pg.reference_id AS order_id,
            so.customer AS customer_id,
            so.customer_name,
            so.customer_group,
            pg.payment_method,
            pg.amount,
            pg.status,
            pg.gateway_reference,
            pg.source,
            pg.payment_source
        FROM (
            /* Payment Gateway */
               SELECT
    pe.posting_date AS transaction_date,
    'Payment Entry' AS source,
    pe.custom_sales_order AS reference_id,
    pe.mode_of_payment AS payment_method,
    pe.paid_amount AS amount,
    'Success' AS status,
    pe.reference_no AS gateway_reference,
    pe.mode_of_payment AS payment_source
FROM `tabPayment Entry` pe
WHERE
    pe.docstatus = 1
    AND IFNULL(pe.custom_sales_order, '') != ''
    AND pe.mode_of_payment LIKE '%%UPI%%'
            UNION ALL

            /* Bank Transfer */
            SELECT
                transaction_date AS transaction_date,
                'Bank Transfer Request' AS source,
                sales_order AS reference_id,
                'Bank Transfer' AS payment_method,
                approved_amount AS amount,
                CASE
                    WHEN status = 'Approved' THEN 'Success'
                    WHEN status IN ('Pending', 'Unsettled') THEN 'Pending'
                    WHEN status = 'Rejected' THEN 'Failed'
                    ELSE 'Pending'
                END AS status,
                utr_number AS gateway_reference,
                'Bank Transfer' AS payment_source
            FROM `tabBank Transfer Request`

            UNION ALL

            /* Rupifi */
            SELECT
                paymentdate AS transaction_date,
                'Rupifi' AS source,
                order_id AS reference_id,
                'Credit' AS payment_method,
                amount_value AS amount,
                CASE
                    WHEN status = 'CAPTURED' THEN 'Success'
                    WHEN status = 'AUTH_PENDING' THEN 'Pending'
                    WHEN status = 'AUTH_FAILED' THEN 'Failed'
                    ELSE 'Pending'
                END AS status,
                payment_id AS gateway_reference,
                'Rupifi BNPL' AS payment_source
            FROM `tabRupifi Webhook Log`
            
            UNION ALL

            /* Order Adjustment Journal Entry */
            SELECT
                je.posting_date AS transaction_date,
                'Order Adjustment' AS source,

                CASE
                    WHEN jea.reference_type = 'Sales Order'
                    THEN jea.reference_name

                    WHEN jea.reference_type = 'Sales Invoice'
                    THEN (
                        SELECT sii.sales_order
                        FROM `tabSales Invoice Item` sii
                        WHERE sii.parent = jea.reference_name
                        AND IFNULL(sii.sales_order, '') != ''
                        LIMIT 1
                    )
                END AS reference_id,

                'Adjusted Order' AS payment_method,

                ABS(
                    CASE
                        WHEN SUM(jea.debit) > 0 THEN SUM(jea.debit)
                        ELSE SUM(jea.credit)
                    END
                ) AS amount,

                'Success' AS status,

                je.name AS gateway_reference,

                'Adjusted From One Order To Another' AS payment_source

            FROM `tabJournal Entry` je
            INNER JOIN `tabJournal Entry Account` jea
                ON je.name = jea.parent

            WHERE
                je.docstatus = 1
                AND je.mode_of_payment = 'adjusted from one order to another'
                AND jea.reference_type IN ('Sales Order', 'Sales Invoice')

            GROUP BY
                je.name,
                jea.reference_type,
                jea.reference_name
        ) pg
        LEFT JOIN `tabSales Order` so
            ON so.name = pg.reference_id
        {where_clause}
        ORDER BY pg.transaction_date DESC
    """

    return frappe.db.sql(query, filters, as_dict=True)
