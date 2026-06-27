# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})

    from_date, to_date = get_date_range(filters)

    columns = get_columns()

    data = get_data(
        from_date,
        to_date,
        filters.get("campaign")
    )

    chart = get_chart(data)
    report_summary = get_report_summary(data)

    return columns, data, None, chart, report_summary


def get_date_range(filters):
    if not filters.get("from_date") and not filters.get("to_date"):
        today = getdate(nowdate())
        return today, today

    from_date = getdate(
        filters.get("from_date")
        or filters.get("to_date")
    )

    to_date = getdate(
        filters.get("to_date")
        or filters.get("from_date")
    )

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    return from_date, to_date


def get_columns():
    return [
        {
            "label": "Campaign ID",
            "fieldname": "campaign_name",
            "fieldtype": "Link",
            "options": "Campaign",
            "width": 220
        },
        {
            "label": "Campaign Name",
            "fieldname": "campaign_title",
            "fieldtype": "Data",
            "width": 220
        },
        {
            "label": "No of Leads",
            "fieldname": "no_of_leads",
            "fieldtype": "Int",
            "width": 120
        },
        {
            "label": "Per Lead Cost",
            "fieldname": "per_lead_cost",
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "label": "Lead Cost",
            "fieldname": "lead_cost",
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "label": "No of Orders",
            "fieldname": "no_of_orders",
            "fieldtype": "Int",
            "width": 120
        },
        {
            "label": "Order Amount",
            "fieldname": "order_amount",
            "fieldtype": "Currency",
            "width": 140
        },
        {
            "label": "Receipt Amount",
            "fieldname": "receipt_amount",
            "fieldtype": "Currency",
            "width": 140
        },
        {
            "label": "Pending Amount",
            "fieldname": "pending_amount",
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "label": "Invoice Amount",
            "fieldname": "invoice_amount",
            "fieldtype": "Currency",
            "width": 140
        },
        {
            "label": "Return Amount",
            "fieldname": "return_order_amount",
            "fieldtype": "Currency",
            "width": 170
        },
        {
            "label": "Expenses (%)",
            "fieldname": "expenses",
            "fieldtype": "Percent",
            "width": 130
        }
    ]


def get_data(from_date, to_date, campaign=None):
    lead_rows = get_lead_rows(from_date, to_date, campaign)
    if not lead_rows:
        return []

    lead_counts = defaultdict(int)
    lead_campaign_map = {}
    campaign_names = set()
    lead_names = set()

    for row in lead_rows:
        campaign_name = row.campaign
        lead_name = row.lead_name
        if not campaign_name or not lead_name:
            continue

        lead_counts[campaign_name] += 1
        lead_campaign_map[lead_name] = campaign_name
        campaign_names.add(campaign_name)
        lead_names.add(lead_name)

    campaign_customers = get_campaign_customers(lead_campaign_map, lead_names)
    customer_campaigns = invert_customer_map(campaign_customers)
    customers = sorted({customer for values in campaign_customers.values() for customer in values})

    order_metrics = get_order_metrics(customer_campaigns, customers, from_date, to_date)
    invoice_metrics = get_invoice_metrics(customer_campaigns, customers, from_date, to_date)
    return_metrics = get_return_metrics(customer_campaigns, customers, from_date, to_date)

    campaigns = get_campaigns(campaign_names, campaign)
    rows = []

    for campaign_doc in campaigns:
        campaign_name = campaign_doc.name
        no_of_leads = lead_counts.get(campaign_name, 0)
        order_data = order_metrics.get(campaign_name, {})
        return_order_amount = flt(return_metrics.get(campaign_name, 0))

        row = {
            "campaign_name": campaign_name,
            "campaign_title": campaign_doc.description,
            "per_lead_cost": flt(campaign_doc.custom_per_lead_cost or 0),
            "no_of_leads": no_of_leads,
            "lead_cost": flt(no_of_leads) * flt(campaign_doc.custom_per_lead_cost or 0),
            "no_of_orders": len(order_data.get("order_names", set())),
            "order_amount": flt(order_data.get("order_amount", 0)),
            "receipt_amount": flt(order_data.get("receipt_amount", 0)),
            "pending_amount": flt(order_data.get("order_amount", 0)) - flt(order_data.get("receipt_amount", 0)),
            "invoice_amount": flt(invoice_metrics.get(campaign_name, 0)),
            "return_order_amount": return_order_amount,
            "expenses":flt(no_of_leads) * flt(campaign_doc.custom_per_lead_cost or 0) /flt(order_data.get("order_amount", 0)) if order_data.get("order_amount", 0) else 0
        }

        if row["no_of_leads"] or row["no_of_orders"] or row["return_order_amount"]:
            rows.append(row)

    return rows


