import frappe
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	data = get_data(filters)
	report_summary = get_report_summary(data)
	return get_columns(), data, None, None, report_summary

def is_accounts_manager():
	return "Accounts Manager" in frappe.get_roles()
def validate_filters(filters):
	if not filters.get("company"):
		frappe.throw("Company is required")

	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw("From Date and To Date are required")

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw("From Date cannot be after To Date")


def get_columns():
	return [
		{"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date", "width": 110},
		{"fieldname": "warrior", "label": "Warrior", "fieldtype": "Link", "options": "User", "width": 210},
		{"fieldname": "entry_type", "label": "Entry Type", "fieldtype": "Data", "width": 130},
		{"fieldname": "voucher_type", "label": "Voucher Type", "fieldtype": "Data", "width": 170},
		{"fieldname": "voucher_no", "label": "Voucher No", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 180},
		{"fieldname": "payment_entry", "label": "Payment Entry", "fieldtype": "Link", "options": "Payment Entry", "width": 180},
		{"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "customer_name", "label": "Customer Name", "fieldtype": "Data", "width": 180},
		{"fieldname": "sales_order", "label": "Sales Order", "fieldtype": "Link", "options": "Sales Order", "width": 160},
		{"fieldname": "van_payment_mode", "label": "Van Payment Mode", "fieldtype": "Data", "width": 140},
		{"fieldname": "utr_no", "label": "UTR No", "fieldtype": "Data", "width": 150},
		{"fieldname": "debit", "label": "Debit", "fieldtype": "Currency", "width": 120},
		{"fieldname": "credit", "label": "Credit", "fieldtype": "Currency", "width": 120},
		{"fieldname": "balance", "label": "Balance", "fieldtype": "Currency", "width": 130},
		{"fieldname": "remarks", "label": "Remarks", "fieldtype": "Data", "width": 240},
	]

def get_data(filters):
	transactions = get_transactions(filters)
	warriors = sorted({row.warrior for row in transactions if row.warrior})
	opening_balances = get_opening_balances(filters, warriors)

	rows = []
	current_warrior = None
	balance = flt(0)
	opening_balance = flt(0)
	total_collected = flt(0)
	total_settled = flt(0)

	grand_opening = flt(0)
	grand_collected = flt(0)
	grand_settled = flt(0)
	grand_closing = flt(0)

	for warrior in warriors:
		grand_opening += flt(opening_balances.get(warrior, 0))

	# Grand Opening Row
	if is_accounts_manager() and warriors:
		rows.append({
			"posting_date": filters.from_date,
			"warrior": "ALL WARRIORS",
			"entry_type": "GRAND OPENING",
			"voucher_type": "",
			"voucher_no": "",
			"debit": 0,
			"credit": 0,
			"balance": grand_opening,
			"remarks": "Grand Opening Balance"
		})

	for row in transactions:
		if row.warrior != current_warrior:

			if current_warrior:
				grand_closing += balance

				rows.append(
					get_closing_row(
						filters,
						current_warrior,
						opening_balance,
						total_collected,
						total_settled,
						balance,
					)
				)

			current_warrior = row.warrior
			opening_balance = flt(opening_balances.get(current_warrior, 0))
			balance = opening_balance
			total_collected = flt(0)
			total_settled = flt(0)

			rows.append(
				get_opening_row(
					filters,
					current_warrior,
					opening_balance,
				)
			)

		collected = flt(row.collected)
		settled = flt(row.settled)

		balance += collected - settled
		total_collected += collected
		total_settled += settled

		grand_collected += collected
		grand_settled += settled

		rows.append({
			"posting_date": row.posting_date,
			"warrior": row.warrior,
			"entry_type": row.entry_type,
			"voucher_type": row.voucher_type,
			"voucher_no": row.voucher_no,
			"payment_entry": row.payment_entry,
			"customer": row.customer,
			"customer_name": row.customer_name,
			"sales_order": row.sales_order,
			"van_payment_mode": row.van_payment_mode,
			"utr_no": row.utr_no,
			"debit": collected,
			"credit": settled,
			"balance": balance,
			"remarks": row.remarks,
		})

	if current_warrior:
		grand_closing += balance

		rows.append(
			get_closing_row(
				filters,
				current_warrior,
				opening_balance,
				total_collected,
				total_settled,
				balance,
			)
		)

	# Grand Total Row
	if is_accounts_manager() and warriors:
		rows.append({
			"posting_date": filters.to_date,
			"warrior": "ALL WARRIORS",
			"entry_type": "GRAND TOTAL",
			"voucher_type": "",
			"voucher_no": "",
			"debit": grand_collected,
			"credit": grand_settled,
			"balance": grand_closing,
			"remarks":
				f"Opening: {grand_opening} | "
				f"Collected: {grand_collected} | "
				f"Settled: {grand_settled} | "
				f"Closing: {grand_closing}"
		})

	return rows

def get_opening_row(filters, warrior, balance):
	return {
		"posting_date": filters.from_date,
		"warrior": warrior,
		"entry_type": "Opening",
		"voucher_type": "Opening",
		"voucher_no": "",
		"debit": 0,
		"credit": 0,
		"balance": balance,
	}

def get_closing_row(filters, warrior, opening_balance, total_collected, total_settled, balance):
	return {
		"posting_date": filters.to_date,
		"warrior": warrior,
		"entry_type": "Closing",
		"voucher_type": "Closing",
		"voucher_no": "",
		"debit": total_collected,
		"credit": total_settled,
		"balance": balance,
		"remarks": (
			f"Opening: {opening_balance} | "
			f"Collected: {total_collected} | "
			f"Settled: {total_settled} | "
			f"Closing: {balance}"
		),
	}

def get_report_summary(data):
	opening = sum(flt(row.get("balance")) for row in data if row.get("entry_type") == "Opening")
	collected = sum(flt(row.get("debit")) for row in data if row.get("entry_type") == "Collected")
	settled = sum(flt(row.get("credit")) for row in data if row.get("entry_type") == "Settled")
	closing = sum(flt(row.get("balance")) for row in data if row.get("entry_type") == "Closing")

	return [
		{
			"label": "Opening",
			"value": opening,
			"datatype": "Currency",
			"indicator": "blue",
		},
		{
			"label": "Collected",
			"value": collected,
			"datatype": "Currency",
			"indicator": "green",
		},
		{
			"label": "Closing",
			"value": closing,
			"datatype": "Currency",
			"indicator": "red" if closing else "green",
		},
	]

def get_opening_balances(filters, warriors):
	if not warriors:
		return {}

	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"warriors": tuple(warriors),
	}

	user_filter = ""

	if not is_accounts_manager():
		values["current_user"] = frappe.session.user
		user_filter = " AND warrior = %(current_user)s "

	rows = frappe.db.sql(
		f"""
		SELECT warrior, SUM(collected - settled) AS opening
		FROM (
			SELECT
				COALESCE(NULLIF(vt.created_by, ''), NULLIF(vt.van_warrior, ''), 'Not Set') AS warrior,
				vt.transaction_amount AS collected,
				0 AS settled
			FROM `tabVan Transactions` vt
			LEFT JOIN `tabPayment Entry` pe
				ON pe.name = vt.payment_entry
			WHERE vt.docstatus = 1
				AND COALESCE(pe.company, vt.company) = %(company)s
				AND COALESCE(pe.posting_date, DATE(vt.created_at), DATE(vt.creation)) < %(from_date)s

			UNION ALL

			SELECT
				COALESCE(NULLIF(vpr.reference_warrior, ''), NULLIF(vt.created_by, ''), NULLIF(vt.van_warrior, ''), 'Not Set') AS warrior,
				0 AS collected,
				vpr.received_amount AS settled
			FROM `tabVan Payment Reconciliation` vpr
			LEFT JOIN `tabVan Transactions` vt
				ON vt.name = vpr.reference_van_payment_submission
			LEFT JOIN `tabPayment Entry` pe
				ON pe.name = vpr.payment_entry
			LEFT JOIN `tabAccount` company_account
				ON company_account.name = vpr.company_account
			LEFT JOIN `tabAccount` received_account
				ON received_account.name = vpr.received_bank_account
			WHERE vpr.docstatus = 1
				AND COALESCE(pe.company, company_account.company, received_account.company) = %(company)s
				AND vpr.posting_date < %(from_date)s
		) ledger
		WHERE warrior IN %(warriors)s
		{user_filter}
		GROUP BY warrior
		""",
		values,
		as_dict=True,
	)

	return {row.warrior: flt(row.opening) for row in rows}

