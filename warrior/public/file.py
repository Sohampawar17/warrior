import frappe

def make_images_public(doc, method=None):

    image_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".svg"
    )

    file_name = (doc.file_name or "").lower()

    if not file_name.endswith(image_extensions):
        return

    if not doc.is_private:
        return

    file_doc = frappe.get_doc("File", doc.name)

    file_doc.is_private = 0
    file_doc.save(ignore_permissions=True)

    frappe.db.commit()