import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, now_datetime, get_datetime, add_to_date
from erpnext.selling.doctype.sales_order.sales_order import make_material_request
from warrior.public.service import update_dispatch_status_for_sales_order,get_available_qty_to_reserve

PO_STATE_TO_TERM = {
    "Pending For PI": "Advance",
    "Pending For Seller Dispatch": "Against PI",
    "Pending For Inward": "Against Dispatch",
}

PI_TERM = "Against GRN"
PO_INWARD_STATE = "Inwarded"  # must match Workflow State name exactly
PI_LAST_TERM = "Credit"

def _get_default_cash_account(company: str) -> str:
    account = frappe.db.get_value("Company", company, "default_cash_account")
    if not account:
        frappe.throw(_("Default Cash Account is not set for Company {0}.").format(company))
    return account


def _get_mode_of_payment(name: str = "cash") -> str:
    if frappe.db.exists("Mode of Payment", name):
        return name

    alt = frappe.db.get_value("Mode of Payment", {"name": ("like", f"{name}%")})
    if alt:
        return alt

    frappe.throw(_("Mode of Payment '{0}' not found.").format(name))


def _normalize_state(state: str) -> str:
    # handles extra spaces / line breaks
    return " ".join((state or "").split()).strip().lower()


def _normalize_text(value: str) -> str:
    return (value or "").strip().lower()



def _get_term_row(doc, term_name: str):
    if not doc.get("payment_schedule"):
        return None

    # collect terms
    terms = list({r.payment_term for r in doc.payment_schedule if r.payment_term})

    # fetch notation
    term_map = frappe.get_all(
        "Payment Term",
        filters={"name": ["in", terms]},
        fields=["name", "custom_notation"]
    )

    notation_map = {
        d.name: (d.custom_notation or "").strip().lower()
        for d in term_map
    }

    target = (term_name or "").strip().lower()

    for r in doc.payment_schedule:
        if notation_map.get(r.payment_term) == target:
            return r

    return None


def _get_po_term_row_by_workflow(po_doc):
    mapped_term = PO_STATE_TO_TERM.get((po_doc.workflow_state or "").strip())
    if not mapped_term:
        return None, None
    return _get_term_row(po_doc, mapped_term), mapped_term


def _resolve_reference_context(reference_doctype, reference_name, payment_term=None):
    """
    Returns workflow-state-aware context for PO/PI linked references.
    """
    if not (reference_doctype and reference_name):
        return frappe._dict()

    if reference_doctype == "Purchase Order":
        po = frappe.get_doc("Purchase Order", reference_name)
        row, mapped_term = _get_po_term_row_by_workflow(po)
        return frappe._dict(
            {
                "purchase_order_id": po.name,
                "po_workflow_state": po.workflow_state,
                "payment_term": (payment_term or (row.payment_term if row else None)),
                "due_date": row.due_date if row else po.get("due_date"),
            }
        )

    if reference_doctype == "Purchase Invoice":
        purchase_order = (
            frappe.db.get_value("Purchase Invoice Item", {"parent": reference_name}, "purchase_order") or ""
        )
        due_date = None
        if payment_term:
            due_date = frappe.db.get_value(
                "Payment Schedule",
                {"parenttype": "Purchase Invoice", "parent": reference_name, "payment_term": payment_term},
                "due_date",
            )
        if not due_date:
            due_date = frappe.db.get_value("Purchase Invoice", reference_name, "due_date")

        po_workflow_state = ""
        if purchase_order:
            po_workflow_state = frappe.db.get_value("Purchase Order", purchase_order, "workflow_state") or ""

        return frappe._dict(
            {
                "purchase_order_id": purchase_order,
                "po_workflow_state": po_workflow_state,
                "payment_term": payment_term,
                "due_date": due_date,
            }
        )

    return frappe._dict()


@frappe.whitelist()
def get_reference_realtime_context(reference_doctype, reference_name, payment_term=None):
    return _resolve_reference_context(reference_doctype, reference_name, payment_term)


