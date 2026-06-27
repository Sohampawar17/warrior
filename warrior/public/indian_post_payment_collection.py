import frappe
from frappe.utils import flt, nowdate
from frappe.utils.csvutils import read_csv_content
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file, read_xls_file_from_attached_file
from erpnext.accounts.doctype.payment_entry.payment_entry import get_bank_cash_account
from warrior.public.sales_invoice_hooks import mark_sales_invoice_delivered

RESULT_CACHE_PREFIX = "indian_post_payment_collection_result"
RESULT_TTL_SECONDS = 60 * 60


def _result_cache_key(job_id):
    return f"{RESULT_CACHE_PREFIX}:{job_id}"


@frappe.whitelist()
def start_payment_entries_from_excel(file_url, company=None, posting_date=None, mode_of_payment=None):
    if not file_url:
        frappe.throw("file_url is required")

    job_id = frappe.generate_hash(length=12)
    result_key = _result_cache_key(job_id)

    frappe.cache.set_value(
        result_key,
        {"status": "queued", "created": 0, "failed": 0, "log": ["Queued for processing."]},
        expires_in_sec=RESULT_TTL_SECONDS,
    )

    frappe.enqueue(
        "warrior.public.indian_post_payment_collection.run_payment_entries_job",
        queue="long",
        timeout=60 * 60,
        job_id=f"indian_post_payment_collection:{job_id}",
        file_url=file_url,
        company=company,
        posting_date=posting_date,
        mode_of_payment=mode_of_payment,
        result_key=result_key,
    )

    return {"job_id": job_id, "status": "queued"}


@frappe.whitelist()
def get_payment_entries_job_status(job_id):
    if not job_id:
        frappe.throw("job_id is required")

    return frappe.cache.get_value(_result_cache_key(job_id), expires=True) or {
        "status": "unknown",
        "created": 0,
        "failed": 1,
        "log": ["Job status was not found. It may have expired."],
    }


def run_payment_entries_job(file_url, result_key, company=None, posting_date=None, mode_of_payment=None):
    frappe.cache.set_value(
        result_key,
        {"status": "processing", "created": 0, "failed": 0, "log": ["Processing payments..."]},
        expires_in_sec=RESULT_TTL_SECONDS,
    )

    try:
        result = create_payment_entries_from_excel(
            file_url=file_url,
            company=company,
            posting_date=posting_date,
            mode_of_payment=mode_of_payment,
        )
        result["status"] = "failed" if result.get("rolled_back") else "completed"
    except Exception as e:
        frappe.db.rollback()
        result = {
            "status": "failed",
            "created": 0,
            "failed": 1,
            "rolled_back": 1,
            "log": [
                f"Failed | Error: {str(e)}",
                "Rolled back all changes. No Payment Entries or Sales Invoice delivery updates were saved.",
            ],
        }
        frappe.log_error(frappe.get_traceback(), "Indian Post Payment Collection Failed")

    frappe.cache.set_value(result_key, result, expires_in_sec=RESULT_TTL_SECONDS)
    return result