def get_transactions(filters):
	values = dict(filters)

	user_condition_collected = ""
	user_condition_settled = ""

	if not is_accounts_manager():
		values["current_user"] = frappe.session.user

		user_condition_collected = """
			AND COALESCE(
				NULLIF(vt.created_by, ''),
				NULLIF(vt.van_warrior, ''),
				'Not Set'
			) = %(current_user)s
		"""

		user_condition_settled = """
			AND COALESCE(
				NULLIF(vpr.reference_warrior, ''),
				NULLIF(vt.created_by, ''),
				NULLIF(vt.van_warrior, ''),
				'Not Set'
			) = %(current_user)s
		"""

	query = f"""
		SELECT *
		FROM (
			SELECT
				COALESCE(NULLIF(vt.created_by, ''), NULLIF(vt.van_warrior, ''), 'Not Set') AS warrior,
				COALESCE(pe.posting_date, DATE(vt.created_at), DATE(vt.creation)) AS posting_date,
				'Collected' AS entry_type,
				'Van Transactions' AS voucher_type,
				vt.name AS voucher_no,
				vt.payment_entry,
				vt.customer,
				vt.customer_name,
				vt.sales_order,
				vt.van_payment_mode,
				NULL AS utr_no,
				vt.transaction_amount AS collected,
				0 AS settled,
				vt.remark AS remarks,
				vt.creation AS creation
			FROM `tabVan Transactions` vt
			LEFT JOIN `tabPayment Entry` pe
				ON pe.name = vt.payment_entry
			WHERE vt.docstatus = 1
				AND COALESCE(pe.company, vt.company) = %(company)s
				AND COALESCE(pe.posting_date, DATE(vt.created_at), DATE(vt.creation))
					BETWEEN %(from_date)s AND %(to_date)s
				{user_condition_collected}

			UNION ALL

			SELECT
				COALESCE(NULLIF(vpr.reference_warrior, ''), NULLIF(vt.created_by, ''), NULLIF(vt.van_warrior, ''), 'Not Set') AS warrior,
				vpr.posting_date,
				'Settled' AS entry_type,
				'Van Payment Reconciliation' AS voucher_type,
				vpr.name AS voucher_no,
				vpr.payment_entry,
				vt.customer,
				vt.customer_name,
				vt.sales_order,
				vt.van_payment_mode,
				vpr.utr_no,
				0 AS collected,
				vpr.received_amount AS settled,
				COALESCE(vpr.remarks, vt.remark) AS remarks,
				vpr.creation
			FROM `tabVan Payment Reconciliation` vpr
			LEFT JOIN `tabVan Transactions` vt
				ON vt.name = vpr.reference_van_payment_submission
			LEFT JOIN `tabPayment Entry` pe
				ON pe.name = vpr.payment_entry
			LEFT JOIN `tabAccount` company_account
				ON company_account.name = vpr.company_account
			LEFT JOIN `tabAccount` received_account
				ON received_account.name = vpr.received_bank_account
			WHERE vpr.docstatus = 1
				AND COALESCE(pe.company, company_account.company, received_account.company) = %(company)s
				AND vpr.posting_date BETWEEN %(from_date)s AND %(to_date)s
				{user_condition_settled}
		) ledger
		ORDER BY warrior, posting_date, creation, voucher_no
	"""

	return frappe.db.sql(query, values, as_dict=True)