def _payment_entry_exists(doc, term_name: str) -> bool:
    # Dedupe: submitted PE which contains a reference row for this doc + this payment term
    res = frappe.db.sql(
        """
        select pe.name
        from `tabPayment Entry` pe
        inner join `tabPayment Entry Reference` per on per.parent = pe.name
        where pe.docstatus = 1
          and per.reference_doctype = %s
          and per.reference_name = %s
          and ifnull(per.payment_term, '') = %s
        limit 1
        """,
        (doc.doctype, doc.name, term_name),
    )
    return bool(res)


def _get_default_payable_account(company: str) -> str:
    acc = frappe.db.get_value("Company", company, "default_payable_account")
    if not acc:
        frappe.throw(_("Default Payable Account is not set for Company {0}.").format(company))
    return acc


def _create_payment_entry_for_term(doc, term_name: str):
    # needs payment schedule rows present
    if not doc.get("payment_schedule"):
        return None

    # prevent duplicates
    if _payment_entry_exists(doc, term_name):
        return None

    row = _get_term_row(doc, term_name)
    # frappe.throw(str(row.as_dict()))
    if not row:
        return None

    term_amount = flt(row.payment_amount)
    if not term_amount:
        return None

    # basic requirements
    if not getattr(doc, "company", None):
        return None

    bank_account = _get_default_cash_account(doc.company)
    mode_of_payment = _get_mode_of_payment("cash")
    payable_account = _get_default_payable_account(doc.company)
    # create Payment Entry
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Pay"
    pe.party_type = "Supplier"
    pe.party = getattr(doc, "supplier", None)
    if not pe.party:
        # if doc doesn't have supplier, don't create
        return None

    pe.company = doc.company
    pe.posting_date = nowdate()
    pe.mode_of_payment = mode_of_payment

    # accounts
    pe.paid_from = bank_account                 # Company cash/bank
    pe.paid_to = payable_account                # Supplier payable (company payable account)

    # amounts
    pe.paid_amount = term_amount
    pe.received_amount = term_amount
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no=frappe.db.get_value("Purchase Invoice Item", {"parent": doc.name}, "purchase_order") if doc.doctype=="Purchase Invoice" else doc.name
    pe.reference_date= nowdate()
    # reference
    pe.append("references", {
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "allocated_amount": term_amount,
        "payment_term": row.payment_term,
        "due_date": row.due_date,
    })
    term_line = f"Payment Term: {term_name}"

    pe.remarks = ((pe.remarks or "").strip() + ("\n" if pe.remarks else "") + term_line)

    if hasattr(pe, "custom_remarks"):
        pe.custom_remarks = ((pe.custom_remarks or "").strip() + ("\n" if pe.custom_remarks else "") + term_line)

    pe.save(ignore_permissions=True)
    return pe.name

def make_po_inwarded(doc,method):

    inward_term = PO_STATE_TO_TERM.get("Pending For Inward")  # "Some 10% Against Dispatch LR"
    po_names=[]
    po_names=list({i.purchase_order for i in doc.items if i.purchase_order})
    for po_name in po_names:
        # Ensure PO exists and is submitted
        po_data = frappe.db.get_value(
            "Purchase Order",
            po_name,
            ["docstatus", "workflow_state"],
            as_dict=True,
        )
        if not po_data or po_data.docstatus != 1:
            continue

        # 1) Update workflow_state using db.set_value
        if (po_data.workflow_state or "").strip() != PO_INWARD_STATE:
            frappe.db.set_value(
                "Purchase Order",
                po_name,
                "workflow_state",
                PO_INWARD_STATE,
                update_modified=True,
            )
def inwared_timestamp_user(doc,method):
    if not doc.custom_inward_by and not doc.custom_inward_datetime:
        doc.custom_inward_by=frappe.session.user
        doc.custom_inward_datetime=now()


