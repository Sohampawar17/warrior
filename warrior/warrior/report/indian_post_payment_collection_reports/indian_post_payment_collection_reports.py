import frappe


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": "Date",
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": "Customer ID",
			"fieldname": "customer_id",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 170,
		},
		{
			"label": "Customer Name",
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": "Order ID",
			"fieldname": "order_id",
			"fieldtype": "Link",
			"options": "Sales Order",
			"width": 170,
		},
		{
			"label": "Tracking ID",
			"fieldname": "tracking_id",
			"fieldtype": "Data",
			"width": 170,
		},
		{
			"label": "Invoice ID",
			"fieldname": "invoice_id",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 170,
		},
		{
			"label": "Invoice Amount",
			"fieldname": "invoice_amount",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": "COD Amount",
			"fieldname": "cod_amount",
			"fieldtype": "Currency",
			"width": 140,
		},
	]


def get_data(filters):
	conditions = ["pe.docstatus = 1", "pe.payment_type = 'Receive'"]
	values = {}

	if filters.get("from_date"):
		conditions.append("pe.posting_date >= %(from_date)s")
		values["from_date"] = filters.get("from_date")

	if filters.get("to_date"):
		conditions.append("pe.posting_date <= %(to_date)s")
		values["to_date"] = filters.get("to_date")

	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters.get("customer")

	if filters.get("order_id"):
		conditions.append(
			"COALESCE(iptl.sales_order, invoice_order.sales_order) = %(order_id)s"
		)
		values["order_id"] = filters.get("order_id")

	if filters.get("tracking_id"):
		conditions.append("pe.reference_no = %(tracking_id)s")
		values["tracking_id"] = filters.get("tracking_id")

	if filters.get("invoice_id"):
		conditions.append("si.name = %(invoice_id)s")
		values["invoice_id"] = filters.get("invoice_id")

	where_clause = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			pe.posting_date AS date,
			si.customer AS customer_id,
			COALESCE(si.customer_name, customer.customer_name, si.customer) AS customer_name,
			COALESCE(iptl.sales_order, invoice_order.sales_order) AS order_id,
			pe.reference_no AS tracking_id,
			si.name AS invoice_id,
			si.rounded_total AS invoice_amount,
			pe.paid_amount AS cod_amount
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Entry Reference` per
			ON per.parent = pe.name
			AND per.reference_doctype = 'Sales Invoice'
		INNER JOIN `tabSales Invoice` si
			ON si.name = per.reference_name
			AND si.docstatus = 1
		INNER JOIN `tabIndian Post Tracking ID` tracking
			ON tracking.tracking_id = pe.reference_no
		LEFT JOIN `tabIndian Post Tracking Log` iptl
			ON iptl.reference_type = 'Sales Invoice'
			AND iptl.reference_name = si.name
			AND iptl.tracking_id = pe.reference_no
			AND IFNULL(iptl.is_cancelled, 0) = 0
		LEFT JOIN (
			SELECT parent, MIN(sales_order) AS sales_order
			FROM `tabSales Invoice Item`
			WHERE IFNULL(sales_order, '') != ''
			GROUP BY parent
		) invoice_order
			ON invoice_order.parent = si.name
		LEFT JOIN `tabCustomer` customer
			ON customer.name = si.customer
		WHERE {where_clause}
		ORDER BY pe.posting_date DESC, pe.creation DESC, si.name
		""",
		values,
		as_dict=True,
	)
