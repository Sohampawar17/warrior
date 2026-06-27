import json

import frappe
from frappe.utils import flt


def fix_ewaybill_place_names_before_print(doc, method=None, settings=None, *args, **kwargs):
    if not doc.get("data"):
        return

    try:
        data = json.loads(doc.data)
    except Exception:
        return

    raw_from_place = data.get("fromPlace")
    data["fromPlace"] = warrior_get_e_waybill_place(doc, data, "dispatch")
    data["toPlace"] = warrior_get_e_waybill_place(doc, data, "delivery")
    _fix_vehicle_from_places(data, data["fromPlace"], raw_from_place)

    doc.data = json.dumps(data)


def warrior_get_e_waybill_place(ewaybill_log, data, place_type):
    fallback = (data or {}).get("fromPlace" if place_type == "dispatch" else "toPlace")
    address = _get_e_waybill_address(ewaybill_log, place_type)

    if not address:
        return _resolve_location_value("Marketplace", fallback)

    parts = [
        _resolve_location_value("Marketplace", address.get("city")),
        _resolve_link_field_value("Address", "custom_tahshil", address.get("custom_tahshil")),
        _resolve_link_field_value("Address", "custom_district", address.get("custom_district")),
    ]

    resolved_parts = []
    for part in parts:
        part = str(part or "").strip()
        if part and part not in resolved_parts:
            resolved_parts.append(part)

    return ", ".join(resolved_parts) or _resolve_location_value("Marketplace", fallback)


def get_stock_transfer_sales_rate(item_code):
    if not item_code:
        return 0

    return flt(
        frappe.db.sql(
            """
            SELECT COALESCE(
                (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    INNER JOIN `tabPrice List` pl ON pl.name = ip.price_list
                    INNER JOIN `tabItem` item ON item.name = ip.item_code
                    WHERE ip.item_code = %(item_code)s
                      AND IFNULL(ip.selling, 0) = 1
                      AND IFNULL(pl.selling, 0) = 1
                      AND IFNULL(pl.enabled, 0) = 1
                      AND pl.custom_customer_group = 'Dealer'
                      AND pl.custom_brand = item.brand
                    ORDER BY ip.valid_from DESC, ip.modified DESC
                    LIMIT 1
                ),
                (
                    SELECT ip.price_list_rate
                    FROM `tabItem Price` ip
                    WHERE ip.item_code = %(item_code)s
                      AND IFNULL(ip.selling, 0) = 1
                      AND ip.price_list = '1-A G Sales-Dealer'
                    ORDER BY ip.valid_from DESC, ip.modified DESC
                    LIMIT 1
                ),
                0
            ) AS sales_rate
            """,
            {"item_code": item_code},
            as_dict=True,
        )[0].sales_rate
    )


def _get_e_waybill_address(ewaybill_log, place_type):
    if not ewaybill_log or not ewaybill_log.reference_doctype or not ewaybill_log.reference_name:
        return None

    try:
        from india_compliance.gst_india.utils.e_waybill import (
            get_billing_shipping_address_map,
        )

        ref_doc = frappe.get_doc(ewaybill_log.reference_doctype, ewaybill_log.reference_name)
        address_map = get_billing_shipping_address_map(ref_doc)
        address_name = (
            (address_map.ship_from or address_map.bill_from)
            if place_type == "dispatch"
            else (address_map.ship_to or address_map.bill_to)
        )

        if address_name:
            return frappe.get_cached_doc("Address", address_name)
    except Exception:
        return None

    return None


def _resolve_link_field_value(parent_doctype, fieldname, value):
    value = str(value or "").strip()
    if not value:
        return ""

    try:
        field = frappe.get_meta(parent_doctype).get_field(fieldname)
    except Exception:
        field = None

    return _resolve_location_value(field.options if field else None, value)


def _fix_vehicle_from_places(data, dispatch_place, raw_from_place):
    resolved_raw_from_place = _resolve_location_value("Marketplace", raw_from_place)
    vehicle_details = data.get("VehiclListDetails") or []
    for detail in vehicle_details:
        if not isinstance(detail, dict):
            continue

        place = _resolve_location_value("Marketplace", detail.get("fromPlace"))
        if place == resolved_raw_from_place:
            place = dispatch_place

        detail["fromPlace"] = _append_state_pincode(
            place,
            detail.get("fromState") or data.get("actFromStateCode"),
            detail.get("fromPincode") or data.get("fromPincode"),
        )


def _append_state_pincode(place, state_code, pincode):
    place = str(place or "").strip()
    state = _get_state_name(state_code)
    pincode = str(pincode or "").strip()

    state_pincode = " - ".join(part for part in (state, pincode) if part)
    return ", ".join(part for part in (place, state_pincode) if part)


def _get_state_name(state_code):
    if not state_code:
        return ""

    try:
        from india_compliance.gst_india.utils import get_state

        return get_state(state_code) or ""
    except Exception:
        return ""


def _resolve_location_value(doctype, value):
    value = str(value or "").strip()
    if not value:
        return ""

    if not doctype or not frappe.db.exists("DocType", doctype):
        return value

    if not frappe.db.exists(doctype, value):
        return value

    title_field = _get_title_field(doctype)
    if title_field:
        return frappe.db.get_value(doctype, value, title_field) or value

    return value


def _get_title_field(doctype):
    try:
        meta = frappe.get_meta(doctype)
    except Exception:
        return None

    if meta.title_field:
        return meta.title_field

    for fieldname in ("marketplace_name", "tahshil", "tehsil", "district_name", "title"):
        if meta.has_field(fieldname):
            return fieldname

    return None