def _get_linked_po_names_from_pi(pi_doc):
    po_names = set()
    for it in (pi_doc.items or []):
        if it.get("purchase_order"):
            po_names.add(it.get("purchase_order"))
    return list(po_names)


def _mark_pos_inward(po_names, pi_doc=None):
    """
    Update PO workflow_state to Inwarded using db.set_value
    and update PO payment schedule due_date based on PI date
    """

    pi_date = None
    if pi_doc:
        pi_date = pi_doc.get("transaction_date") or pi_doc.get("posting_date") or nowdate()

    inward_term = PO_STATE_TO_TERM.get("Pending For Inward")  # "Some 10% Against Dispatch LR"

    for po_name in po_names:
        # Ensure PO exists and is submitted
        po_data = frappe.db.get_value(
            "Purchase Order",
            po_name,
            ["docstatus", "workflow_state"],
            as_dict=True,
        )
        if not po_data or po_data.docstatus != 1:
            continue

        # 1) Update workflow_state using db.set_value
        if (po_data.workflow_state or "").strip() != PO_INWARD_STATE:
            frappe.db.set_value(
                "Purchase Order",
                po_name,
                "workflow_state",
                PO_INWARD_STATE,
                update_modified=True,
            )

        # 2) Update PO payment schedule due_date for Dispatch LR term
        if pi_date and inward_term:
            rows = frappe.db.get_all(
                "Payment Schedule",
                filters={
                    "parenttype": "Purchase Order",
                    "parent": po_name,
                    # "payment_term": inward_term,
                    "custom_notation":inward_term
                },
                fields=["name", "due_date"],
            )

            for r in rows:
                if r.due_date != pi_date:
                    frappe.db.set_value(
                        "Payment Schedule",
                        r.name,
                        "due_date",
                        pi_date,
                        update_modified=False,
                    )


def _switch_draft_pe_from_po_to_pi(po_name, pi_name):
    pe_names = frappe.db.get_all(
        "Payment Entry Reference",
        filters={
            "docstatus": 0,
            "reference_doctype": "Purchase Order",
            "reference_name": po_name,
        },
        pluck="parent",
        order_by="creation asc",
    )

    for pe_name in pe_names:
        pe = frappe.get_doc("Payment Entry", pe_name)

        changed = False
        for ref in pe.references:
            if ref.reference_doctype == "Purchase Order" and ref.reference_name == po_name:
                ref.reference_doctype = "Purchase Invoice"
                ref.reference_name = pi_name
                changed = True

        if changed:
            pe.remarks = (pe.remarks or "")
            if f"Auto switched to PI {pi_name}" not in pe.remarks:
                pe.remarks += f"\nAuto switched to PI {pi_name} on PI submit."

            pe.set_missing_values()
            pe.set_amounts()
            pe.save(ignore_permissions=True)

    return len(pe_names)


