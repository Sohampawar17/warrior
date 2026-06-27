import json

import frappe
from frappe.utils import (
    fmt_money,
    getdate,
    today,
    cint,
add_months,
flt,
get_url,
)
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url



def attach_file(fieldname, doctype, docname):
    uploaded_file = frappe.request.files.get("image")
    if not uploaded_file:
        return None

    if not frappe.has_permission(doctype, "write", docname):
        frappe.throw("Not permitted")

    file_doc = save_file(
        fname=uploaded_file.filename,
        content=uploaded_file.stream.read(),
        dt=doctype,
        dn=docname,
        df=fieldname,
        is_private=0
    )

    return file_doc.file_url
from frappe.utils import getdate, today, add_months, cint, fmt_money

@frappe.whitelist()
@validate_method(methods=["GET"])
def get_expense_claims_list(page=1, page_size=20, from_date=None, to_date=None):
    try:
        page = cint(page) or 1
        page_size = cint(page_size) or 20
        
        # Handle date range
        if from_date and to_date:
            from_date = getdate(from_date)
            to_date = getdate(to_date)
            if from_date > to_date:
                return api_response(False, "From date cannot be greater than To date")
        else:
            from_date = add_months(today(), -1)
            to_date = today()
        
        global_defaults = get_global_defaults()
        
        # Get employee for current user
        emp_data = get_employee_by_user(frappe.session.user)
        if not emp_data:
            return api_response(False, "Employee does not exist")
        
        employee_name = emp_data[0]["name"] if isinstance(emp_data, list) else emp_data.get("name")
        
        # Filters for child table expense_date
        filters = {
            "employee": employee_name
        }
        
        fields = [
            "`tabExpense Claim`.name",
            "`tabExpense Claim`.employee",
            "`tabExpense Claim`.employee_name",
            "`tabExpense Claim`.approval_status",
            "`tabExpense Claim`.status",
            "`tabExpense Claim`.expense_approver",
            "`tabExpense Claim`.total_claimed_amount",
            "`tabExpense Claim`.posting_date",
            "`tabExpense Claim`.company",
            "`tabExpense Claim Detail`.expense_type",
            "`tabExpense Claim Detail`.description",
            "`tabExpense Claim Detail`.expense_date",
            "count(`tabExpense Claim Detail`.expense_type) as total_expenses",
        ]
        
        # Get Expense Claims where at least one child has expense_date in range
        claims = frappe.db.sql("""
            SELECT 
                `tabExpense Claim`.name,
                `tabExpense Claim`.employee,
                `tabExpense Claim`.employee_name,
                `tabExpense Claim`.approval_status,
                `tabExpense Claim`.status,
                `tabExpense Claim`.expense_approver,
                `tabExpense Claim`.total_claimed_amount,
                `tabExpense Claim`.posting_date,
                `tabExpense Claim`.company,
                `tabExpense Claim Detail`.expense_type,
                `tabExpense Claim Detail`.description,
                `tabExpense Claim Detail`.expense_date,
                COUNT(`tabExpense Claim Detail`.expense_type) as total_expenses
            FROM `tabExpense Claim`
            LEFT JOIN `tabExpense Claim Detail` 
                ON `tabExpense Claim Detail`.parent = `tabExpense Claim`.name
            WHERE `tabExpense Claim`.employee = %(employee)s
                AND `tabExpense Claim Detail`.expense_date BETWEEN %(from_date)s AND %(to_date)s
            GROUP BY `tabExpense Claim`.name
            ORDER BY `tabExpense Claim`.posting_date DESC
            LIMIT %(start)s, %(page_size)s
        """, {
            "employee": employee_name,
            "from_date": from_date,
            "to_date": to_date,
            "start": (page - 1) * page_size,
            "page_size": page_size
        }, as_dict=True)
        
        # Format currency
        for expense in claims:
            expense["total_claimed_amount"] = fmt_money(
                expense["total_claimed_amount"],
                currency=global_defaults.get("default_currency"),
            )
        
        # Total records
        total_records = frappe.db.count(
            "Expense Claim",
            filters={"employee": employee_name}
        )
        total_pages = (total_records + page_size - 1) // page_size
        
        return api_response(True, "Expense data get successfully", {
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "data": claims
        })

    except Exception as e:
        return api_response(False, str(e))

