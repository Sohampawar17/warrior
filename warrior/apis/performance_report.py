import frappe
from frappe.utils import now,nowdate,add_days,get_url,quote,getdate,format_datetime, format_date,format_time,get_datetime
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url
from frappe.utils import flt,cint,fmt_money
import json
from frappe.utils.file_manager import save_file

def format_timedelta_to_time(td):
    if not td:
        return None

    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def format_seconds_to_readable(seconds):
    if not seconds:
        return "0 sec"

    seconds = int(seconds)

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []

    if days:
        parts.append(f"{days} day" + ("s" if days > 1 else ""))
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    if secs or not parts:
        parts.append(f"{secs} sec")

    return " ".join(parts)

@frappe.whitelist()
def performance_report(from_date=None, to_date=None,customer_group="Farmer"):
    try:

        from frappe.utils import getdate, nowdate, flt, format_datetime

        start_date = from_date
        end_date = to_date
        data = frappe.db.sql("""
            SELECT DISTINCT dl.link_name
            FROM `tabAddress` a
            JOIN `tabDynamic Link` dl 
                ON dl.parent = a.name
                AND dl.link_doctype = 'Customer'
            WHERE a.custom_tahshil IN (
                SELECT for_value
                FROM `tabUser Permission`
                WHERE user = %s
                AND allow = 'Tahshil'
            )
            AND a.disabled = 0
        """, (frappe.session.user,))
        filters = {
            "customer_group": ["in", ["Dealer"]],
            "custom_document_value": ["is", "set"],
            "custom_document_type": ["in", ["Delear Registration"]]
        }
        if data:
            customers = [d[0] for d in data]
            filters["name"]=["in",customers]

        customers = frappe.get_list(
            "Customer",
            filters=filters,
            fields=[
                "name",
                "customer_name",
                "disabled",
                "customer_primary_address",
                "mobile_no",
                "custom_document_value",
            ],
            order_by="modified desc",
        )

        # -----------------------
        # Address Map
        # -----------------------

        addr_names = tuple(
            [c.get("customer_primary_address") for c in customers if c.get("customer_primary_address")]
        ) or ("",)

        addr_rows = frappe.db.sql(
            """
            SELECT name, city, county, custom_tahshil, state
            FROM `tabAddress`
            WHERE name IN %(addr_names)s
            """,
            {"addr_names": addr_names},
            as_dict=True,
        )

        addr_map = {a["name"]: a for a in addr_rows}

        customer_names = [c["name"] for c in customers]

        # -----------------------
        # Date Conditions
        # -----------------------

        so_date_sql = ""
        si_date_sql = ""
        target_map = {}
        orders_map = {}
        invoice_map = {}
        collected_map = {}

        # -----------------------
        # ORDERS
        # -----------------------
        if customer_names:
            params = {"customers": tuple(customer_names)}

            if from_date and to_date:
                so_date_sql = " AND so.transaction_date BETWEEN %(from_date)s AND %(to_date)s"
                params["from_date"] = from_date
                params["to_date"] = to_date

            orders_map = dict(
                frappe.db.sql(
                    f"""
                    SELECT customer, SUM(grand_total)
                    FROM `tabSales Order` so
                    WHERE docstatus=1
                    AND customer IN %(customers)s
                    {so_date_sql}
                    GROUP BY customer
                    """,
                    params,
                    as_list=True,
                )
            )

        # -----------------------
        # INVOICES
        # -----------------------
        if customer_names:
            params = {"customers": tuple(customer_names)}

            if from_date and to_date:
                si_date_sql = " AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
                params["from_date"] = from_date
                params["to_date"] = to_date

            invoice_map = dict(
                frappe.db.sql(
                    f"""
                    SELECT customer, SUM(grand_total)
                    FROM `tabSales Invoice` si
                    WHERE docstatus=1
                    AND customer IN %(customers)s
                    {si_date_sql}
                    GROUP BY customer
                    """,
                    params,
                    as_list=True,
                )
            )

        # -----------------------
        # COLLECTED
        # -----------------------
        if customer_names:
            collected_map = dict(
                frappe.db.sql(
                    """
                    SELECT customer, SUM(amount)
                    FROM (
                        SELECT so.customer, per.allocated_amount as amount
                        FROM `tabPayment Entry Reference` per
                        JOIN `tabPayment Entry` pe ON pe.name = per.parent
                        JOIN `tabSales Order` so ON so.name = per.reference_name
                        WHERE pe.docstatus=1
                        AND per.reference_doctype='Sales Order'
                        AND so.customer IN %(customers)s

                        UNION ALL

                        SELECT si.customer, per.allocated_amount
                        FROM `tabPayment Entry Reference` per
                        JOIN `tabPayment Entry` pe ON pe.name = per.parent
                        JOIN `tabSales Invoice` si ON si.name = per.reference_name
                        WHERE pe.docstatus=1
                        AND per.reference_doctype='Sales Invoice'
                        AND si.customer IN %(customers)s
                    ) t
                    GROUP BY customer
                    """,
                    {"customers": tuple(customer_names)},
                    as_list=True,
                )
            )
        first_visit_time=frappe.db.get_value("Visit",{"owner": frappe.session.user, "visit_date": ["between", [start_date, end_date]]}, "visit_time", order_by="visit_date asc")
        total_visits = frappe.db.count("Visit", {"owner": frappe.session.user, "visit_date": ["between", [start_date, end_date]]})
        # -----------------------
        # Call Metrics
        # -----------------------
        call_start_dt = get_datetime(start_date)
        call_end_dt = get_datetime(add_days(end_date, 1))
        first_call = frappe.db.get_value(
            "Call Detail Entry",
            {
                "owner": frappe.session.user,
                "posting_datetime": ["between", [call_start_dt, call_end_dt]],
            },
            "posting_datetime",
            order_by="posting_datetime asc",
        )

        total_calls = frappe.db.count(
            "Call Detail Entry",
            {
                "owner": frappe.session.user,
                "posting_datetime": ["between", [call_start_dt, call_end_dt]],
            },
        )

        total_duration = frappe.db.sql(
            """
            SELECT SUM(call_duration)
            FROM `tabCall Detail Entry`
            WHERE owner=%s
            AND call_status='SUCCESS' AND call_belongs_to='Customer'
            AND posting_datetime BETWEEN %s AND %s
            """,
            (frappe.session.user, call_start_dt, call_end_dt),
        )[0][0] or 0
        customer_calls=frappe.db.count(
            "Call Detail Entry",
            {
                "owner": ["in", frappe.session.user],
                "call_belongs_to":"Customer",
                "posting_datetime": ["between", [call_start_dt, call_end_dt]],
            },
        )
        personal_calls=frappe.db.count(
            "Call Detail Entry",
            {
                "owner": ["in", frappe.session.user],
                "call_belongs_to":"Personal",
                "posting_datetime": ["between", [call_start_dt, call_end_dt]],
            },
        )
        success_calls = frappe.db.count(
            "Call Detail Entry",
            {
                "owner": ["in", frappe.session.user],
                "call_status": "SUCCESS",
                "call_belongs_to":"Customer",
                "posting_datetime": ["between", [call_start_dt, call_end_dt]],
            },
        )


        # -----------------------
        # Totals
        # -----------------------

        total_target = 0
        total_invoiced = 0

        for c in customers:

            cust = c["name"]
            did = c.get("custom_document_value")

            target = flt(target_map.get(did))
            invoiced = flt(invoice_map.get(cust))

            total_target += target
            total_invoiced += invoiced

        # -----------------------
        # Dealers Metrics
        # -----------------------
        dealer_doc_values = [
            c.get("custom_document_value")
            for c in customers
            if c.get("custom_document_value")
        ]
        no_of_dealers_with_deposit = frappe.db.count(
            "Apply Dealership",
            {
                "dealer_id": ["in", dealer_doc_values],
                "dealership_target": [">", 0],
                "docstatus": 0,
            },
        )

        no_of_dealers_with_agreement_signed = frappe.db.count(
            "Apply Dealership",
            {
                "dealer_id": ["in", dealer_doc_values],
                "docstatus": 1,
                "dealership_aggrement": ["is", "set"],
            },
        )
        no_of_days_present=frappe.db.count(
            "Attendance",
            {
                "employee": get_employee_by_user(frappe.session.user).get("name"),
                "attendance_date": ["between", [start_date, end_date]],
                "status": "Present",
            },
        )
        # -----------------------
        # Response
        # -----------------------

        revenue_where = [
            "si.docstatus = 1",
            "so.transaction_date BETWEEN %(from_date)s AND %(to_date)s",
        ]
        revenue_params = {
            "from_date": str(start_date),
            "to_date": str(end_date),
        }
        if customer_group:
            revenue_where.append("so.customer_group = %(customer_group)s")
            revenue_params["customer_group"] = customer_group

        revenue_row = frappe.db.sql(
            f"""
            SELECT
                SUM(CASE WHEN IFNULL(si.is_return, 0) = 0 THEN si.grand_total ELSE 0 END) AS total_order_amount,
                SUM(
                    CASE
                        WHEN IFNULL(si.is_return, 0) = 0
                        AND UPPER(TRIM(IFNULL(si.custom_dispatch_status, ''))) = 'DELIVERED'
                        THEN si.grand_total
                        ELSE 0
                    END
                ) AS delivered_amount,
                SUM(
                    CASE
                        WHEN IFNULL(si.is_return, 0) = 1
                        OR UPPER(TRIM(IFNULL(si.custom_dispatch_status, ''))) = 'REFUNDED'
                        THEN ABS(si.grand_total)
                        ELSE 0
                    END
                ) AS returned_amount,
                SUM(
                    CASE
                        WHEN IFNULL(si.is_return, 0) = 0
                        AND UPPER(TRIM(IFNULL(si.custom_dispatch_status, ''))) NOT IN ('DELIVERED', 'REFUNDED')
                        THEN si.grand_total
                        ELSE 0
                    END
                ) AS in_transit_amount
            FROM `tabSales Invoice` si
            LEFT JOIN (
                SELECT DISTINCT parent, sales_order
                FROM `tabSales Invoice Item`
                WHERE IFNULL(sales_order, '') != ''
            ) sii ON sii.parent = si.name
            LEFT JOIN `tabSales Order` so ON so.name = sii.sales_order
            WHERE {" AND ".join(revenue_where)}
            """,
            revenue_params,
            as_dict=True,
        )
        revenue_row = revenue_row[0] if revenue_row else {}

        refund_where = [
            "rr.order_doctype = 'Sales Order'",
            "rr.workflow_state = 'Paid'",
            "so.transaction_date BETWEEN %(from_date)s AND %(to_date)s",
        ]
        refund_params = {
            "from_date": str(start_date),
            "to_date": str(end_date),
        }
        if customer_group:
            refund_where.append("so.customer_group = %(customer_group)s")
            refund_params["customer_group"] = customer_group

        refund_row = frappe.db.sql(
            f"""
            SELECT SUM(rr.requested_refund_amount) AS refund_request_amount
            FROM `tabRefund Request` rr
            JOIN `tabSales Order` so ON so.name = rr.order_id
            WHERE {" AND ".join(refund_where)}
            """,
            refund_params,
            as_dict=True,
        )
        refund_row = refund_row[0] if refund_row else {}
        credit_note_returned_amount = flt(revenue_row.get("returned_amount"))
        refund_request_returned_amount = flt(refund_row.get("refund_request_amount"))
        total_returned_amount = credit_note_returned_amount + refund_request_returned_amount
        # -----------------------
        # Response
        # -----------------------

        return api_response(
            True,
            "Performance report fetched",
            {
                "no_of_dealers_with_deposit": no_of_dealers_with_deposit,
                "no_of_dealers_with_agreement_signed": no_of_dealers_with_agreement_signed,
                "target_business": round(total_target, 2),
                "achieved": round(total_invoiced, 2),
                "shortfall": round(total_target - total_invoiced, 2),
                "first_call": format_datetime(first_call) if first_call else None,
                "first_visit_time": format_timedelta_to_time(first_visit_time) if first_visit_time else None,
                "total_visits": total_visits,
                "total_calls": total_calls,
                 "customer_calls":customer_calls,
                "personal_calls":personal_calls,
                "success_calls": success_calls,
                "total_duration": format_seconds_to_readable(total_duration) if total_duration else None,
                "no_of_days_present":no_of_days_present,
                "total_order_amount": round(flt(revenue_row.get("total_order_amount")), 2),
                "delivered_amount": round(flt(revenue_row.get("delivered_amount")), 2),
                "returned_amount": round(total_returned_amount, 2),
                "in_transit_amount": round(flt(revenue_row.get("in_transit_amount")), 2),
            },
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Performance Report API Error")
        return api_response(False, "Failed to fetch report")