def set_order_reference_for_payment_entry(doc, method):
    def _pick_primary_reference(references):
        if not references:
            return None

        # Prefer Purchase refs that carry due-date/payment-term metadata.
        for ref in references:
            if ref.reference_doctype in ("Purchase Order", "Purchase Invoice") and (
                ref.get("due_date") or ref.get("payment_term")
            ):
                return ref

        # Then any ref with due-date/payment-term metadata.
        for ref in references:
            if ref.get("due_date") or ref.get("payment_term"):
                return ref

        # Fallback to first row for backward compatibility.
        return references[0]

    for ref in doc.references:
        if ref.reference_doctype == "Sales Order" and not doc.custom_sales_order:
            doc.custom_sales_order = ref.reference_name
            break

    if not hasattr(doc, "custom_purchase_order_id"):
        return

    primary_ref = _pick_primary_reference(doc.references)
    if not primary_ref:
        return

    context = _resolve_reference_context(
        primary_ref.reference_doctype, primary_ref.reference_name, primary_ref.get("payment_term")
    )

    purchase_order = context.get("purchase_order_id", "")
    if context.get("payment_term") and not primary_ref.get("payment_term"):
        primary_ref.payment_term = context.get("payment_term")
    if context.get("due_date"):
        primary_ref.due_date = context.get("due_date")

    doc.custom_purchase_order_id = purchase_order
    doc.custom_payment_term = primary_ref.payment_term or ""
    doc.custom_requested_amount = flt(primary_ref.allocated_amount) or flt(doc.paid_amount)
    doc.custom_payment_term_due_date = primary_ref.due_date
    # Keep UTR in a dedicated field; fallback to reference_no when explicitly not UTR

    due_date = primary_ref.get("due_date")
    if due_date:
        due_dt = get_datetime(due_date)
        now_dt = now_datetime()
        overdue_cutoff = add_to_date(due_dt, days=1, as_datetime=True)

        # Keep as Due for 24 hours from due date, then mark Overdue.
        if now_dt >= overdue_cutoff:
            doc.custom_payment_status = "Overdue"
        elif getdate(now_dt) >= getdate(due_date):
            doc.custom_payment_status = "Due"
        else:
            doc.custom_payment_status = "In Credit Period"
    else:
        # If term exists but no due date metadata, mark as credit-period context.
        if (primary_ref.get("payment_term") or "").strip():
            doc.custom_payment_status = "In Credit Period"
        else:
            doc.custom_payment_status = ""
        
# HOOK FUNCTIONS
# -----------------------------

def create_payment_entry_for_po_workflow(doc, method):
    # only after submit; avoids draft spam and invalid refs
    if doc.docstatus != 1:
        return
    

    prev = doc.get_doc_before_save()
    if prev and prev.workflow_state == doc.workflow_state:
        return

    state_key = _normalize_state(doc.workflow_state)
    term_name = PO_STATE_TO_TERM.get(doc.workflow_state)
    if not term_name:
        return

    _create_payment_entry_for_term(doc, term_name)


def create_payment_entry_for_po_submit(doc, method):
    if doc.docstatus != 1:
        return

    state_key = _normalize_state(doc.workflow_state)
    term_name = PO_STATE_TO_TERM.get(doc.workflow_state)
    if not term_name:
        return
    _create_payment_entry_for_term(doc, term_name)
    

def create_payment_entry_for_pi_submit(doc, method):
    po_names = _get_linked_po_names_from_pi(doc)

    for po in po_names:
        _switch_draft_pe_from_po_to_pi(po, doc.name)
    
    _create_payment_entry_for_term(doc, PI_TERM)
    _create_payment_entry_for_term(doc, PI_LAST_TERM)
    # Update PO workflow_state to Inward (and whatever else your function does)
    _mark_pos_inward(po_names, pi_doc=doc)


def change_reference_no_in_pe(doc, method):
    
    entries=frappe.db.get_all(
        "Payment Entry Reference",
        filters={"reference_doctype": doc.doctype, "reference_name": doc.name},
        fields=["parent"],
    )

import frappe

def on_cancel_purchase_invoice(doc, method=None):
    # 1) Delete draft Payment Entries created against this PI
    pe_names = frappe.db.sql_list(
        """
        SELECT DISTINCT per.parent
        FROM `tabPayment Entry Reference` per
        WHERE per.reference_doctype = 'Purchase Invoice'
          AND per.reference_name = %s
        """,
        (doc.name,),
    )

    for pe_name in pe_names:
        pe = frappe.get_doc("Payment Entry", pe_name)

        if pe.docstatus == 0:
            frappe.delete_doc("Payment Entry", pe.name, force=1)
        elif pe.docstatus == 1:
            # Don't silently cancel accounting docs
            frappe.throw(
                f"Cannot cancel Purchase Invoice {doc.name} because Payment Entry {pe.name} is submitted. "
                f"Cancel the Payment Entry first."
            )

    # 2) Set linked PO workflow_state to "Pending For Inward"
    po_names = _get_linked_po_names_from_pi(doc)
    if not po_names:
        return

    for po_name in po_names:
        po_data = frappe.db.get_value(
            "Purchase Order",
            po_name,
            ["docstatus", "workflow_state"],
            as_dict=True,
        )
        if not po_data or po_data.docstatus != 1:
            continue

        frappe.db.set_value(
            "Purchase Order",
            po_name,
            "workflow_state",
            "Pending For Inward",   # <-- make sure this matches your workflow state's exact value
            update_modified=True,
        )