# Helper to get month wise details
def get_month_year_details(expense):
    date = getdate(expense.get("posting_date"))
    month = date.strftime("%B")
    year = date.year
    return f"{month} {year}"


# get totals for expense
@frappe.whitelist()
@validate_method(methods=["GET"])
def get_expense_claim_type_totals():
    try:
        global_defaults = get_global_defaults()
        emp_data = get_employee_by_user(frappe.session.user)
        if not len(emp_data) >= 1:
            return api_response(False, "Employee does not exists")
        filters = frappe._dict()
        filters.employee = emp_data.get("name")
        filters.approval_status = "Approved"
        fields = [
            "`tabExpense Claim`.name",
            "`tabExpense Claim`.employee",
            "`tabExpense Claim`.employee_name",
            "`tabExpense Claim Detail`.expense_type",
            "sum(`tabExpense Claim Detail`.amount) as total_amount",
        ]

        claims = frappe.get_list(
            "Expense Claim",
            fields=fields,
            filters=filters,
            order_by="`tabExpense Claim`.posting_date desc",
            group_by="`tabExpense Claim Detail`.expense_type",
        )

        for claim in claims:
            claim["total_amount_currency"] = fmt_money(
                claim["total_amount"], currency=global_defaults.get("default_currency")
            )

        return api_response(True, "Expense date get successfully", claims)
    except Exception as e:
        return api_response(False, str(e))


@frappe.whitelist()
def get_expense_type():
    try:
        expense_types = frappe.get_all(
            "Expense Claim Type", filters={}, pluck="name"
        )
        return api_response(True, "Expense type get successfully", expense_types)
    except Exception as e:
        return api_response(False, str(e))


# create new expense
@frappe.whitelist()
@validate_method(methods=["POST"])
def apply_expense():
    try:
        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company", "expense_approver"]
        )

        if not len(emp_data) >= 1:
            return api_response(True, "Employee does not exists")
        cost_center = (
            frappe.get_value("Company", emp_data.get("company"), "cost_center")
            or frappe.defaults.get_global_default("cost_center")
        )
        payable_account = get_payable_account(emp_data.get("company"))
        expense_doc = frappe.get_doc(
            doctype="Expense Claim",
            employee=emp_data.name,
            expense_approver=emp_data.expense_approver,
            expenses=[
                {
                    "expense_date": frappe.form_dict.expense_date,
                    "expense_type": frappe.form_dict.expense_type,
                    "description": frappe.form_dict.description,
                    "amount": frappe.form_dict.amount,
                    "sanctioned_amount": frappe.form_dict.amount,
                    "cost_center": cost_center
                }
            ],
            posting_date=today(),
            company=emp_data.get("company"),
            payable_account=payable_account,
        ).insert()

        from frappe.utils.file_manager import save_file

        if frappe.request.files:
            files = frappe.request.files.getlist("file")

            for f in files:
                file_doc = save_file(
                    f.filename,
                    f.stream.read(),
                    "Expense Claim",
                    expense_doc.name,
                    is_private=0
                )

        return api_response(True, "Expense applied Successfully")
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(),title= "Expense applied API Error")
        return api_response(False, str(e))


@frappe.whitelist()
def get_expense_ledger(from_date=None, to_date=None):
    try:
        user = frappe.session.user

        from_date = getdate(from_date) if from_date else getdate(add_months(today(), -1))
        to_date = getdate(to_date) if to_date else getdate(today())

        emp_data = get_employee_by_user(user, fields=["name", "company"])

        if not emp_data:
            return api_response(False, "Employee does not exist")

        if isinstance(emp_data, list):
            if not emp_data:
                return api_response(False, "Employee does not exist")
            emp_data = emp_data[0]

        employee = emp_data.get("name")
        if not employee:
            return api_response(False, "Employee does not exist")

        values = {
            "employee": employee,
            "from_date": from_date,
            "to_date": to_date
        }

        opening_balance = flt(
            frappe.db.sql(
                """
                SELECT COALESCE(SUM(ec.grand_total), 0)
                FROM `tabExpense Claim` ec
                WHERE ec.employee = %(employee)s
                  AND ec.docstatus = 1
                  AND ec.posting_date < %(from_date)s
                """,
                values
            )[0][0]
        )

        entries = frappe.db.sql(
            """
            SELECT
                ec.posting_date AS date,
                ec.grand_total AS amount,
                ec.approval_status AS transaction_type,
                ec.name AS reference_name,
                'Expense Claim' AS reference_doctype
            FROM `tabExpense Claim` ec
            WHERE ec.employee = %(employee)s
              AND ec.docstatus = 1
              AND ec.posting_date >= %(from_date)s
              AND ec.posting_date <= %(to_date)s
            ORDER BY ec.posting_date DESC, ec.creation DESC
            """,
            values=values,
            as_dict=True
        )

        period_total = sum(flt(row.amount) for row in entries)
        closing_balance = opening_balance + period_total

        return api_response(
            True,
            "Expense ledger fetched successfully",
            {
                "from_date": str(from_date),
                "to_date": str(to_date),
                "opening_balance": opening_balance,
                "closing_balance": closing_balance,
                "entries": entries
            }
        )

    except Exception:
        frappe.log_error(message=frappe.get_traceback(),title= "Expense Ledger API Error")
        return api_response(False, "Something went wrong while fetching expense ledger")

