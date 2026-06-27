import frappe
from frappe.utils import flt
from erpnext.stock.doctype.batch.batch import make_batch


def _get_serial_range(range_string, separator="::"):
    if not range_string:
        return []

    parts = range_string.strip().split(separator)
    if len(parts) != 2:
        return []

    start_str, end_str = parts
    if not start_str or not end_str:
        return []

    try:
        end_int = int(end_str)
    except ValueError:
        return []

    length_difference = len(start_str) - len(end_str)
    if length_difference < 0:
        return []

    try:
        start_int = int(start_str[length_difference:])
    except ValueError:
        return []

    if end_int < start_int:
        return []

    prefix = start_str[:length_difference]
    serial_numbers = []
    for val in range(start_int, end_int + 1):
        serial_numbers.append(prefix + str(val).zfill(len(end_str)))

    return serial_numbers


def apply_serial_series_before_submit(doc, method):
    if not getattr(doc, "update_stock", 0):
        return

    for row in doc.items:
        if not row.get("custom_serial_series"):
            continue

        if row.get("serial_no"):
            continue

        item = frappe.get_cached_doc("Item", row.item_code)
        if not item.has_serial_no:
            continue

        serial_nos = _get_serial_range(row.custom_serial_series)
        if not serial_nos:
            frappe.throw(
                f"Invalid Serial No Range in row {row.idx}: {row.custom_serial_series}"
            )

        row.serial_no = "\n".join(serial_nos)
        row.use_serial_batch_fields = 1

        if item.has_batch_no and not row.get("batch_no") and not getattr(doc, "is_return", 0):
            row.batch_no = make_batch(
                frappe._dict(
                    {
                        "item": row.item_code,
                        "reference_doctype": doc.doctype,
                        "reference_name": doc.name,
                    }
                )
            )

def create_format(doc, method):
    """
    Create Serial Nos → Batch → Serial & Batch Bundle
    on Purchase Invoice Submit
    """
    for row in doc.items:

        if not row.item_code or flt(row.qty) <= 0:
            continue

        item = frappe.get_cached_doc("Item", row.item_code)

        if not (item.has_serial_no and item.has_batch_no):
            continue

        if row.serial_and_batch_bundle:
            continue

        # -----------------------------
        # QR VALIDATION
        # -----------------------------
        # if row.custom_qr_start is None or row.custom_qr_end is None:
        #     frappe.throw(
        #         f"QR Start and End are mandatory for item {row.item_code}"
        #     )

        # qr_start = int(row.custom_qr_start)
        # qr_end = int(row.custom_qr_end)
        # row.custom_serial_series = f"{row.item_code}{qr_start}::{qr_end}"
        # frappe.db.set_value(
        #     row.doctype,
        #     row.name,
        #     "custom_serial_series",
        #     f"{row.item_code}{qr_start}::{qr_end}"
        # )



def create_serial_batch_bundles(doc, method):
    """
    Create Serial Nos → Batch → Serial & Batch Bundle
    on Purchase Invoice Submit
    """

    frappe.log_error(
        title="PI Serial Bundle START",
        message=f"Triggered for Purchase Invoice: {doc.name}"
    )

    # for row in doc.items:

    #     if not row.item_code or flt(row.qty) <= 0:
    #         continue

    #     item = frappe.get_cached_doc("Item", row.item_code)

    #     if not (item.has_serial_no and item.has_batch_no):
    #         continue

    #     if row.serial_and_batch_bundle:
    #         continue

    #     # -----------------------------
    #     # QR VALIDATION
    #     # -----------------------------
    #     if row.custom_qr_start is None or row.custom_qr_end is None:
    #         frappe.throw(
    #             f"QR Start and End are mandatory for item {row.item_code}"
    #         )

    #     qr_start = int(row.custom_qr_start)
    #     qr_end = int(row.custom_qr_end)
    #     expected_qty = qr_end - qr_start + 1
    #     frappe.db.set_value(
    #         row.doctype,
    #         row.name,
    #         "custom_serial_series",
    #         f"{row.item_code}{qr_start}::{qr_end}"
    #     )

#         if expected_qty != int(flt(row.qty)):
#             frappe.throw(
#                 f"Qty mismatch for item {row.item_code}: "
#                 f"QR range gives {expected_qty}, Item Qty {row.qty}"
#             )

#         # -----------------------------
#         # CREATE SERIAL NOS
#         # -----------------------------
#         serial_nos = [
#             f"{row.item_code}-{i}"
#             for i in range(qr_start, qr_end + 1)
#         ]