#scheduler entry for the last payment entry creation if not created during submit
import frappe
from frappe.utils import flt, nowdate,getdate

# OPTIONAL: If you want to restrict to only one term name (e.g. "60% After 60 Days"),
# set this to that exact term name. Else keep None to process ALL terms due today.
ONLY_TERM_NAME = "Some 60% Credit Of Days"  # e.g. "60% After 60 Days"

def create_draft_pe_for_due_pi_terms():
    # today = nowdate()
    today=getdate(nowdate())
    # Fetch PI payment schedule rows due today (submitted PI only)
    # Payment Schedule is shared child doctype used by invoices/orders in ERPNext
    cond_term = ""
    params = {"today": today}

    if ONLY_TERM_NAME:
        cond_term = " AND ps.payment_term = %(term)s"
        params["term"] = ONLY_TERM_NAME

    rows = frappe.db.sql(
        f"""
        SELECT
            ps.name AS schedule_row,
            ps.parent AS purchase_invoice,
            ps.due_date,
            ps.payment_term,
            ps.payment_amount,
            ps.invoice_portion,
            pi.company,
            pi.supplier,
            pi.credit_to,
            pi.grand_total,
            pi.outstanding_amount,
            pi.posting_date
        FROM `tabPayment Schedule` ps
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = ps.parent
        WHERE ps.parenttype = 'Purchase Invoice'
          AND pi.docstatus = 1
          AND ps.due_date = %(today)s
          AND IFNULL(pi.outstanding_amount, 0) > 0
          AND IFNULL(ps.payment_amount, 0) > 0
          {cond_term}
        """,
        params,
        as_dict=True,
    )

    if not rows:
        return

    for r in rows:
        amount = flt(r.payment_amount)

        # Don’t overpay: cap to current invoice outstanding
        amount = min(amount, flt(r.outstanding_amount))
        if amount <= 0:
            continue

        # Avoid duplicates: same PI + same due date + same amount (not cancelled)
        if _pe_already_created(r.purchase_invoice, r.due_date, amount):
            continue

        _make_draft_payment_entry_against_pi(
            pi_name=r.purchase_invoice,
            company=r.company,
            supplier=r.supplier,
            credit_to=r.credit_to,
            posting_date=r.due_date,   # due-date posting
            amount=amount,
            term_name=r.payment_term,
        )


def _pe_already_created(pi_name, posting_date, amount):
    existing = frappe.db.sql(
        """
        SELECT pe.name
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Purchase Invoice'
          AND per.reference_name = %s
          AND pe.docstatus != 2
          AND pe.posting_date = %s
          AND ABS(IFNULL(per.allocated_amount, 0) - %s) < 0.0001
        LIMIT 1
        """,
        (pi_name, posting_date, flt(amount)),
    )
    return bool(existing)


