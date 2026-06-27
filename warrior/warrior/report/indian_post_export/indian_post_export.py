import frappe
from frappe.utils import today

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters or {})
	return columns, data


# ✅ FULL INDIA POST HEADER (MATCHED)
def get_columns():
    return [
        {"label": "Serial Number", "fieldname": "serial_number", "width": 100},
        {"label": "Barcode Number", "fieldname": "barcode_number", "width": 150},
        {"label": "Physical Weight", "fieldname": "physical_weight", "width": 120},
        {"label": "COD", "fieldname": "cod", "width": 120},
        {"label": "Receiver City", "fieldname": "receiver_city", "width": 150},
        {"label": "Receiver Pincode", "fieldname": "receiver_pincode", "width": 120},
        {"label": "Receiver Name", "fieldname": "receiver_name", "width": 180},
        {"label": "Receiver Address Line 1", "fieldname": "addr1", "width": 200},
        {"label": "Receiver Address Line 2", "fieldname": "addr2", "width": 200},
        {"label": "Receiver Address Line 3", "fieldname": "addr3", "width": 200},
        {"label": "Ack", "fieldname": "ack", "width": 100},
        {"label": "Sender Mobile Number", "fieldname": "sender_mobile", "width": 140},
        {"label": "Receiver Mobile Number", "fieldname": "receiver_mobile", "width": 140},
        {"label": "Sender Name", "fieldname": "sender_name", "width": 180},
        {"label": "Sender Company Name", "fieldname": "sender_company", "width": 180},
        {"label": "Sender City", "fieldname": "sender_city", "width": 140},
        {"label": "Sender Pincode", "fieldname": "sender_pincode", "width": 120},
        {"label": "Sender Email ID", "fieldname": "sender_email", "width": 180},
        {"label": "Sender Alt Contact", "fieldname": "sender_alt", "width": 140},
        {"label": "Sender KYC", "fieldname": "sender_kyc", "width": 140},
        {"label": "Sender Tax", "fieldname": "sender_tax", "width": 140},
        {"label": "Receiver Company Name", "fieldname": "receiver_company", "width": 180},
        {"label": "Receiver State/UT", "fieldname": "receiver_state", "width": 140},
        {"label": "Receiver Email ID", "fieldname": "receiver_email", "width": 180},
        {"label": "Receiver Alt Contact", "fieldname": "receiver_alt", "width": 140},
        {"label": "Receiver KYC", "fieldname": "receiver_kyc", "width": 140},
        {"label": "Receiver Tax Ref", "fieldname": "receiver_tax", "width": 140},
        {"label": "Bulk Reference", "fieldname": "bulk_reference", "width": 180},
        {"label": "Alt Address Flag", "fieldname": "alt_flag", "width": 120},
        {"label": "Sender Address Line 1", "fieldname": "s_addr1", "width": 200},
        {"label": "Sender Address Line 2", "fieldname": "s_addr2", "width": 200},
        {"label": "Sender Address Line 3", "fieldname": "s_addr3", "width": 200},
		{"label": "Receiver State/UT", "fieldname": "receiver_state", "width": 140},
        {"label": "Prepayment Code", "fieldname": "prepayment_code", "width": 140},
        {"label": "Value Of Prepayment", "fieldname": "prepayment_value", "width": 140},
        {"label": "COD R/COD", "fieldname": "cod_type", "width": 120},
        {"label": "Insurance Type", "fieldname": "insurance_type", "width": 140},
        {"label": "Value Of Insurance", "fieldname": "insurance_value", "width": 140},
        {"label": "Shape Of Article", "fieldname": "shape", "width": 140},
        {"label": "Priority Flag", "fieldname": "priority", "width": 120},
        {"label": "Delivery Instruction", "fieldname": "delivery_instruction", "width": 200},
        {"label": "Delivery Slot", "fieldname": "delivery_slot", "width": 150},
        {"label": "Instruction RTS", "fieldname": "rts", "width": 120},
        {"label": "Length", "fieldname": "length", "width": 100},
        {"label": "Breadth", "fieldname": "breadth", "width": 100},
        {"label": "Height", "fieldname": "height", "width": 100},
    ]


