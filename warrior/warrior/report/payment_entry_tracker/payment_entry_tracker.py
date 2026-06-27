import frappe
from frappe.utils import getdate, now_datetime, get_datetime, add_to_date


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": "Payment Entry ID",
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Payment Entry",
			"width": 150,
		},
		{
			"label": "Posting Date",
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": "Status",
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": "Party",
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 100,
		},
		{
			"label": "Party Name",
			"fieldname": "party_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": "Purchase Order ID",
			"fieldname": "custom_purchase_order_id",
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 170,
		},
		{
			"label": "Payment Term",
			"fieldname": "custom_payment_term",
			"fieldtype": "Data",
			"width": 140,
		},
  {
			"label": "Payment Term Due Date",
			"fieldname": "custom_payment_term_due_date",
			"fieldtype": "Date",
			"width": 150,
		},
		{
			"label": "Purchase Order Amount",
			"fieldname": "purchase_order_amount",
			"fieldtype": "Currency",
			"width": 170,
		},
		{
			"label": "Paid Amount",
			"fieldname": "paid_amount",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": "Payment State",
			"fieldname": "custom_payment_status",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": "UTR No",
			"fieldname": "custom_utr_no",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": "Purchase Order Status",
			"fieldname": "po_workflow_state",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": "Company",
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 140,
		},
	]


def get_data(filters):
	conditions = ["pe.docstatus < 2"]
	values = {}

	if filters.get("from_date"):
		conditions.append("pe.posting_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("pe.posting_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	for key in (
		"company",
		"party",
		"party_type",
		"custom_purchase_order_id",
		"custom_payment_term",
		"custom_payment_status",
		"custom_utr_no",
		"name",
		"po_workflow_state",
	):
		if filters.get(key):
			if key == "po_workflow_state":
				conditions.append("po.workflow_state = %(po_workflow_state)s")
			else:
				conditions.append(f"pe.{key} = %({key})s")
			values[key] = filters.get(key)

	where_clause = " and ".join(conditions)

	rows = frappe.db.sql(
		f"""
		select
			pe.name,
			pe.posting_date,
			pe.company,
			pe.party_type,
			pe.workflow_state as status,
			pe.party,
			pe.party_name,

			CASE
				WHEN pe.docstatus = 1 THEN pe.paid_amount
				ELSE 0
			END as paid_amount,

			po.grand_total as purchase_order_amount,

			pe.custom_purchase_order_id,
			pe.custom_payment_term,
			pe.custom_utr_no,
			pe.custom_attachment,
			pe.custom_remark,
			pe.custom_payment_status,
			pe.custom_payment_term_due_date,
			po.workflow_state as po_workflow_state

		from `tabPayment Entry` pe

		left join `tabPurchase Order` po
			on po.name = pe.custom_purchase_order_id

		where
			{where_clause}
			AND pe.party_type = 'Supplier'

		order by pe.posting_date desc, pe.modified desc
		""",
		values,
		as_dict=True,
	)

	now_dt = now_datetime()

	for row in rows:
		primary_ref = {
			"due_date": row.get("custom_payment_term_due_date"),
			"payment_term": row.get("custom_payment_term"),
		}

		due_date = primary_ref.get("due_date")

		if due_date:
			due_dt = get_datetime(due_date)
			overdue_cutoff = add_to_date(
				due_dt,
				days=1,
				as_datetime=True,
			)

			if now_dt >= overdue_cutoff:
				row["payment_status_from"] = "Overdue"

			elif getdate(now_dt) >= getdate(due_date):
				row["payment_status_from"] = "Due"

			else:
				row["payment_status_from"] = "In Credit Period"

		else:
			if (primary_ref.get("payment_term") or "").strip():
				row["payment_status_from"] = "In Credit Period"
			else:
				row["payment_status_from"] = ""

	return rows