def _make_draft_payment_entry_against_pi(pi_name, company, supplier, credit_to, posting_date, amount, term_name=None):
    if not credit_to:
        # credit_to is critical (supplier payable). If missing, stop with clear msg.
        frappe.log_error(f"PI {pi_name} has no credit_to; cannot create Payment Entry", "Auto PE Error")
        return

    paid_from = _get_paid_from_account(company)
    if not paid_from:
        frappe.log_error(f"Company {company} has no default bank account", "Auto PE Error")
        return

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Pay"
    pe.party_type = "Supplier"
    pe.party = supplier
    pe.company = company
    pe.posting_date = posting_date

    # Accounts
    pe.paid_from = paid_from          # Bank/Cash
    pe.paid_to = credit_to            # Creditors (Payable)

    pe.paid_amount = flt(amount)
    pe.received_amount = flt(amount)
    pe.reference_no= frappe.db.get_value("Purchase Invoice Item", {"parent": pi_name}, "purchase_order") or ""  # just an example; adjust as needed
    pe.reference_date= nowdate()
    pe.append("references", {
        "reference_doctype": "Purchase Invoice",
        "reference_name": pi_name,
        "allocated_amount": flt(amount),
        "payment_term": term_name,
        "due_date": posting_date,
    })

    # Optional: helpful trace
    if term_name:
        pe.remarks = f"Auto-created draft PE for term '{term_name}' due on {posting_date} (PI: {pi_name})"

    pe.insert(ignore_permissions=True)  # keep DRAFT
    frappe.db.commit()


def _get_paid_from_account(company):
    # Prefer Company default bank if set; else adjust as per your setup
    return frappe.db.get_value("Company", company, "default_bank_account")

def on_submit(doc, method):
    if doc.payment_type != "Receive":
        return

    for ref in doc.references:
        if ref.reference_doctype != "Sales Order":
            continue

        try:
            so = frappe.get_doc("Sales Order", ref.reference_name)

            if should_reserve_for_so(so):
                has_available_stock, shortage_found = _get_stock_status_for_so(so)
                if has_available_stock:
                    reserve_stock_for_so(so)
                create_material_request_from_so(so, shortage_found=shortage_found)

            update_dispatch_status_for_sales_order(so.name)
        except Exception:
            # Don't block PE submit; log for review.
            frappe.log_error(
                frappe.get_traceback(),
                f"Payment Entry on_submit error for Sales Order {ref.reference_name}",
            )


def _get_stock_status_for_so(doc):
    has_available_stock = False
    shortage_found = False

    for item in doc.items:
        req = flt(item.get("stock_qty") or item.get("qty") or 0)
        if req <= 0 or not item.warehouse:
            continue

        avail = flt(
            get_available_qty_to_reserve(item_code=item.item_code, warehouse=item.warehouse) or 0
        )

        if avail > 0:
            has_available_stock = True

        if req > avail:
            shortage_found = True

    return has_available_stock, shortage_found


def _get_paid_amount_for_so(so_name: str) -> float:
    paid_amount = frappe.db.sql(
        """
        SELECT SUM(per.allocated_amount)
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Order'
          AND per.reference_name = %s
          AND pe.docstatus = 1
        """,
        so_name,
    )[0][0]
    je_paid_amount=frappe.db.sql(
        """
        SELECT SUM(per.credit)
        FROM `tabJournal Entry Account` per
        JOIN `tabJournal Entry` pe ON pe.name = per.parent
        WHERE per.reference_type = 'Sales Order'
          AND per.reference_name = %s
          AND pe.docstatus = 1 AND is_advance="Yes"
        """,
        so_name,
    )[0][0]
    paid_amount = flt(paid_amount or 0) + flt(je_paid_amount or 0)
    return flt(paid_amount or 0)



def should_reserve_for_so(so) -> bool:
    tolerance = 1  # ₹1 tolerance

    customer_group = (
        so.customer_group
        or frappe.db.get_value("Customer", so.customer, "customer_group")
        or ""
    ).strip().lower()

    paid_amount = flt(_get_paid_amount_for_so(so.name))
    so_total = flt(so.rounded_total or so.grand_total or 0)

    payment_type = (
        getattr(so, "custom_payment_type", None) or ""
    ).strip().lower()

    pending_amount = so_total - paid_amount
    is_fully_paid = pending_amount <= tolerance and so_total > 0

    if customer_group == "farmer":
        if payment_type == "full payment":
            return is_fully_paid

        # Advance payment / COD Farmer
        return paid_amount > 0

    if customer_group == "dealer":
        return is_fully_paid

    return False