@frappe.whitelist()
def create_payment_entries_from_excel(file_url, company=None, posting_date=None, mode_of_payment=None):
    """
    Excel columns used:
      - Article Number => tracking_id
      - Net Amount => amount
    """
    if not file_url:
        frappe.throw("file_url is required")

    posting_date = posting_date or nowdate()

    # Load file content
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    content = file_doc.get_content()
    file_name = (file_doc.file_name or file_doc.file_url or "").lower()

    # Read rows using Frappe utilities
    if file_name.endswith(".xlsx"):
        rows = read_xlsx_file_from_attached_file(file_url=file_url)
    elif file_name.endswith(".xls"):
        if isinstance(content, str):
            content = content.encode("utf-8", errors="ignore")
        rows = read_xls_file_from_attached_file(content)
    elif file_name.endswith(".csv"):
        rows = read_csv_content(content)
    else:
        frappe.throw("Unsupported file type. Please upload .xlsx, .xls, or .csv.")

    if not rows:
        frappe.throw("No data found in the file")

    header = [str(col).strip() if col is not None else "" for col in rows[0]]
    header_map = {col: idx for idx, col in enumerate(header)}

    # Validate columns
    required_cols = {"Article Number", "Net Amount"}
    missing = required_cols - set(header_map.keys())
    if missing:
        frappe.throw(f"Missing columns in file: {', '.join(missing)}")

    created, failed = 0, 0
    log = []
    seen_tracking_ids = set()

    def _get_cell(row, idx):
        return row[idx] if idx < len(row) else None

    try:
        for i, row in enumerate(rows[1:], start=2):  # header is row 1
            tracking_id = str(_get_cell(row, header_map["Article Number"]) or "").strip()
            amount = flt(_get_cell(row, header_map["Net Amount"]) or 0)

            if not tracking_id:
                raise ValueError("Article Number is empty")
            if amount <= 0:
                raise ValueError("Net Amount must be > 0")
            if tracking_id in seen_tracking_ids:
                raise ValueError(f"Duplicate Tracking ID in uploaded file: {tracking_id}")
            seen_tracking_ids.add(tracking_id)

            # 🔁 Map tracking_id -> reference doc (example: Payment Link.transactionid)
            ref = frappe.db.get_value(
                "Indian Post Tracking ID",
                {"tracking_id": tracking_id},
                "against_document"
            )
            if not ref:
                raise ValueError(f"No reference found for tracking_id={tracking_id}")

            sales_invoice = frappe.get_doc("Sales Invoice", ref)
            if sales_invoice.docstatus != 1:
                raise ValueError(f"Sales Invoice {ref} must be submitted")

            # -------------------------
            # Prevent duplicate tracking id
            # -------------------------
            existing_pe = frappe.db.get_value(
                "Payment Entry",
                {
                    "reference_no": tracking_id,
                    "docstatus": ["!=", 2]
                },
                ["name", "paid_amount"],
                as_dict=True
            )

            if existing_pe:
                raise ValueError(
                    f"Duplicate Tracking ID Found | "
                    f"Tracking ID: {tracking_id} | "
                    f"Existing Payment Entry: {existing_pe.name} | "
                    f"Amount: {existing_pe.paid_amount}"
                )

            pe = frappe.new_doc("Payment Entry")
            pe.payment_type ="Receive"   # change if required
            pe.company = company or frappe.defaults.get_user_default("Company")
            pe.posting_date = posting_date
            if mode_of_payment:
                pe.mode_of_payment = mode_of_payment

            party_type, party = _get_party_from_reference("Sales Invoice", ref)
            pe.party_type = party_type
            pe.party = party

            pe.setup_party_account_field()
            pe.set_missing_values()

            bank = get_bank_cash_account(pe, None)
            if not bank or not bank.account:
                frappe.throw("Default Bank/Cash account not found for the company")

            if pe.payment_type == "Receive":
                pe.paid_to = bank.account
                pe.paid_to_account_currency = bank.account_currency
                pe.paid_to_account_type = bank.account_type

            pe.append("references", {
                "reference_doctype": "Sales Invoice",
                "reference_name": ref,
                "allocated_amount": amount
            })
            pe.reference_no = tracking_id
            pe.reference_date = posting_date
            pe.paid_amount = amount
            pe.received_amount = amount

            pe.set_missing_values()
            pe.set_missing_ref_details()

            pe.insert(ignore_permissions=True)
            pe.submit()  # optional
            mark_sales_invoice_delivered(ref)

            created += 1
            log.append(
                    f"Row {i} Success | "
                    f"Tracking ID: {tracking_id} | "
                    f"Sales Invoice: {ref} | "
                    f"Payment Entry: {pe.name} | "
                    f"Amount: {amount} | "
                    f"Invoice Status: Delivered"
                )

    except Exception as e:
        frappe.db.rollback()
        failed += 1
        log.append(
                f"Row {i if 'i' in locals() else 'N/A'} Failed | "
                f"Tracking ID: {tracking_id if 'tracking_id' in locals() else 'N/A'} | "
                f"Error: {str(e)}"
            )
        log.append("Rolled back all changes. No Payment Entries or Sales Invoice delivery updates were saved.")
        return {"created": 0, "failed": failed, "rolled_back": 1, "log": log}

    return {"created": created, "failed": failed, "log": log}


def _get_party_from_reference(reference_doctype, reference_name):
    if reference_doctype in ("Sales Order", "Sales Invoice"):
        customer = frappe.db.get_value(reference_doctype, reference_name, "customer")
        if not customer:
            frappe.throw(f"Customer not found in {reference_doctype} {reference_name}")
        return "Customer", customer

    if reference_doctype in ("Purchase Invoice", "Purchase Order"):
        supplier = frappe.db.get_value(reference_doctype, reference_name, "supplier")
        if not supplier:
            frappe.throw(f"Supplier not found in {reference_doctype} {reference_name}")
        return "Supplier", supplier

    frappe.throw(f"Unsupported reference_doctype: {reference_doctype}")
