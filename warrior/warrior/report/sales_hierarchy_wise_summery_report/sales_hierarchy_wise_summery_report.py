# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt, getdate, is_invalid_date_string, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = get_date_range(filters)
	columns = get_columns()
	data = get_data(filters, from_date, to_date)
	return columns, data


def get_columns():
	return [
		{"label": "Executive", "fieldname": "executive_name", "fieldtype": "Data", "width": 180},
		{"label": "Order Count", "fieldname": "order_count", "fieldtype": "Int", "width": 110},
		{"label": "Order ID", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": "Order Status", "fieldname": "order_status", "fieldtype": "Data", "width": 160},
		{"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 220},
		{"label": "Marketplace", "fieldname": "marketplace", "fieldtype": "Data", "width": 150},
		{"label": "State", "fieldname": "state", "fieldtype": "Data", "width": 120},
		{"label": "District", "fieldname": "district", "fieldtype": "Data", "width": 140},
		{"label": "Tehsil", "fieldname": "tehsil", "fieldtype": "Data", "width": 140},
		{"label": "Order Amount", "fieldname": "order_amount", "fieldtype": "Currency", "width": 130},
		{"label": "Receipt Amount", "fieldname": "receipt_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Pending Amount", "fieldname": "pending_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Invoice Amount", "fieldname": "invoice_amount", "fieldtype": "Currency", "width": 120},
		{"label": "Return Amount", "fieldname": "return_amount_crn", "fieldtype": "Currency", "width": 120},
		{"label": "Products", "fieldname": "product_names", "fieldtype": "Small Text", "width": 320},
	]


def get_date_range(filters):
	from_date = parse_date(filters.get("from_date"))
	to_date = parse_date(filters.get("to_date"))

	if not from_date and not to_date:
		today = getdate(nowdate())
		return today, today
	if not from_date:
		from_date = to_date
	if not to_date:
		to_date = from_date
	if from_date > to_date:
		from_date, to_date = to_date, from_date

	return from_date, to_date


def parse_date(value):
	if not value or is_invalid_date_string(value):
		return None
	return getdate(value)


def get_data(filters, from_date, to_date):
	conditions = [
		"so.docstatus = 1",
		"so.transaction_date BETWEEN %(from_date)s AND %(to_date)s",
		"COALESCE(NULLIF(TRIM(so.custom_dispatch_status), ''), so.status) NOT IN ('CANCELLED', 'REFUNDED')",
		"""(
			COALESCE(so.advance_paid, 0) > 0
			OR EXISTS (
				SELECT 1
				FROM `tabBank Transfer Request` btr
				WHERE btr.sales_order = so.name
				  AND btr.docstatus = 0
				  AND btr.transfer_type = 'Bank Transfer'
				  AND btr.status = 'Unsettled'
			)
		)""",
	]
	params = {"from_date": from_date, "to_date": to_date}
	manager_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	allowed_employees = get_hierarchy_employee_ids(manager_employee) if manager_employee else []

	if allowed_employees:
		conditions.append("(sp.employee IN %(allowed_employees)s OR IFNULL(sp.employee, '') = '')")
		params["allowed_employees"] = tuple(allowed_employees)

	executives = normalize_filter_values(filters.get("executive"))
	if executives:
		conditions.append("sp.employee IN %(executives)s")
		params["executives"] = tuple(executives)

	products = normalize_filter_values(filters.get("product"))
	if products:
		conditions.append("soi.item_code IN %(products)s")
		params["products"] = tuple(products)

	states = normalize_filter_values(filters.get("state"))
	if states:
		conditions.append("addr.state IN %(states)s")
		params["states"] = tuple(states)

	districts = normalize_filter_values(filters.get("district"))
	if districts:
		conditions.append("addr.custom_district IN %(districts)s")
		params["districts"] = tuple(districts)

	tehsils = normalize_filter_values(filters.get("tehsil"))
	if tehsils:
		conditions.append("addr.custom_tahshil IN %(tehsils)s")
		params["tehsils"] = tuple(tehsils)

	marketplaces = normalize_filter_values(filters.get("marketplace"))
	if marketplaces:
		conditions.append("addr.city IN %(marketplaces)s")
		params["marketplaces"] = tuple(marketplaces)

	order_rows = frappe.db.sql(
		f"""
		SELECT
			so.name AS sales_order,
			sp.employee AS executive_employee,
			COALESCE(emp.employee_name, st.sales_person, 'Unassigned') AS executive_name,
			COALESCE(NULLIF(TRIM(so.custom_dispatch_status), ''), so.status) AS order_status,
			so.customer_name,
			COALESCE(m.marketplace_name, addr.city) AS marketplace,
			addr.state,
			d.district_name AS district,
			t.tahshil AS tehsil,
			so.grand_total AS order_amount,
			COALESCE(so.advance_paid, 0) AS receipt_amount,
			(so.grand_total - COALESCE(so.advance_paid, 0)) AS pending_amount,
			COALESCE(inv.invoice_amount, 0) AS invoice_amount,
			COALESCE(inv.return_amount_crn, 0) AS return_amount_crn,
			GROUP_CONCAT(DISTINCT COALESCE(soi.item_name, soi.item_code) ORDER BY soi.idx SEPARATOR ', ') AS product_names
		FROM `tabSales Order` so
		LEFT JOIN `tabSales Team` st
			ON st.parent = so.name
			AND st.parenttype = 'Sales Order'
			AND st.allocated_percentage = 100
		LEFT JOIN `tabSales Person` sp
			ON sp.name = st.sales_person
		LEFT JOIN `tabEmployee` emp
			ON emp.name = sp.employee
		LEFT JOIN `tabAddress` addr
			ON addr.name = so.shipping_address_name
		LEFT JOIN `tabMarketplace` m
			ON m.name = addr.city
		LEFT JOIN `tabDistrict` d
			ON d.name = addr.custom_district
		LEFT JOIN `tabTahshil` t
			ON t.name = addr.custom_tahshil
		LEFT JOIN (
			SELECT
				sales_order,
				SUM(invoice_amount) AS invoice_amount,
				SUM(return_amount_crn) AS return_amount_crn
			FROM (
				SELECT DISTINCT
					si.name AS invoice,
					sii.sales_order,
					CASE WHEN IFNULL(si.is_return, 0) = 0 THEN si.grand_total ELSE 0 END AS invoice_amount,
					CASE WHEN IFNULL(si.is_return, 0) = 1 THEN ABS(si.grand_total) ELSE 0 END AS return_amount_crn
				FROM `tabSales Invoice` si
				INNER JOIN `tabSales Invoice Item` sii
					ON sii.parent = si.name
				WHERE si.docstatus = 1
				  AND IFNULL(sii.sales_order, '') != ''
			) inv_rows
			GROUP BY sales_order
		) inv
			ON inv.sales_order = so.name
		INNER JOIN `tabSales Order Item` soi
			ON soi.parent = so.name
		WHERE {' AND '.join(conditions)}
		GROUP BY so.name
		ORDER BY so.transaction_date DESC, so.name DESC
		""",
		params,
		as_dict=True,
	)

	for row in order_rows:
		row.receipt_amount = flt(row.receipt_amount)
		row.order_amount = flt(row.order_amount)
		row.pending_amount = flt(row.pending_amount)
		row.invoice_amount = flt(row.invoice_amount)
		row.return_amount_crn = flt(row.return_amount_crn)

	return build_tree_rows(order_rows, manager_employee)


def build_tree_rows(order_rows, manager_employee):
	unmapped_emp_id = "UNMAPPED_ORDERS"
	employees = frappe.get_all(
		"Employee",
		filters={"status":"Active"},
		fields=["name", "employee_name", "reports_to"],
		limit_page_length=0,
	)
	emp_map = {e.name: e for e in employees}
	children_map = {}
	for e in employees:
		children_map.setdefault(e.reports_to or "", []).append(e.name)

	orders_by_emp = {}
	for row in order_rows:
		orders_by_emp.setdefault(row.get("executive_employee") or "", []).append(row)

	# Make unmapped orders part of hierarchy so parent totals (including CEO) aggregate them.
	unassigned_orders = orders_by_emp.get("", [])
	if unassigned_orders and manager_employee and manager_employee in emp_map:
		orders_by_emp[unmapped_emp_id] = unassigned_orders
		orders_by_emp.pop("", None)
		emp_map[unmapped_emp_id] = frappe._dict(
			{
				"name": unmapped_emp_id,
				"employee_name": "Unmapped Orders",
				"reports_to": manager_employee,
			}
		)
		children_map.setdefault(manager_employee, [])
		if unmapped_emp_id not in children_map[manager_employee]:
			children_map[manager_employee].append(unmapped_emp_id)

	rows = []
	added = set()
	aggregate_cache = {}

	def get_subtree_totals(emp_id):
		if emp_id in aggregate_cache:
			return aggregate_cache[emp_id]

		own_orders = orders_by_emp.get(emp_id, [])
		order_count = len(own_orders)
		order_amount = sum(flt(x.order_amount) for x in own_orders)
		receipt_amount = sum(flt(x.receipt_amount) for x in own_orders)
		pending_amount = sum(flt(x.pending_amount) for x in own_orders)
		invoice_amount = sum(flt(x.invoice_amount) for x in own_orders)
		return_amount_crn = sum(flt(x.return_amount_crn) for x in own_orders)

		for child_id in children_map.get(emp_id, []):
			c_count, c_order_amt, c_receipt_amt, c_pending_amt, c_invoice_amt, c_return_amt = get_subtree_totals(child_id)
			order_count += c_count
			order_amount += c_order_amt
			receipt_amount += c_receipt_amt
			pending_amount += c_pending_amt
			invoice_amount += c_invoice_amt
			return_amount_crn += c_return_amt

		aggregate_cache[emp_id] = (order_count, order_amount, receipt_amount, pending_amount, invoice_amount, return_amount_crn)
		return aggregate_cache[emp_id]

	def add_emp_node(emp_id, level):
		if emp_id in added or emp_id not in emp_map:
			return
		emp = emp_map[emp_id]
		emp_orders = orders_by_emp.get(emp_id, [])
		if not emp_orders and not has_ordered_child(emp_id):
			return
		subtree_count, subtree_order_amount, subtree_receipt_amount, subtree_pending_amount, subtree_invoice_amount, subtree_return_amount = get_subtree_totals(emp_id)

		row_id = f"EMP::{emp_id}"
		rows.append(
			{
				"row_id": row_id,
				"parent_row": f"EMP::{emp.reports_to}" if emp.reports_to in emp_map else "",
				"indent": level,
				"is_group": 1,
				"executive_name": emp.employee_name or emp_id,
				"order_count": subtree_count,
				"order_amount": subtree_order_amount,
				"receipt_amount": subtree_receipt_amount,
				"pending_amount": subtree_pending_amount,
				"invoice_amount": subtree_invoice_amount,
				"return_amount_crn": subtree_return_amount,
			}
		)
		added.add(emp_id)

		for order in emp_orders:
			rows.append(
				{
					"row_id": f"SO::{order.sales_order}",
					"parent_row": row_id,
					"indent": level + 1,
					"is_group": 0,
					"executive_name": order.executive_name,
					"order_count": 1,
					"sales_order": order.sales_order,
					"order_status": order.order_status,
					"customer_name": order.customer_name,
					"marketplace": order.marketplace,
					"state": order.state,
					"district": order.district,
					"tehsil": order.tehsil,
					"order_amount": order.order_amount,
					"receipt_amount": order.receipt_amount,
					"pending_amount": order.pending_amount,
					"invoice_amount": order.invoice_amount,
					"return_amount_crn": order.return_amount_crn,
					"product_names": order.product_names,
				}
			)

		for child_id in sorted(children_map.get(emp_id, [])):
			add_emp_node(child_id, level + 1)

	def has_ordered_child(emp_id):
		for child_id in children_map.get(emp_id, []):
			if orders_by_emp.get(child_id):
				return True
			if has_ordered_child(child_id):
				return True
		return False

	if manager_employee and manager_employee in emp_map:
		add_emp_node(manager_employee, 0)
	else:
		emp_ids_with_orders = sorted({x.get("executive_employee") for x in order_rows if x.get("executive_employee")})
		for emp_id in emp_ids_with_orders:
			chain = []
			current = emp_id
			while current and current in emp_map:
				chain.append(current)
				current = emp_map[current].reports_to
			for i, chain_emp in enumerate(reversed(chain)):
				add_emp_node(chain_emp, i)

	unassigned_orders = orders_by_emp.get("", [])
	if unassigned_orders:
		unassigned_id = "EMP::UNMAPPED_ORDERS"
		parent_row = ""
		indent = 0
		if manager_employee and manager_employee in emp_map:
			parent_row = f"EMP::{manager_employee}"
			indent = 1
		rows.append(
			{
				"row_id": unassigned_id,
				"parent_row": parent_row,
				"indent": indent,
				"is_group": 1,
				"executive_name": "Unmapped Orders",
				"order_count": len(unassigned_orders),
				"order_amount": sum(flt(x.order_amount) for x in unassigned_orders),
				"receipt_amount": sum(flt(x.receipt_amount) for x in unassigned_orders),
				"pending_amount": sum(flt(x.pending_amount) for x in unassigned_orders),
				"invoice_amount": sum(flt(x.invoice_amount) for x in unassigned_orders),
				"return_amount_crn": sum(flt(x.return_amount_crn) for x in unassigned_orders),
			}
		)
		for order in unassigned_orders:
			rows.append(
				{
					"row_id": f"SO::{order.sales_order}",
					"parent_row": unassigned_id,
					"indent": indent + 1,
					"is_group": 0,
					"executive_name": order.executive_name,
					"order_count": 1,
					"sales_order": order.sales_order,
					"order_status": order.order_status,
					"customer_name": order.customer_name,
					"marketplace": order.marketplace,
					"state": order.state,
					"district": order.district,
					"tehsil": order.tehsil,
					"order_amount": order.order_amount,
					"receipt_amount": order.receipt_amount,
					"pending_amount": order.pending_amount,
					"invoice_amount": order.invoice_amount,
					"return_amount_crn": order.return_amount_crn,
					"product_names": order.product_names,
				}
			)

	return rows


def get_hierarchy_employee_ids(manager_employee):
	all_employees = frappe.get_all(
		"Employee",
		filters={"status":"Active"},
		fields=["name", "reports_to"],
		limit_page_length=0,
	)
	employee_map = {emp.name: emp for emp in all_employees}
	if manager_employee not in employee_map:
		return []

	children_map = {}
	for emp in all_employees:
		children_map.setdefault(emp.reports_to or "", []).append(emp.name)

	scoped_ids = []
	seen = set()

	def collect(emp_id):
		if emp_id in seen or emp_id not in employee_map:
			return
		seen.add(emp_id)
		scoped_ids.append(emp_id)
		for child_id in children_map.get(emp_id, []):
			collect(child_id)

	collect(manager_employee)
	return scoped_ids


def normalize_filter_values(value):
	if not value:
		return []
	if isinstance(value, (list, tuple, set)):
		return [str(v).strip() for v in value if str(v).strip()]
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return []
		try:
			parsed = frappe.parse_json(text)
			if isinstance(parsed, list):
				return [str(v).strip() for v in parsed if str(v).strip()]
		except Exception:
			pass
		return [x.strip() for x in text.split(",") if x.strip()]
	return [str(value).strip()]


@frappe.whitelist()
def get_distinct_address_states(doctype=None, txt=None, searchfield=None, start=0, page_len=20, filters=None):
	txt = (txt or "").strip().lower()
	page_len = int(page_len or 20)
	start = int(start or 0)

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT addr.state
		FROM `tabAddress` addr
		WHERE IFNULL(addr.state, '') != ''
		ORDER BY addr.state
		""",
		as_dict=True,
	)

	values = [r.state for r in rows if r.get("state")]
	if txt:
		values = [v for v in values if txt in v.lower()]
	return values[start : start + page_len]