#         create_serial_nos(
#             serial_nos=serial_nos,
#             item_code=row.item_code
#         )

#         # -----------------------------
#         # CREATE BATCH
#         # -----------------------------
#         batch = frappe.get_doc({
#             "doctype": "Batch",
#             "item": row.item_code,
#             "batch_qty": expected_qty,
#             "manufacturing_date": doc.posting_date
#         })
#         batch.insert(ignore_permissions=True)

#         batch_no = batch.name  # THIS IS CRITICAL

#         # -----------------------------
#         # CREATE SERIAL & BATCH BUNDLE
#         # -----------------------------
#         bundle = frappe.new_doc("Serial and Batch Bundle")
#         bundle.company = doc.company
#         bundle.item_code = row.item_code
#         bundle.item_name = row.item_name
#         bundle.item_group = item.item_group
#         bundle.warehouse = row.warehouse
#         bundle.type_of_transaction = "Inward"
#         bundle.voucher_type = doc.doctype
#         bundle.voucher_no = doc.name
#         bundle.posting_date = doc.posting_date
#         bundle.posting_time = doc.posting_time
#         bundle.total_qty = expected_qty

#         for sn in serial_nos:
#             bundle.append("entries", {
#                 "serial_no": sn,
#                 "batch_no": batch_no,   # ✅ REQUIRED
#                 "qty": 1,
#                 "warehouse": row.warehouse,
#                 "incoming_rate": flt(row.rate),
#                 "is_outward": 0
#             })

#         bundle.insert(ignore_permissions=True)
#         bundle.submit()

#         frappe.db.set_value(
#             row.doctype,
#             row.name,
#             "serial_and_batch_bundle",
#             bundle.name
#         )

#     frappe.log_error(
#         title="PI Serial Bundle END",
#         message=f"Completed for PI: {doc.name}"
#     )
import frappe
from frappe.utils.pdf import get_pdf
from frappe.utils import get_files_path
import os

@frappe.whitelist()
def get_barcodes_label_pdf(purchase_invoice):
    """
    Generate PDF barcode labels (business card size) for a Purchase Invoice.
    Each barcode on a separate page (like a card).
    Using HTML barcode font.
    """
    # Fetch Purchase Invoice
    doc = frappe.get_doc("Purchase Invoice", purchase_invoice)

    # Start HTML
    html = """
    <html>
    <head>
    <style>
    @page {
        size: 85mm 55mm; /* Business card size */
        margin: 0;
    }

    body {
        margin: 0;
        padding: 0;
    }

    .label {
        width: 85mm;
        height: 55mm;
        font-family: Arial, sans-serif;
        box-sizing: border-box;
        padding: 2mm;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        border: 1px dashed #ccc; /* optional preview border */
        page-break-after: always; /* each label on new page */
    }

    .item-info {
        font-size: 9pt;
    }

    .barcode {
        font-family: 'Libre Barcode 128 Text', monospace;
        font-size: 24pt;
        text-align: center;
    }

    .meta {
        font-size: 8pt;
        text-align: center;
    }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Libre+Barcode+128+Text&display=swap" rel="stylesheet">
    </head>
    <body>
    """

    # Create a label for each serial/batch entry
    for item in doc.items:
        if item.serial_and_batch_bundle:
            bundle = frappe.get_doc("Serial and Batch Bundle", item.serial_and_batch_bundle)
            for e in bundle.entries:
                barcode_value = e.get('custom_barcode') or ''
                serial_no = e.get('serial_no') or e.get('custom_serial_no') or ''
                mfd_date = e.get('manufacturing_date') or item.get('manufacturing_date') or doc.posting_date
                html += f"""
                <div class="label">
                    <div class="item-info">
                        {item.item_code}<br>
                        {item.item_name}
                    </div>
                    <div class="barcode">{barcode_value}</div>
                    <div class="meta">Serial No: {serial_no}</div>
                    <div class="meta">MFD: {mfd_date}</div>
                </div>
                """

    html += "</body></html>"

    # Generate PDF
    pdf_content = get_pdf(html)

    # Save PDF to /files/
    file_name = f"Purchase_Invoice_{purchase_invoice}_Barcode_Labels.pdf"
    file_path = os.path.join(get_files_path(), file_name)
    with open(file_path, "wb") as f:
        f.write(pdf_content)

    file_url = f"/files/{file_name}"
    return {"file_url": file_url, "file_path": file_path}