def create_material_request_from_so(doc, shortage_found=None):
    """
    Automatically create Material Request only for true remaining shortage
    """

    debug_log = []

    if shortage_found is None:
        shortage_found = False

        for item in doc.items:
            so_stock_qty = flt(item.get("stock_qty") or item.get("qty") or 0)
            if so_stock_qty <= 0 or not item.warehouse:
                continue

            free_available_qty = flt(
                get_available_qty_to_reserve(
                    item_code=item.item_code,
                    warehouse=item.warehouse
                ) or 0
            )
            reserved_for_same_so_item = flt(
                frappe.db.sql(
                    """
                    SELECT IFNULL(SUM(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)), 0)
                    FROM `tabStock Reservation Entry` sre
                    WHERE
                        sre.voucher_type = 'Sales Order'
                        AND sre.voucher_no = %s
                        AND sre.voucher_detail_no = %s
                        AND sre.docstatus = 1
                    """,
                    (doc.name, item.name),
                )[0][0]
                or 0
            )
            effective_available_qty = free_available_qty + reserved_for_same_so_item

            if so_stock_qty > effective_available_qty:
                shortage_found = True
                break

    if not shortage_found:
        frappe.log_error(
            title="MR Debug - No Shortage",
            message=f"No shortage found for SO: {doc.name}"
        )
        return

    # Create MR
    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Purchase"
    mr.schedule_date = doc.delivery_date
    mr.sales_order = doc.name

    for item in doc.items:
        if not item.warehouse:
            continue

        conversion_factor = flt(item.get("conversion_factor") or 1)
        so_qty = flt(item.get("qty") or 0)
        so_stock_qty = flt(item.get("stock_qty") or (so_qty * conversion_factor))

        if so_stock_qty <= 0:
            continue

        free_available_qty = flt(
            get_available_qty_to_reserve(
                item_code=item.item_code,
                warehouse=item.warehouse
            ) or 0
        )
        reserved_for_same_so_item = flt(
            frappe.db.sql(
                """
                SELECT IFNULL(SUM(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)), 0)
                FROM `tabStock Reservation Entry` sre
                WHERE
                    sre.voucher_type = 'Sales Order'
                    AND sre.voucher_no = %s
                    AND sre.voucher_detail_no = %s
                    AND sre.docstatus = 1
                """,
                (doc.name, item.name),
            )[0][0]
            or 0
        )
        effective_available_qty = free_available_qty + reserved_for_same_so_item

        already_requested = frappe.db.sql("""
            SELECT IFNULL(SUM(
                IFNULL(mri.stock_qty, IFNULL(mri.qty, 0) * IFNULL(mri.conversion_factor, 1))
            ), 0)
            FROM `tabMaterial Request Item` mri
            INNER JOIN `tabMaterial Request` mr
                ON mr.name = mri.parent
            WHERE
                mri.sales_order = %s
                AND mri.sales_order_item = %s
                AND mr.material_request_type = 'Purchase'
                AND mr.docstatus != 2
                AND IFNULL(mr.status, '') NOT IN ('Stopped', 'Cancelled', 'Ordered')
        """, (doc.name, item.name))[0][0] or 0

        remaining_shortage_stock = so_stock_qty - effective_available_qty - flt(already_requested)
        if remaining_shortage_stock > 0:
            remaining_shortage_qty = remaining_shortage_stock / conversion_factor
            mr.append("items", {
                "item_code": item.item_code,
                "qty": remaining_shortage_qty,
                "uom": item.uom,
                "stock_uom": item.stock_uom,
                "conversion_factor": conversion_factor,
                "warehouse": item.warehouse,
                "schedule_date": doc.delivery_date,
                "sales_order": doc.name,
                "sales_order_item": item.name
            })

    if not mr.items:
        frappe.log_error(
            title="MR Debug - No Items Added",
            message=f"SO: {doc.name}"
        )
        return


    mr.insert(ignore_permissions=True)
    mr.submit()