def get_report_summary(data):
    total_leads = sum(int(row.get("no_of_leads") or 0) for row in data)
    total_orders = sum(int(row.get("no_of_orders") or 0) for row in data)
    total_order_amount = sum(flt(row.get("order_amount") or 0) for row in data)
    total_receipt_amount = sum(flt(row.get("receipt_amount") or 0) for row in data)
    total_invoice_amount = sum(flt(row.get("invoice_amount") or 0) for row in data)
    total_return_amount = sum(flt(row.get("return_order_amount") or 0) for row in data)
    total_lead_cost = sum(flt(row.get("lead_cost") or 0) for row in data)

    return [
        {"label": "Leads", "value": total_leads, "datatype": "Int", "indicator": "Blue"},
        {"label": "Orders", "value": total_orders, "datatype": "Int", "indicator": "Green"},
        {"label": "Lead Cost", "value": total_lead_cost, "datatype": "Currency", "indicator": "Orange"},
        {"label": "Order Amount", "value": total_order_amount, "datatype": "Currency", "indicator": "Purple"},
        {"label": "Receipt Amount", "value": total_receipt_amount, "datatype": "Currency", "indicator": "Cyan"},
        {"label": "Invoice Amount", "value": total_invoice_amount, "datatype": "Currency", "indicator": "Purple"},
        {"label": "Return Amount", "value": total_return_amount, "datatype": "Currency", "indicator": "Red"},
    ]


def get_chart(data):
    if not data:
        return None

    chart_rows = sorted(data, key=lambda row: flt(row.get("order_amount") or 0), reverse=True)[:10]
    if not chart_rows:
        return None

    labels = [row.get("campaign_title") or row.get("campaign_name") for row in chart_rows]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": "Lead Cost",
                    "values": [flt(row.get("lead_cost") or 0) for row in chart_rows],
                },
                {
                    "name": "Order Amount",
                    "values": [flt(row.get("order_amount") or 0) for row in chart_rows],
                },
            ],
        },
        "type": "bar",
        "colors": ["#4C78A8", "#59A14F"],
    }


def get_lead_rows(from_date, to_date, campaign=None):
    params = {
        "from_date": from_date,
        "to_date": to_date,
    }

    campaign_filter = ""
    if campaign:
        params["campaign"] = campaign
        campaign_filter = " AND l.campaign_name = %(campaign)s "

    return frappe.db.sql(
        f"""
        SELECT
            td.name AS todo_name,
            td.allocated_to,
            l.name AS lead_name,
            l.campaign_name AS campaign,
            l.type AS lead_type
        FROM `tabToDo` td
        INNER JOIN `tabLead` l
            ON l.name = td.reference_name
        WHERE td.reference_type = 'Lead'
          AND td.status = 'Open'
          AND td.creation >= %(from_date)s
          AND td.creation < DATE_ADD(%(to_date)s, INTERVAL 1 DAY)
          AND l.campaign_name IS NOT NULL
          AND l.campaign_name != ''
          {campaign_filter}
        ORDER BY l.campaign_name ASC, td.creation ASC, td.name ASC
        """,
        params,
        as_dict=True,
    )


def get_campaign_customers(lead_campaign_map, lead_names):
    campaign_customers = defaultdict(set)

    if not lead_names:
        return campaign_customers

    lead_names = tuple(lead_names)
    customer_rows = []

    customer_rows.extend(
        frappe.db.sql(
            """
            SELECT DISTINCT
                l.name AS lead_name,
                cust.name AS customer
            FROM `tabLead` l
            INNER JOIN `tabCustomer` cust
                ON cust.lead_name = l.name
            WHERE l.name IN %(lead_names)s AND cust.disabled = 0
            """,
            {"lead_names": lead_names},
            as_dict=True,
        )
    )

    customer_rows.extend(
        frappe.db.sql(
            """
            SELECT DISTINCT
                fr.from_document AS lead_name,
                cust.name AS customer
            FROM `tabFarmer Registration` fr
            INNER JOIN `tabCustomer` cust
                ON cust.custom_document_type = 'Farmer Registration'
                AND cust.custom_document_value = fr.name
            WHERE fr.from_document IN %(lead_names)s AND fr.docstatus = 1 AND cust.disabled = 0 
            """,
            {"lead_names": lead_names},
            as_dict=True,
        )
    )

    customer_rows.extend(
        frappe.db.sql(
            """
            SELECT DISTINCT
                dr.from_document AS lead_name,
                cust.name AS customer
            FROM `tabDelear Registration` dr
            INNER JOIN `tabCustomer` cust
                ON cust.custom_document_type = 'Delear Registration'
                AND cust.custom_document_value = dr.name
            WHERE dr.from_document IN %(lead_names)s AND dr.docstatus = 1 AND cust.disabled = 0
            """,
            {"lead_names": lead_names},
            as_dict=True,
        )
    )

    for row in customer_rows:
        campaign_name = lead_campaign_map.get(row.lead_name)
        if campaign_name and row.customer:
            campaign_customers[campaign_name].add(row.customer)

    return campaign_customers


