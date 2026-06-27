import frappe

def set_bundle_entry_barcodes(doc, method):
    """
    Auto-generate barcode for each Serial & Batch Bundle child row
    BEFORE SAVE
    """

    if not doc.entries:
        return

    for row in doc.entries:

        # Do not regenerate
        if row.custom_barcode:
            continue

        # Barcode field expects simple string
        if not row.serial_no:
            continue

        # BEST PRACTICE: Serial No as barcode
        row.custom_barcode = row.serial_no