def on_cancel(doc, method):
    if doc.payment_type != "Receive":
        return

    for ref in doc.references:
        if ref.reference_doctype != "Sales Order":
            continue

        so = frappe.get_doc("Sales Order", ref.reference_name)

        if not should_reserve_for_so(so):
            cancel_reservation_for_so(so)

        update_dispatch_status_for_sales_order(so.name)




def reserve_stock_for_so(so):
    eligible_rows = []
    eligible_items_details = []
    reserved_rows = []

    for d in so.items:
        if not d.get("warehouse"):
            continue

        req = flt(d.get("stock_qty") or d.get("qty") or 0)
        if req <= 0:
            continue

        reserved_qty = _get_reserved_qty_for_so_item(so.name, d.name)
        remaining_qty = flt(req - reserved_qty)
        if remaining_qty <= 0:
            reserved_rows.append(d)
            continue

        avail = flt(
            get_available_qty_to_reserve(item_code=d.item_code, warehouse=d.warehouse) or 0
        )

        frappe.log_error(
            f"SO {so.name} Item {d.item_code}: Remaining Req={remaining_qty}, Avail={avail}",
            "Stock Reservation",
        )

        if avail >= remaining_qty:
            eligible_rows.append(d)
            eligible_items_details.append(
                {
                    "sales_order_item": d.name,
                    "warehouse": d.warehouse,
                    "qty_to_reserve": remaining_qty / flt(d.get("conversion_factor") or 1),
                    "conversion_factor": flt(d.get("conversion_factor") or 1),
                }
            )

    rows_to_mark_reserved = {d.name for d in eligible_rows + reserved_rows}

    if not rows_to_mark_reserved:
        so.flags.ignore_permissions = True
        so.flags.ignore_validate_update_after_submit = True

        so.set("reserve_stock", 0)
        for d in so.items:
            d.set("reserve_stock", 0)

        so.save(ignore_permissions=True)
        return

    so.flags.ignore_permissions = True
    so.flags.ignore_validate_update_after_submit = True

    so.set("reserve_stock", 1)
    for d in so.items:
        d.set("reserve_stock", 1 if d.name in rows_to_mark_reserved else 0)

    so.save(ignore_permissions=True)

    if not eligible_items_details:
        return

    try:
        so.run_method(
            "create_stock_reservation_entries",
            items_details=eligible_items_details,
            notify=False,
        )
        frappe.db.commit()
    except Exception:
        # Don't block caller; log for review.
        frappe.log_error(
            frappe.get_traceback(),
            f"Stock reservation error for Sales Order {so.name}",
        )


def _get_reserved_qty_for_so_item(sales_order, sales_order_item):
    return flt(
        frappe.db.sql(
            """
            SELECT IFNULL(SUM(IFNULL(sre.reserved_qty, 0)), 0)
            FROM `tabStock Reservation Entry` sre
            WHERE
                sre.voucher_type = 'Sales Order'
                AND sre.voucher_no = %s
                AND sre.voucher_detail_no = %s
                AND sre.docstatus = 1
            """,
            (sales_order, sales_order_item),
        )[0][0] or 0
    )


def cancel_reservation_for_so(so):
    so.flags.ignore_permissions = True
    so.flags.ignore_validate_update_after_submit = True

    so.cancel_stock_reservation_entries(notify=False)
    so.set("reserve_stock", 0)
    for d in so.items:
        d.set("reserve_stock", 0)

    so.save()
    frappe.db.commit()



from erpnext.stock.doctype.stock_reservation_entry.stock_reservation_entry import get_available_qty_to_reserve

def reserve_stock_quantity(item_code, warehouse):
    available = flt(
        get_available_qty_to_reserve(item_code=item_code, warehouse=warehouse) or 0
    )
    frappe.log_error(
        f"Available qty to reserve for {item_code} in {warehouse}: {available}",
        "Reserve Stock for Waiting Sales Orders",
    )
    if available <= 0:
        return