def get_order_metrics(customer_campaigns, customers, from_date, to_date):
    metrics = defaultdict(lambda: {"order_names": set(), "order_amount": 0, "receipt_amount": 0})

    if not customers:
        return metrics

    rows = frappe.db.sql(
        """
        SELECT
            so.customer,
            so.name,
            so.grand_total,
            so.advance_paid
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND so.transaction_date >= %(from_date)s
          AND so.transaction_date <= %(to_date)s
          AND so.customer IN %(customers)s
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
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "customers": tuple(customers),
        },
        as_dict=True,
    )

    for row in rows:
        for campaign_name in customer_campaigns.get(row.customer, []):
            metrics[campaign_name]["order_names"].add(row.name)
            metrics[campaign_name]["order_amount"] += flt(row.grand_total or 0)
            metrics[campaign_name]["receipt_amount"] += flt(row.advance_paid or 0)

    return metrics


def get_return_metrics(customer_campaigns, customers, from_date, to_date):
    metrics = defaultdict(float)

    if not customers:
        return metrics

    rows = frappe.db.sql(
        """
        SELECT DISTINCT
            so.customer,
            si.name,
            ABS(si.grand_total) AS return_order_amount
        FROM `tabSales Order` so
        INNER JOIN `tabSales Invoice Item` sii
            ON sii.sales_order = so.name
        INNER JOIN `tabSales Invoice` si
            ON si.name = sii.parent
        WHERE so.docstatus = 1
          AND so.transaction_date >= %(from_date)s
          AND so.transaction_date <= %(to_date)s
          AND si.docstatus = 1
          AND si.is_return = 1
          AND so.customer IN %(customers)s
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
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "customers": tuple(customers),
        },
        as_dict=True,
    )

    for row in rows:
        for campaign_name in customer_campaigns.get(row.customer, []):
            metrics[campaign_name] += flt(row.return_order_amount or 0)

    return metrics


def get_invoice_metrics(customer_campaigns, customers, from_date, to_date):
    metrics = defaultdict(float)

    if not customers:
        return metrics

    rows = frappe.db.sql(
        """
        SELECT
            x.customer,
            SUM(x.invoice_amount) AS invoice_amount
        FROM (
            SELECT DISTINCT
                so.customer,
                si.name,
                si.grand_total AS invoice_amount
            FROM `tabSales Order` so
            INNER JOIN `tabSales Invoice Item` sii
                ON sii.sales_order = so.name
            INNER JOIN `tabSales Invoice` si
                ON si.name = sii.parent
            WHERE so.docstatus = 1
              AND so.transaction_date >= %(from_date)s
              AND so.transaction_date <= %(to_date)s
              AND si.docstatus = 1
              AND IFNULL(si.is_return, 0) = 0
              AND so.customer IN %(customers)s
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
        ) x
        GROUP BY x.customer
        """,
        {
            "from_date": from_date,
            "to_date": to_date,
            "customers": tuple(customers),
        },
        as_dict=True,
    )

    for row in rows:
        for campaign_name in customer_campaigns.get(row.customer, []):
            metrics[campaign_name] += flt(row.invoice_amount or 0)

    return metrics


def invert_customer_map(campaign_customers):
    customer_campaigns = defaultdict(set)
    for campaign_name, customers in campaign_customers.items():
        for customer in customers:
            customer_campaigns[customer].add(campaign_name)
    return customer_campaigns


def get_campaigns(campaign_names, campaign=None):
    filters = {"name": ["in", ["B2C-AO-001"]]}
    if campaign:
        filters = {"name": campaign}

    return frappe.get_all(
        "Campaign",
        filters=filters,
        fields=["name", "campaign_name", "custom_per_lead_cost", "description"],
        order_by="campaign_name asc, name asc",
    )