# ✅ DATA LOGIC
def get_data(filters):
	if filters.get("from_date") and filters.get("to_date"):
		filters["created_at"] = ["between", [filters["from_date"], filters["to_date"]]]
	invoices = frappe.get_all(
	"Sales Invoice",
	pluck="name",
	filters={
		"posting_date": ["between", ["2026-04-01", today()]]
		}
	)
	filters={"is_cancelled": 0,"reference_name":["in", invoices]}
	# if filters.get("from_date") and filters.get("to_date"):
	# 	filters["created_at"] = ["between", [filters["from_date"], filters["to_date"]]]
	logs = frappe.get_all(
		"Indian Post Tracking Log",
		filters=filters,
		fields=[
			"name", "tracking_id", "total_weight", "amount", "payment_status",
			"customer", "customer_address", "customer_contact",
			"company", "company_address",
			"length_cm", "breadth_cm", "height_cm",
			"sales_order","created_at"
		]
	)

	data = []
	serial = 1

	for log in logs:

		# Receiver
		customer_name = frappe.db.get_value("Customer", log.customer, "customer_name")

		address = frappe.db.get_value(
			"Address",
			log.customer_address,
			["address_line1", "address_line2", "city", "state", "custom_tahshil", "custom_district", "pincode", "email_id"],
			as_dict=True
		) or {}

		# # Sender
		# company_address = frappe.db.get_value(
		# 	"Address",
		# 	log.company_address,
		# 	["address_line1", "address_line2", "city", "state", "custom_tahshil", "custom_district", "pincode", "phone", "email_id"],
		# 	as_dict=True
		# ) or {}

		# COD logic
		receiver_city=frappe.db.get_value("Marketplace", address.get("city"), "marketplace_name") if address.get("city") else ""
		receiver_tahsil=frappe.db.get_value("Tahshil", address.get("custom_tahshil"), "tahshil") if address.get("custom_tahshil") else ""
		receiver_district=frappe.db.get_value("District", address.get("custom_district"), "district_name") if address.get("custom_district") else ""
		addr3 = ", ".join(filter(None, [
			address.get("address_line1"),
			address.get("address_line2"),
			receiver_city,
			receiver_tahsil,
			receiver_district,
			address.get("state"),
			address.get("pincode"),
		]))
		data.append({
			"serial_number": serial,
			"barcode_number": log.tracking_id,
			"physical_weight": log.total_weight,
			"cod": log.amount,
			"date": log.created_at,
			"receiver_city": receiver_city,
			"receiver_pincode": address.get("pincode"),
			"receiver_state": address.get("state"),
			"receiver_name": customer_name,
			"addr1": receiver_tahsil,
			"addr2": receiver_city,
			"addr3": addr3,
			"ack": "FALSE",
			"sender_mobile": "9114151617",
			"receiver_mobile": log.customer_contact,
			"sender_name": log.company,
			"sender_company": log.company,
			"sender_city": "Pune",
			"sender_state":"Maharashtra",
			"sender_pincode": "412308",
			"sender_email": "",
			"sender_alt": "",
			"sender_kyc": "",
			"sender_tax": "",
			"receiver_company": "",
			"receiver_email": address.get("email_id"),
			"receiver_alt": "",
			"receiver_kyc": "",
			"receiver_tax": "",
			"bulk_reference": "",
			"alt_flag": "FALSE",
			"s_addr1": "Survey Number :133/3/9, Saswad Rd, behind Laxmi Hotel",
			"s_addr2": "Uruli Devachi, Pune, Haveli, Maharashtra 412308",
			"s_addr3": "",
			"prepayment_code": "",
			"prepayment_value": "",
			"cod_type": "COD",
			"insurance_type": "",
			"insurance_value": "",
			"shape": "",
			"priority": "",
			"delivery_instruction": "",
			"delivery_slot": "",
			"rts": "",
			"length": log.length_cm,
			"breadth": log.breadth_cm,
			"height": log.height_cm,
		})

		serial += 1

	return data

import frappe
from openpyxl import Workbook
from frappe.utils import today
from frappe.core.doctype.access_log.access_log import make_access_log


@frappe.whitelist()
def download_excel(filters=None):
    filters = frappe.parse_json(filters)

    result = execute(filters)
    columns = result[0]
    data = result[1]

    wb = Workbook()
    ws = wb.active

    # 🔹 Header
    ws.append(["CUSTOMER NAME :- Shoption Pvt Ltd"])
    ws.append(["CUSTOMER ID :- Sptn9114151617"])
    ws.append(["MOBILE NUMBER :- 9114151617 / 9114151617"])
    ws.append(["CONTRACT NO :- "])
    ws.append([f"DATE :- {today()}"])

    ws.append([])

    # 🔹 Column Headers
    ws.append([col["label"] for col in columns])

    # 🔹 Data Rows
    for row in data:
        ws.append([row.get(col["fieldname"]) for col in columns])

    # 🔹 Save File
    file_name = f"India_Post_Export_{today()}.xlsx"
    file_path = f"/files/{file_name}"
    full_path = frappe.get_site_path(file_path)

    wb.save(full_path)

    # ✅ ACCESS LOG (IMPORTANT)
    make_access_log(
        doctype="Indian Post Tracking Log",
        document=None,
        file_type="XLSX",
        method="Report Export",
        page="/app/query-report/Indian Post Export"
    )

    return file_path