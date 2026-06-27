import frappe


def calculations(doc,method):
    # =====================================================
    # INITIALIZATION
    # =====================================================
    doc.payment_days_amount = 0

    base_salary = 0.0
    doc.custom_employer_pf = 0.0
    doc.custom_employer_esic = 0.0
    doc.custom_total_ctc = 0.0
    doc.custom_fixed_variable = 0.0
    doc.custom_c_t_c = 0.0

    # =====================================================
    # REQUIRED FIELD VALIDATION
    # =====================================================
    missing = [f for f in ("employee", "salary_structure", "start_date") if not doc.get(f)]
    if missing:
        frappe.throw(
            "Salary Slip cannot be calculated. Missing required fields:<br><br>"
            + "<br>".join(
                f"• {frappe.bold(f.replace('_', ' ').title())}" for f in missing
            )
        )

    # =====================================================
    # FETCH LATEST VALID SALARY STRUCTURE ASSIGNMENT
    # =====================================================
    base_salary = frappe.db.get_value(
        "Salary Structure Assignment",
        {
            "employee": doc.employee,
            "salary_structure": doc.salary_structure,
            "from_date": ["<=", doc.start_date],
            "docstatus": 1,
        },
        "base",
        order_by="from_date desc",
    )

    if base_salary is None:
        frappe.throw(
            "No submitted Salary Structure Assignment found for:<br><br>"
            f"• Employee: {frappe.bold(doc.employee)}<br>"
            f"• Salary Structure: {frappe.bold(doc.salary_structure)}<br>"
            f"• From Date ≤ {frappe.bold(str(doc.start_date))}"
        )

    # =====================================================
    # PAYMENT DAYS AMOUNT CALCULATION
    # =====================================================
    base_salary = float(base_salary)
    total_working_days = float(doc.total_working_days or 0)
    payment_days = float(doc.payment_days or 0)

    if base_salary <= 0:
        frappe.throw(
            f"Base salary is zero or invalid for Employee {frappe.bold(doc.employee)}."
        )

    if total_working_days <= 0:
        frappe.throw("Total Working Days must be greater than 0.")

    if payment_days <= 0:
        frappe.throw("Payment Days must be greater than 0.")

    doc.payment_days_amount = round(
        (base_salary / total_working_days) * payment_days,
        2
    )

    # =====================================================
    # EMPLOYER PROVIDENT FUND (FROM DEDUCTIONS)
    # =====================================================
    doc.custom_employer_pf = sum(
        float(d.amount or 0)
        for d in (doc.deductions or [])
        if d.salary_component == "EMPL Provident Fund"
    )

    doc.custom_expenses = sum(
        float(e.amount or 0)
        for e in (doc.earnings or [])
        if e.salary_component == "Expenses"
    )

    doc.custom_variables = sum(
        float(e.amount or 0)
        for e in (doc.earnings or [])
        if e.salary_component == "Variable"
    )

    # =====================================================
    # EMPLOYER ESIC (3.25% OF GROSS PAY)
    # =====================================================
    gross_pay = float(doc.gross_pay or 0)

    if 0 < base_salary < 21000 and gross_pay > 0:
        doc.custom_employer_esic = round(gross_pay * 3.25 / 100, 2)
    else:
        doc.custom_employer_esic = 0.0

    # =====================================================
    # TOTAL CTC (BASE + EMPLOYER PF + EMPLOYER ESIC)
    # =====================================================
    doc.custom_total_ctc = round(
        base_salary
        + doc.custom_employer_pf
        + doc.custom_employer_esic,
        2
    )

    # =====================================================
    # FETCH FIXED RATE FROM EMPLOYEE
    # =====================================================
    fixed_rate = frappe.db.get_value(
        "Employee",
        doc.employee,
        "custom_fixed_rate"
    )
    doc.custom_fixed_variable = float(fixed_rate or 0)

    # =====================================================
    # FINAL CTC (GROSS + EMPLOYER PF + EMPLOYER ESIC)
    # =====================================================
    doc.custom_c_t_c = round(
        gross_pay
        + doc.custom_employer_pf
        + doc.custom_employer_esic,
        2
    )
    doc.custom_total_pay_out = round(
        (doc.net_pay or 0)
        + (doc.custom_expenses or 0)
        + (doc.custom_variables or 0),
        2
    )

def after_save_salary_slip(doc, method=None):
    # --------------------------------------------------
    # Prevent infinite recursion
    # --------------------------------------------------
    if doc.flags.get("recomputed_once"):
        return

    doc.flags.recomputed_once = True

    # --------------------------------------------------
    # DO YOUR FINAL CALCULATIONS / ADJUSTMENTS HERE
    # (things that depend on gross_pay, deductions, etc.)
    # --------------------------------------------------

    # Example: ensure final CTC consistency
    doc.custom_c_t_c = round(
        float(doc.gross_pay or 0)
        + float(doc.custom_employer_pf or 0)
        + float(doc.custom_employer_esic or 0),
        2
    )

    # --------------------------------------------------
    # Trigger ONE controlled re-save
    # --------------------------------------------------
    doc.save(ignore_permissions=True)