# update expense
@frappe.whitelist()
@validate_method(methods=["POST"])
def update_expense(**data):
    try:
        emp_data = get_employee_by_user(frappe.session.user, fields=["name", "company"])

        if not len(emp_data) >= 1:
            return api_response(False, "Employee does not exists")

        if not frappe.db.exists(
            "Expense Claim", {"name": data.get("id"), "employee": emp_data.name}
        ):
            return api_response(False, "Invalid ID")

        expense_doc = frappe.get_doc("Expense Claim", data.get("id"))
        expense_doc.update(data)
        expense_doc.save(ignore_permissions=True)

        if data.get("attachments") is not None:
            for file in data.get("attachments"):
                frappe.get_doc(
                    doctype="File",
                    file_url=file.get("file_url"),
                    attached_to_doctype="Expense Claim",
                    attached_to_name=expense_doc.name,
                ).insert(ignore_permissions=True)

        return api_response(True, "Expense updated Successfully", expense_doc)
    except Exception as e:
        return api_response(False, str(e))


def get_payable_account(company):
    default_payable_account = frappe.db.get_value(
        "Company", company, "default_payable_account"
    )

    if not default_payable_account:
        frappe.throw("Please set Default Payable Account in Company Settings")

    return default_payable_account


@frappe.whitelist()
def get_expense(name):
    try:
        # Validate the input
        if not name:
            return api_response(False, "Expense ID is required")

        # Get logged-in employee
        emp_data = get_employee_by_user(
            frappe.session.user, fields=["name", "company", "expense_approver"]
        )

        if not emp_data:
            return api_response(False, "Employee does not exist")

        # Check if the Expense Claim exists
        if not frappe.db.exists("Expense Claim", {"name": name}):
            return api_response(False, f"Expense Claim {name} not found")

        # Fetch Expense Claim
        expense = frappe.get_doc("Expense Claim", name)

        # Fetch first expense detail
        detail = frappe.db.get_value(
            "Expense Claim Detail",
            {"parent": expense.name},
            ["expense_type", "description", "expense_date", "amount"],
            as_dict=True,
        )
        base_url = frappe.utils.get_url()

        attachments = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": "Expense Claim",
                "attached_to_name": expense.name,
                "is_folder": 0,
            },
            fields=["name", "file_name", "file_url"],
        )

        # Prepare response
        expense_json = {
            "name": expense.name,
            "expense_approver": frappe.db.get_value("User", expense.expense_approver, "full_name") if expense.expense_approver else None,
            "department": expense.department,
            "expense_type": detail.expense_type if detail else None,
            "expense_description": detail.description if detail else None,
            "expense_date": detail.expense_date if detail and detail.expense_date else None,
            "amount": float(detail.amount) if detail and detail.amount else 0.0,
            "docstatus": expense.docstatus,
            "total_sanctioned_amount":expense.total_sanctioned_amount,
            "total_claimed_amount": expense.total_claimed_amount,
            "attachments":  [
            {
                **file,
                "file_url": base_url + file["file_url"] if file.get("file_url") else ""
            }
            for file in attachments
        ]
        }
        
        return api_response(True, "Expense fetched successfully", expense_json)

    except Exception as e:
        return api_response(False, str(e))

def get_attachments(id):
    return frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Expense Claim", "attached_to_name": id},
        fields=["file_url", "file_name"],
    )