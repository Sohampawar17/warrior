import frappe
from frappe.utils import get_datetime

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Visit ID", "fieldname": "name", "fieldtype": "Link", "options": "Visit", "width": 140},
        {"label": "Owner", "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 180},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Data", "width": 100},
        {"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 200},

        {"label": "Visit DateTime", "fieldname": "visit_datetime", "fieldtype": "Datetime", "width": 170},
        {"label": "Visit Date", "fieldname": "visit_date", "fieldtype": "Date", "width": 110},
        {"label": "Visit Time", "fieldname": "visit_time", "fieldtype": "Time", "width": 110},

        {"label": "Mobile", "fieldname": "mobile_number", "fieldtype": "Data", "width": 130},
        {"label": "Alternate Mobile", "fieldname": "alternate_mobile_number", "fieldtype": "Data", "width": 130},

        {"label": "Marketplace", "fieldname": "marketplace", "fieldtype": "Data", "width": 110},
        {"label": "Order ID", "fieldname": "order_id", "fieldtype": "Data", "width": 160},
        {"label": "Next Order Date", "fieldname": "next_order_date", "fieldtype": "Date", "width": 130},

        {"label": "Brands Available", "fieldname": "brands_available_in_shop", "fieldtype": "Data", "width": 180},
        {"label": "Most Selling Product/Brand", "fieldname": "most_selling_product_and_brand", "fieldtype": "Data", "width": 220},
        {"label": "Opinion on Credit", "fieldname": "opinion_on_credit_system", "fieldtype": "Data", "width": 150},
        {"label": "Thoughts on Product/Quality", "fieldname": "thoughts_on_gbru_product_and_quality", "fieldtype": "Data", "width": 210},
        {"label": "Additional Remarks", "fieldname": "additional_remarks", "fieldtype": "Data", "width": 240},

        {"label": "Location Name", "fieldname": "loc_name", "fieldtype": "Data", "width": 120},
        {"label": "Street", "fieldname": "loc_street", "fieldtype": "Data", "width": 220},
        {"label": "Locality", "fieldname": "loc_locality", "fieldtype": "Data", "width": 150},
        {"label": "Sub Locality", "fieldname": "loc_sub_locality", "fieldtype": "Data", "width": 150},
        {"label": "Admin Area", "fieldname": "loc_administrative_area", "fieldtype": "Data", "width": 150},
        {"label": "Sub Admin Area", "fieldname": "loc_sub_administrative_area", "fieldtype": "Data", "width": 160},
        {"label": "Postal Code", "fieldname": "loc_postal_code", "fieldtype": "Data", "width": 110},
        {"label": "Country", "fieldname": "loc_country", "fieldtype": "Data", "width": 150},
        {"label": "Country Code", "fieldname": "loc_country_code", "fieldtype": "Data", "width": 110},

        {"label": "Latitude", "fieldname": "lattitude", "fieldtype": "Data", "width": 100},
        {"label": "Longitude", "fieldname": "longitude", "fieldtype": "Data", "width": 100},

        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "Profile Status", "fieldname": "profile_status", "fieldtype": "Data", "width": 120},

        {"label": "Created On", "fieldname": "creation", "fieldtype": "Datetime", "width": 170},
        {"label": "Modified On", "fieldname": "modified", "fieldtype": "Datetime", "width": 170},
    ]


def get_data(filters):
    conditions = ["v.docstatus < 2"]
    values = {}

    # Date filters
    if filters.get("from_date") and filters.get("to_date"):
        conditions.append("v.visit_date BETWEEN %(from_date)s AND %(to_date)s")
        values["from_date"] = filters.from_date
        values["to_date"] = filters.to_date
    elif filters.get("from_date"):
        conditions.append("v.visit_date >= %(from_date)s")
        values["from_date"] = filters.from_date
    elif filters.get("to_date"):
        conditions.append("v.visit_date <= %(to_date)s")
        values["to_date"] = filters.to_date

    # Marketplace
    if filters.get("marketplace"):
        conditions.append("v.marketplace = %(marketplace)s")
        values["marketplace"] = filters.marketplace

    # Owner
    if filters.get("owner"):
        conditions.append("v.owner = %(owner)s")
        values["owner"] = filters.owner

    # Search
    if filters.get("search"):
        values["search_like"] = f"%{filters.search.strip()}%"
        conditions.append("""
            (
                v.customer_name LIKE %(search_like)s
                OR v.mobile_number LIKE %(search_like)s
                OR v.order_id LIKE %(search_like)s
                OR v.name LIKE %(search_like)s
            )
        """)

    where_clause = " AND ".join([c.strip() for c in conditions])

    rows = frappe.db.sql(
        f"""
        SELECT
            v.name, v.owner, v.customer, v.customer_name,
            v.visit_date, v.visit_time,
            v.mobile_number, v.alternate_mobile_number,
            v.marketplace, v.order_id, v.next_order_date,
            v.brands_available_in_shop, v.most_selling_product_and_brand,
            v.opinion_on_credit_system, v.thoughts_on_gbru_product_and_quality,
            v.additional_remarks,

            v.loc_name, v.loc_street, v.loc_country_code, v.loc_country,
            v.loc_postal_code, v.loc_administrative_area, v.loc_sub_administrative_area,
            v.loc_locality, v.loc_sub_locality,

            v.lattitude, v.longitude,

            v.creation, v.modified
        FROM `tabVisit` v
        WHERE {where_clause}
        ORDER BY v.creation DESC
        """,
        values=values,
        as_dict=True
    )

    # Registration status by mobile (Dealer/Farmer)
    mobile_numbers = list({r.get("mobile_number") for r in rows if r.get("mobile_number")})
    dealer_map, farmer_map = {}, {}

    if mobile_numbers:
        dealer_docs = frappe.get_all(
            "Delear Registration",
            filters={"mobile_number": ["in", mobile_numbers]},
            fields=["mobile_number", "docstatus"]
        )
        farmer_docs = frappe.get_all(
            "Farmer Registration",
            filters={"mobile_number": ["in", mobile_numbers]},
            fields=["mobile_number", "docstatus"]
        )
        dealer_map = {d.mobile_number: d.docstatus for d in dealer_docs}
        farmer_map = {f.mobile_number: f.docstatus for f in farmer_docs}

    data = []
    for r in rows:
        # Combine date + time into Datetime for report
        visit_datetime = None
        if r.get("visit_date"):
            if r.get("visit_time"):
                visit_datetime = get_datetime(f"{r['visit_date']} {r['visit_time']}")
            else:
                visit_datetime = get_datetime(str(r["visit_date"]))

        docstatus = dealer_map.get(r.get("mobile_number")) or farmer_map.get(r.get("mobile_number"))
        profile_status = "Registered" if docstatus == 1 else "Unregistered"

        # optional profile filter
        if filters.get("profile_status") and filters.profile_status != profile_status:
            continue

        data.append({
            **r,
            "visit_datetime": visit_datetime,
            "status": "Completed",
            "profile_status": profile_status
        })

    return data