import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, flt

from warrior.public.sales_order import (
	DISPATCH_STATUS_PARTIALLY_AVAILABLE,
	update_dispatch_status_for_sales_order,
)


SOURCE_STATUSES = ("PARTIAL DISPATCH", "READY TO DISPATCH","PARTIALLY AVAILABLE")
TARGET_STATUSES = (
	"PARTIAL DISPATCH",
	"MATERIAL SHORTAGE",
	"PARTIALLY AVAILABLE",
	"PARTIALLY INVOICED",
	"PARTIALLY DISPATCHED",
	"PARTIALLY DELIVERED",
)
TARGET_ORDER_STATUSES = (
	"PARTIALLY INVOICED",
	"PARTIALLY DISPATCHED",
	"PARTIALLY DELIVERED",
)


class StockReservationMapping(Document):
	def validate(self):
		self.total_qty_to_map = sum(flt(row.qty_to_map) for row in self.items or [])
		self.status = self.status or "Draft"

	def before_submit(self):
		_process_reservation_mapping(self.items, self.target_sales_order, validate_only=True)

	def on_submit(self):
		result = _process_reservation_mapping(self.items, self.target_sales_order)
		self.db_set("total_qty_to_map", result.total_qty, update_modified=False)
		self.db_set("status", "Mapped", update_modified=False)

		for row in self.items or []:
			if flt(row.qty_to_map) > 0:
				frappe.db.set_value(
					row.doctype,
					row.name,
					{"mapping_status": "Mapped", "error_message": ""},
					update_modified=False,
				)

	def on_cancel(self):
		frappe.throw(_("Submitted reservation mappings cannot be cancelled because stock reservation has already moved."))


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		return json.loads(value)
	return value


def _reserved_qty(sales_order_item):
	return flt(
		frappe.db.sql(
			"""
			SELECT IFNULL(SUM(IFNULL(reserved_qty, 0) - IFNULL(delivered_qty, 0)), 0)
			FROM `tabStock Reservation Entry`
			WHERE voucher_type = 'Sales Order'
			  AND voucher_detail_no = %s
			  AND docstatus = 1
			""",
			sales_order_item,
		)[0][0]
	)


def _available_qty(sre):
	return flt(sre.reserved_qty) - flt(sre.delivered_qty)


def _ordered_qty(item):
	return flt(item.stock_qty or item.qty or 0)


def _delivered_stock_qty(item):
	return flt(item.delivered_qty) * flt(item.get("conversion_factor", 1) or 1)


def _invoiced_stock_qty(sales_order_item):
	return flt(
		frappe.db.sql(
			"""
			SELECT IFNULL(
				SUM(
					ABS(
						IFNULL(
							NULLIF(sii.stock_qty, 0),
							IFNULL(sii.qty, 0) * IFNULL(sii.conversion_factor, 1)
						)
					)
				),
				0
			)
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1
			  AND IFNULL(si.is_return, 0) = 0
			  AND sii.so_detail = %s
			""",
			sales_order_item,
		)[0][0]
	)


def _pending_qty(item):

	ordered_qty = _ordered_qty(item)
	delivered_qty = _delivered_stock_qty(item)
	invoiced_qty = _invoiced_stock_qty(item.name)
	reserved_qty = _reserved_qty(item.name)

	pending_qty = max(
		ordered_qty
		- max(delivered_qty, invoiced_qty)
		- reserved_qty,
		0,
	)
	return pending_qty

def _html(value):
	return escape_html(value or "")


def _format_qty(value):
	return frappe.format_value(flt(value), {"fieldtype": "Float"})


def r2(value):
	return round(flt(value or 0), 2)


def _badge_colors(status):
	status = (status or "").lower()
	if "cancel" in status or "closed" in status:
		return "#FFE5E5", "#B00020"
	if "paid" in status or "completed" in status or "delivered" in status:
		return "#E7F7EE", "#0F7B43"
	if "overdue" in status or "unpaid" in status:
		return "#FFF4E5", "#9A5A00"
	return "#EEF2FF", "#243B8A"


def _field_exists(doctype, fieldname):
	return frappe.get_meta(doctype).has_field(fieldname)


@frappe.whitelist()
def get_target_sales_order_details(target_sales_order):
	return get_order_details_html(target_sales_order)



from frappe.utils import getdate

def get_last_payment_date_for_sales_order(sales_order_name):
    pe_date = frappe.db.sql(
        """
        SELECT MAX(pe.posting_date)
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
        WHERE per.reference_doctype = 'Sales Order'
            AND per.reference_name = %s
            AND pe.docstatus = 1
        """,
        sales_order_name,
    )[0][0]

    je_date = frappe.db.sql(
        """
        SELECT MAX(je.posting_date)
        FROM `tabJournal Entry Account` jea
        INNER JOIN `tabJournal Entry` je
            ON je.name = jea.parent
        WHERE jea.reference_type = 'Sales Order'
            AND jea.reference_name = %s
            AND je.docstatus = 1
            AND jea.is_advance = 'Yes'
        """,
        sales_order_name,
    )[0][0]

    dates = [d for d in [pe_date, je_date] if d]

    return max(dates) if dates else None




@frappe.whitelist()
def get_order_details_html(order_id):
	if not order_id:
		return {"html": ""}

	doctype = "Sales Order"
	payment_status_field = "custom_payment_status"
	dispatch_status_field = "custom_dispatch_status"

	base_fields = [
		"name",
		"customer",
		"customer_name",
		"customer_group",
		"status",
		"transaction_date",
		"delivery_date",
		"net_total",
		"total_taxes_and_charges",
		"grand_total",
  "rounded_total",
  		"advance_paid",
		"docstatus",
	]

	if _field_exists(doctype, payment_status_field):
		base_fields.append(payment_status_field)

	if _field_exists(doctype, dispatch_status_field):
		base_fields.append(dispatch_status_field)

	select_cols = ", ".join(f"`{field}`" for field in base_fields)

	so_rows = frappe.db.sql(
		f"""
		SELECT {select_cols}
		FROM `tabSales Order`
		WHERE name = %s
		  AND docstatus != 2
		LIMIT 1
		""",
		(order_id,),
		as_dict=True,
	)

	if not so_rows:
		return {"html": ""}

	so = so_rows[0]

	# if (
	# 	so.get("docstatus") != 1
	# 	or so.get(dispatch_status_field) not in TARGET_STATUSES
	# ):
	# 	frappe.throw(
	# 		_("Select a submitted Sales Order with Partial Dispatch or Material Shortage status.")
	# 	)

	order_no = so.get("name")
	custom_shop_name=so.get("custom_shop_name") or ""
	customer = so.get("customer") or ""
	customer_name = so.get("customer_name") or ""
	customer_group = so.get("customer_group") or ""
	status = so.get("status") or ""
	posting_date = so.get("transaction_date") or ""
	delivery_date = so.get("delivery_date") or ""

	payment_status = (
		so.get(payment_status_field)
		if payment_status_field in so
		else ""
	)

	dispatch_status = (
		so.get(dispatch_status_field)
		if dispatch_status_field in so
		else ""
	)

	net_total = r2(so.get("net_total"))
	taxes_and_charges = r2(so.get("total_taxes_and_charges"))
	grand_total = r2(so.get("rounded_total") or so.get("grand_total"))

	item_totals = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS total_items,
			SUM(qty) AS total_qty
		FROM `tabSales Order Item`
		WHERE parent = %s
		""",
		(order_no,),
		as_dict=True,
	)[0]

	total_items = int(item_totals.get("total_items") or 0)
	total_qty = r2(item_totals.get("total_qty") or 0)
	received = r2(so.get("advance_paid") or 0)
	last_payment_date = get_last_payment_date_for_sales_order(order_no)

	pending = r2(max(grand_total - received, 0))

	if pending <= 1:
		pending = 0

	badge_bg, badge_fg = _badge_colors(status)

	full_payment_date = None

	if pending <= 0 and received > 0:
		full_payment_date = last_payment_date
	def esc(value):
		return escape_html(str(value or ""))

	html = f"""
	<div style="border:1px solid #d1d8dd;border-radius:8px;background:#fff;padding:10px;font-size:12px;">

		<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
			<div>
				<div style="font-size:15px;font-weight:700;">
					{esc(order_no)}
				</div>
				<div style="color:#666;">
					{esc(customer_name or customer)}
				</div>
    <div style="color:#666;">
					{esc(custom_shop_name or customer_name)}
				</div>
			</div>

			<div style="
				background:{badge_bg};
				color:{badge_fg};
				padding:4px 10px;
				border-radius:20px;
				font-weight:600;
				font-size:11px;
			">
				{esc(dispatch_status)}
			</div>
		</div>

		<table style="width:100%;border-collapse:collapse;font-size:12px;">
			<tr>
				<td style="padding:3px;"><b>Group</b></td>
				<td style="padding:3px;">{esc(customer_group) or "-"}</td>

				<td style="padding:3px;"><b>Order</b></td>
				<td style="padding:3px;">{esc(posting_date)}</td>
			</tr>

			<tr>
				<td style="padding:3px;"><b>Delivery</b></td>
				<td style="padding:3px;">{esc(delivery_date)}</td>

				<td style="padding:3px;"><b>Dispatch</b></td>
				<td style="padding:3px;">{esc(dispatch_status)}</td>
			</tr>

			<tr>
				<td style="padding:3px;"><b>Payment</b></td>
				<td style="padding:3px;">{esc(payment_status)}</td>

				<td style="padding:3px;"><b>Last Pay</b></td>
				<td style="padding:3px;">{esc(last_payment_date) if last_payment_date else "-"}</td>
			</tr>

			<tr>
				<td style="padding:3px;"><b>Full Pay</b></td>
				<td style="padding:3px;">
					{esc(full_payment_date) if full_payment_date else "-"}
				</td>

				<td style="padding:3px;"><b>Items</b></td>
				<td style="padding:3px;">{total_items} / {total_qty}</td>
			</tr>
		</table>

		<div style="margin-top:10px;border-top:1px solid #eee;padding-top:8px;">
			<table style="width:100%;text-align:center;">
				<tr>
					<td>
						<div style="color:#666;font-size:11px;">Net</div>
						<div style="font-weight:700;">₹ {net_total:,.2f}</div>
					</td>

					<td>
						<div style="color:#666;font-size:11px;">Tax</div>
						<div style="font-weight:700;">₹ {taxes_and_charges:,.2f}</div>
					</td>

					<td>
						<div style="color:#666;font-size:11px;">Total</div>
						<div style="font-weight:700;">₹ {grand_total:,.2f}</div>
					</td>

					<td>
						<div style="color:#16a34a;font-size:11px;">Received</div>
						<div style="font-weight:700;color:#16a34a;">
							₹ {received:,.2f}
						</div>
					</td>

					<td>
						<div style="color:#dc2626;font-size:11px;">Pending</div>
						<div style="font-weight:700;color:#dc2626;">
							₹ {pending:,.2f}
						</div>
					</td>
				</tr>
			</table>
		</div>

	</div>
	"""

	return {
		"html": html,
		"totals": {
			"total_items": total_items,
			"total_qty": total_qty,
			"net_total": net_total,
			"taxes_and_charges": taxes_and_charges,
			"grand_total": grand_total,
			"received": received,
			"pending": pending,
			"payment_status": payment_status,
			"dispatch_status": dispatch_status,
			"last_payment_date": last_payment_date,
			"full_payment_date": full_payment_date,
		},
	}

def _open_source_conditions(filters):
	conditions = [
		"so.docstatus = 1",
		"sre.docstatus = 1",
		"sre.voucher_type = 'Sales Order'",
		"IFNULL(sre.reservation_based_on, 'Qty') = 'Qty'",
		"(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)) > 0",
		"so.custom_dispatch_status IN %(statuses)s",
	]
	params = {"statuses": SOURCE_STATUSES}

	if filters.get("dispatch_status") in SOURCE_STATUSES:
		params["statuses"] = (filters.get("dispatch_status"),)
	source_sales_order = filters.get("source_sales_order")
	if source_sales_order:
		if isinstance(source_sales_order, (list, tuple, set)):
			conditions.append("so.name IN %(source_sales_order)s")
			params["source_sales_order"] = tuple(source_sales_order)
		else:
			conditions.append("so.name = %(source_sales_order)s")
			params["source_sales_order"] = source_sales_order

	return conditions, params


def _append_target_item_conditions(conditions, params, target_sales_order):
	target_items = _get_target_pending_item_keys(target_sales_order)
	if not target_items:
		return False

	item_conditions = []
	for index, (item_code, warehouse) in enumerate(target_items):
		item_key = f"target_item_{index}"
		warehouse_key = f"target_warehouse_{index}"
		item_conditions.append(f"(soi.item_code = %({item_key})s AND soi.warehouse = %({warehouse_key})s)")
		params[item_key] = item_code
		params[warehouse_key] = warehouse

	conditions.append(f"({' OR '.join(item_conditions)})")
	return True


def _source_order_names(selected_sources):
	source_orders = []
	for row in _as_list(selected_sources):
		if isinstance(row, str):
			source_order = row
		else:
			source_order = frappe._dict(row).get("sales_order")
		if source_order and source_order not in source_orders:
			source_orders.append(source_order)

	return source_orders


def _selected_target_requests(target_so, target_items):
	requests = []
	target_item_by_name = {item.name: item for item in target_so.items or []}
	target_item_by_key = {(item.item_code, item.warehouse): item for item in target_so.items or []}

	for row in map(frappe._dict, _as_list(target_items)):
		if row.get("select") is not None and not flt(row.get("select")):
			continue

		target_item = None
		if row.get("sales_order_item"):
			target_item = target_item_by_name.get(row.get("sales_order_item"))
		if not target_item:
			target_item = target_item_by_key.get((row.get("item") or row.get("item_code"), row.get("warehouse")))

		if not target_item:
			continue

		requested_qty = flt(row.get("reserved_qty") or row.get("qty_to_map"))
		if requested_qty <= 0:
			continue
		pending_qty = flt(
			row.get("reserved_qty")
			if row.get("reserved_qty") is not None
			else _pending_qty(target_item))		
		if pending_qty <= 0:
			continue

		requests.append(
			frappe._dict(
				{
					"target_item": target_item,
					"item_code": target_item.item_code,
					"warehouse": target_item.warehouse,
					"qty_needed": min(requested_qty, pending_qty),
					"target_pending_qty": pending_qty,
				}
			)
		)

	return requests


def _get_source_rows_for_mapping(source_orders, target_requests):
	if not source_orders or not target_requests:
		return []

	conditions = [
		"so.docstatus = 1",
		"so.name IN %(source_orders)s",
		"sre.docstatus = 1",
		"sre.voucher_type = 'Sales Order'",
		"IFNULL(sre.reservation_based_on, 'Qty') = 'Qty'",
		"(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)) > 0",
		"so.custom_dispatch_status IN %(statuses)s",
	]
	params = {
		"source_orders": tuple(source_orders),
		"statuses": SOURCE_STATUSES,
	}

	item_conditions = []
	for index, request in enumerate(target_requests):
		item_key = f"request_item_{index}"
		warehouse_key = f"request_warehouse_{index}"
		item_conditions.append(f"(soi.item_code = %({item_key})s AND soi.warehouse = %({warehouse_key})s)")
		params[item_key] = request.item_code
		params[warehouse_key] = request.warehouse

	conditions.append(f"({' OR '.join(item_conditions)})")

	rows = frappe.db.sql(
		f"""
		SELECT
			so.name AS sales_order,
			so.customer,
			so.customer_name,
			so.custom_dispatch_status AS dispatch_status,
			soi.item_code AS item,
			soi.item_name,
			soi.warehouse,
			IFNULL(soi.stock_qty, soi.qty) AS ordered_qty,
			sre.reserved_qty,
			(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)) AS available_qty,
			soi.name AS sales_order_item,
			sre.name AS stock_reservation_entry
		FROM `tabStock Reservation Entry` sre
		INNER JOIN `tabSales Order Item` soi ON soi.name = sre.voucher_detail_no
		INNER JOIN `tabSales Order` so ON so.name = sre.voucher_no
		WHERE {" AND ".join(conditions)}
		ORDER BY so.transaction_date ASC, so.creation ASC
		""",
		params,
		as_dict=True,
	)

	order_index = {sales_order: index for index, sales_order in enumerate(source_orders)}
	return sorted(rows, key=lambda row: (order_index.get(row.sales_order, len(order_index)), row.sales_order, row.sales_order_item))


@frappe.whitelist()
def fetch_source_orders(
	dispatch_status=None,
	source_sales_order=None,
	target_sales_order=None,
):
	if not target_sales_order:
		return []

	filters = frappe._dict(
		dispatch_status=dispatch_status,
		source_sales_order=source_sales_order,
	)
	conditions, params = _open_source_conditions(filters)

	conditions.append("so.name != %(target_sales_order)s")
	params["target_sales_order"] = target_sales_order
	if not _append_target_item_conditions(conditions, params, target_sales_order):
		return []

	return frappe.db.sql(
		f"""
		SELECT
			so.name AS sales_order,
			so.customer,
			so.customer_name,
			so.custom_dispatch_status AS dispatch_status,
			soi.item_code AS item,
			soi.item_name,
			soi.warehouse,
			IFNULL(soi.stock_qty, soi.qty) AS ordered_qty,
			sre.reserved_qty,
			(IFNULL(sre.reserved_qty, 0) - IFNULL(sre.delivered_qty, 0)) AS available_qty,
			soi.name AS sales_order_item,
			sre.name AS stock_reservation_entry
		FROM `tabStock Reservation Entry` sre
		INNER JOIN `tabSales Order Item` soi ON soi.name = sre.voucher_detail_no
		INNER JOIN `tabSales Order` so ON so.name = sre.voucher_no
		WHERE {" AND ".join(conditions)}
		ORDER BY so.transaction_date DESC, so.creation DESC
		""",
		params,
		as_dict=True,
	)

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def source_sales_order_query(doctype, txt, searchfield, start, page_len, filters):
	filters = frappe._dict(filters or {})
	conditions, params = _open_source_conditions(filters)
	target_sales_order = filters.get("target_sales_order")
	if not target_sales_order:
		return []
	target_items = filters.get("target_items") or []
	if isinstance(target_items, str):
		target_items = frappe.parse_json(target_items)

	conditions.append("so.name != %(target_sales_order)s")
	params["target_sales_order"] = target_sales_order

	conditions.append("""
		(
			so.name LIKE %(txt)s
			OR so.customer_name LIKE %(txt)s
		)
	""")

	params["txt"] = f"%{txt}%"

	# Filter by selected target items
	item_conditions = []

	for idx, row in enumerate(target_items):
		row = frappe._dict(row)
		if row.get("select") is not None and not flt(row.get("select")):
			continue

		item_code = row.get("item")
		warehouse = row.get("warehouse")
		required_qty = flt(
			row.get("reserved_qty")
			or row.get("available_qty")
			or 0
		)

		if not item_code:
			continue

		item_conditions.append(f"""
			(
				soi.item_code = %(item_{idx})s
				AND IFNULL(sre.warehouse, '') = %(warehouse_{idx})s
				AND IFNULL(sre.reserved_qty, 0) >= %(qty_{idx})s
			)
		""")

		params[f"item_{idx}"] = item_code
		params[f"warehouse_{idx}"] = warehouse or ""
		params[f"qty_{idx}"] = required_qty

	if item_conditions:
		conditions.append(
			"(" + " OR ".join(item_conditions) + ")"
		)
	rows = frappe.db.sql(
	f"""
	SELECT
		so.name,
		so.customer_name,
		so.custom_dispatch_status,
		so.custom_payment_type,
		ROUND(IFNULL(SUM(sre.reserved_qty), 0), 2) AS reserved_qty
	FROM `tabStock Reservation Entry` sre
	INNER JOIN `tabSales Order Item` soi
		ON soi.name = sre.voucher_detail_no
	INNER JOIN `tabSales Order` so
		ON so.name = sre.voucher_no
	WHERE
		{" AND ".join(conditions)}
		AND so.transaction_date >= '2026-04-01'
	GROUP BY so.name,sre.voucher_no
	ORDER BY
		so.transaction_date DESC,
		so.creation DESC
	LIMIT %(start)s, %(page_len)s
	""",
	{
		**params,
		"start": start,
		"page_len": page_len,
	},
		as_dict=True,
	)

	result = []

	for row in rows:
		full_payment_date = get_last_payment_date_for_sales_order(row.name)

		result.append([
			row.name,
			f"{row.customer_name or ''}"
			f" | Dispatch: {row.custom_dispatch_status or ''}"
			f" | Payment: {row.custom_payment_type or ''}"
			f" | Full Paid: {frappe.utils.formatdate(full_payment_date) if full_payment_date else 'N/A'}"
			f" | Reserved Qty: {_format_qty(row.reserved_qty)}"
		])

	return result

@frappe.whitelist()
def target_sales_order_query(doctype, txt, searchfield, start, page_len, filters):
	return frappe.db.sql(
		"""
		SELECT
			so.name,
			CONCAT(
				IFNULL(so.customer_name, ''),
				' | ',
				IFNULL(so.custom_dispatch_status, '')
			)
		FROM `tabSales Order` so
		WHERE so.docstatus = 1
		  AND so.transaction_date >= "2026-04-01"
		  AND (
			so.custom_dispatch_status IN %(statuses)s
			OR UPPER(IFNULL(so.status, '')) IN %(order_statuses)s
		  )
		  AND IFNULL(so.status, '') NOT IN ('Closed', 'Completed', 'Cancelled')
		  AND (
			so.name LIKE %(txt)s
			OR so.customer_name LIKE %(txt)s
		  )
		ORDER BY so.transaction_date DESC, so.creation DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"statuses": tuple(TARGET_STATUSES),
			"order_statuses": tuple(TARGET_ORDER_STATUSES),
			"txt": f"%{txt or ''}%",
			"start": start,
			"page_len": page_len,
		},
		as_list=True,
	)


def _target_has_pending_item(sales_order, item_code, warehouse):
	target_so = frappe.get_doc("Sales Order", sales_order)
	for item in target_so.items:
		if item.item_code == item_code and item.warehouse == warehouse and _pending_qty(item) > 0:
			return True
	return False


def _get_target_pending_item_keys(target_sales_order):
	if not target_sales_order:
		return set()

	return {
		(row.item_code, row.warehouse)
		for row in frappe.get_all(
			"Sales Order Item",
			filters={"parent": target_sales_order},
			fields=["name", "item_code", "warehouse", "stock_qty", "qty", "delivered_qty", "conversion_factor"],
		)
		if row.item_code and row.warehouse and _pending_qty(row) > 0
	}


@frappe.whitelist()
def fetch_target_items(target_sales_order):
	if not target_sales_order:
		frappe.throw(_("Select Target Sales Order."))

	target_so = frappe.get_doc("Sales Order", target_sales_order)
	if target_so.docstatus != 1:
		frappe.throw(_("Target Sales Order must be submitted."))
	if (
		target_so.custom_dispatch_status not in TARGET_STATUSES
		and (target_so.status or "").upper() not in TARGET_ORDER_STATUSES
	):
		frappe.throw(_("Target Sales Order must have Partial Dispatch or Material Shortage status."))

	rows = []
	for item in target_so.items or []:
		pending_qty = _pending_qty(item)
		if pending_qty <= 0:
			continue

		rows.append(
			{
				"sales_order": target_so.name,
				"customer": target_so.customer,
				"customer_name": target_so.customer_name,
				"dispatch_status": target_so.custom_dispatch_status,
				"item": item.item_code,
				"item_name": item.item_name,
				"warehouse": item.warehouse,
				"ordered_qty": pending_qty,
    			"item_reserved_qty": _reserved_qty(item.name),
				"reserved_qty": 0,
				"available_qty": pending_qty,
				"sales_order_item": item.name,
				"stock_reservation_entry": "",
			}
		)

	return rows


@frappe.whitelist()
def prepare_mapping(selected_sources, target_sales_order, target_items=None):
	source_orders = _source_order_names(selected_sources)
	if not source_orders:
		frappe.throw(_("Select at least one Source Sales Order."))
	if not target_sales_order:
		frappe.throw(_("Select Target Sales Order."))

	target_so = frappe.get_doc("Sales Order", target_sales_order)
	if target_so.docstatus != 1:
		frappe.throw(_("Target Sales Order must be submitted."))
	if (
		target_so.custom_dispatch_status not in TARGET_STATUSES
		and (target_so.status or "").upper() not in TARGET_ORDER_STATUSES
	):
		frappe.throw(_("Target Sales Order must have Partial Dispatch or Material Shortage status."))

	target_requests = _selected_target_requests(target_so, target_items)
	if not target_requests:
		frappe.throw(_("Select at least one Target Order Item and enter Reserved Qty."))

	source_rows = _get_source_rows_for_mapping(source_orders, target_requests)
	source_rows_by_item = {}
	for source in map(frappe._dict, source_rows):
		source_rows_by_item.setdefault((source.item, source.warehouse), []).append(source)

	rows = []
	source_remaining_qty = {
		source.stock_reservation_entry: flt(source.available_qty or source.reserved_qty)
		for source in map(frappe._dict, source_rows)
	}

	for request in target_requests:
		qty_needed = flt(request.qty_needed)
		matching_sources = source_rows_by_item.get(
        (request.item_code, request.warehouse),
        []
    )
		for source in source_rows_by_item.get((request.item_code, request.warehouse), []):
			if qty_needed <= 0:
				break

			available_qty = source_remaining_qty.get(source.stock_reservation_entry, 0)
			qty_to_map = min(available_qty, qty_needed)
			if qty_to_map <= 0:
				continue
			rows.append(
				_mapping_row(
					source,
					request.target_item,
					target_sales_order,
					available_qty,
					request.target_pending_qty,
					qty_to_map,
				)
			)
						
			source_remaining_qty[source.stock_reservation_entry] = available_qty - qty_to_map
			qty_needed -= qty_to_map

		if qty_needed > 0 and matching_sources:
			rows.append(
				_mapping_row(
					matching_sources[0],
					request.target_item,
     				target_sales_order,
					0,
					request.target_pending_qty,
					0,
					_("Selected source orders do not have enough reserved qty for this target item."),
				)
			)

	if not any(flt(row.get("qty_to_map")) > 0 for row in rows):
		frappe.throw(_("Selected source orders do not have matching reserved stock for selected target items."))

	return rows


def _mapping_row(
	source,
	target_item=None,
	target_sales_order=None,
	source_qty=0,
	target_qty=0,
	qty_to_map=0,
	message=""
):
	return {
		
		"source_order": source.get("sales_order"),
		"target_sales_order": target_sales_order,

		"source_sales_order_item": source.get("sales_order_item"),
		"target_sales_order_item": target_item.name if target_item else "",

		"stock_reservation_entry": source.get("stock_reservation_entry"),

		"item_code": source.get("item"),
		"item_name": source.get("item_name"),
		"warehouse": source.get("warehouse"),

		"source_reserved_qty": source_qty
			or flt(source.get("available_qty") or source.get("reserved_qty")),

		"target_pending_qty": target_qty,
		"qty_to_map": qty_to_map,

		"uom": (
			target_item.stock_uom or target_item.uom
		) if target_item else "",

		"mapping_status": (
			"Pending"
			if qty_to_map > 0
			else ("Skipped" if target_item else "Failed")
		),

		"error_message": message,
	}


@frappe.whitelist()
def update_reservation(docname, items, target_sales_order):
	result = _process_reservation_mapping(items, target_sales_order)

	if docname:
		frappe.db.set_value(
			"Stock Reservation Mapping",
			docname,
			{"total_qty_to_map": result.total_qty, "status": "Mapped"},
			update_modified=False,
		)

	frappe.db.commit()
	return result
def _process_reservation_mapping(items, target_sales_order, validate_only=False):

	items = _as_list(items or [])

	if not items:
		frappe.throw(_("No item rows found to map."))

	if not target_sales_order:
		frappe.throw(_("Select Target Sales Order."))

	target_so = frappe.get_doc("Sales Order", target_sales_order)

	source_sales_orders = set()

	total_qty = 0
	mapped_rows = 0

	remaining_target_qty = {}

	cancelled_sources = []
	target_updates = {}

	# =====================================
	# VALIDATE EVERYTHING
	# =====================================

	for row in items:

		qty_to_map = flt(row.qty_to_map)

		if qty_to_map <= 0:
			continue

		source_sre = frappe.get_doc(
			"Stock Reservation Entry",
			row.stock_reservation_entry
		)

		target_item = frappe.get_doc(
			"Sales Order Item",
			row.target_sales_order_item
		)

		if target_item.name not in remaining_target_qty:
			remaining_target_qty[target_item.name] = _pending_qty(target_item)

		current_remaining_qty = remaining_target_qty[target_item.name]

		_validate_row(
			source_sre,
			target_so,
			target_item,
			qty_to_map,
			current_remaining_qty
		)

		remaining_target_qty[target_item.name] -= qty_to_map

		total_qty += qty_to_map
		mapped_rows += 1

		remaining_qty = _available_qty(source_sre) - qty_to_map

		cancelled_sources.append({
			"source_sre": source_sre,
			"remaining_qty": remaining_qty
		})

		target_updates.setdefault(
			target_item.name,
			{
				"target_item": target_item,
				"qty": 0
			}
		)

		target_updates[target_item.name]["qty"] += qty_to_map

		source_sales_orders.add(source_sre.voucher_no)

	if not mapped_rows:
		frappe.throw(_("Enter Qty To Map for at least one valid row."))

	if validate_only:
		return frappe._dict(
			mapped_rows=mapped_rows,
			total_qty=total_qty
		)

	# =====================================
	# STEP 1 : CANCEL SOURCE RESERVATIONS
	# =====================================

	for row in cancelled_sources:

		source_sre = row["source_sre"]

		if source_sre.docstatus == 1:
			source_sre.cancel()

	frappe.db.commit()

	# =====================================
	# STEP 2 : CREATE / UPDATE TARGET SRE
	# =====================================

	for row in target_updates.values():

		target_item = row["target_item"]
		qty_to_add = row["qty"]

		target_sre_name = frappe.db.get_value(
			"Stock Reservation Entry",
			{
				"voucher_type": "Sales Order",
				"voucher_no": target_so.name,
				"voucher_detail_no": target_item.name,
				"docstatus": 1,
				"reservation_based_on": "Qty",
			},
			"name",
		)

		if target_sre_name:

			target_sre = frappe.get_doc(
				"Stock Reservation Entry",
				target_sre_name
			)

			existing_qty = flt(target_sre.reserved_qty)

			target_sre.cancel()

			new_target_sre = frappe.copy_doc(target_sre)

			new_target_sre.name = None
			new_target_sre.amended_from = None
			new_target_sre.docstatus = 0

			new_target_sre.reserved_qty = (
				existing_qty + qty_to_add
			)

			new_target_sre.insert(ignore_permissions=True)
			new_target_sre.submit()

		else:

			target_sre = _get_or_create_target_sre(
				target_so,
				target_item,
				qty_to_add
			)

			if target_sre.docstatus == 0:
				target_sre.submit()

	# =====================================
	# STEP 3 : RECREATE SOURCE BALANCE
	# =====================================

	for row in cancelled_sources:

		source_sre = row["source_sre"]
		remaining_qty = row["remaining_qty"]

		if remaining_qty <= 0:
			continue

		source_available_qty = frappe.db.get_value(
			"Bin",
			{
				"item_code": source_sre.item_code,
				"warehouse": source_sre.warehouse
			},
			"actual_qty"
		) or 0

		new_source_sre = frappe.copy_doc(source_sre)

		new_source_sre.name = None
		new_source_sre.amended_from = None
		new_source_sre.docstatus = 0

		new_source_sre.available_qty = source_available_qty

		new_source_sre.reserved_qty = remaining_qty

		new_source_sre.insert(ignore_permissions=True)
		new_source_sre.submit()

	# =====================================
	# STEP 4 : UPDATE STATUS
	# =====================================

	update_dispatch_status_for_sales_order(
		target_sales_order
	)

	for sales_order in source_sales_orders:
		update_dispatch_status_for_sales_order(
			sales_order
		)

	return frappe._dict(
		mapped_rows=mapped_rows,
		total_qty=total_qty
	)
def _validate_row(
	sre,
	target_so,
	target_item,
	qty_to_map,
	remaining_target_qty
):

	if target_so.docstatus != 1:
		frappe.throw(_("Target Sales Order must be submitted."))

	if sre.docstatus != 1:
		frappe.throw(
			_("Source Stock Reservation Entry {0} must be submitted.")
			.format(sre.name)
		)

	if (sre.reservation_based_on or "Qty") != "Qty":
		frappe.throw(
			_("Serial/Batch reservation cannot be mapped with this tool: {0}")
			.format(sre.name)
		)

	if sre.voucher_no == target_so.name:
		frappe.throw(_("Source and target order cannot be same."))

	if target_item.parent != target_so.name:
		frappe.throw(
			_("Target item does not belong to selected Target Sales Order.")
		)

	if (
		sre.item_code != target_item.item_code
		or sre.warehouse != target_item.warehouse
	):
		frappe.throw(
			_("Source and target item/warehouse must match.")
		)

	if qty_to_map > _available_qty(sre):
		frappe.throw(
			_("Qty To Map is greater than source available reserved qty for {0}.")
			.format(sre.name)
		)

	if qty_to_map > remaining_target_qty:
		frappe.throw(
			_("Qty To Map is greater than remaining target qty for item {0}.")
			.format(target_item.item_code)
		)

	has_serial_no, has_batch_no = frappe.db.get_value(
		"Item",
		target_item.item_code,
		["has_serial_no", "has_batch_no"]
	)

	if has_serial_no or has_batch_no:
		frappe.throw(
			_("Serial/Batch Item {0} cannot be mapped with this tool.")
			.format(target_item.item_code)
		)

def _get_or_create_target_sre(target_so, target_item, qty_to_map):

	target_sre_name = frappe.db.get_value(
		"Stock Reservation Entry",
		{
			"voucher_type": "Sales Order",
			"voucher_no": target_so.name,
			"voucher_detail_no": target_item.name,
			"docstatus": 1,
			"reservation_based_on": "Qty",
		},
		"name",
	)

	if target_sre_name:
		return frappe.get_doc(
			"Stock Reservation Entry",
			target_sre_name
		)

	has_serial_no, has_batch_no = frappe.db.get_value(
		"Item",
		target_item.item_code,
		["has_serial_no", "has_batch_no"]
	)

	available_qty = frappe.db.get_value(
		"Bin",
		{
			"item_code": target_item.item_code,
			"warehouse": target_item.warehouse
		},
		"actual_qty"
	) or 0

	target_sre = frappe.new_doc(
		"Stock Reservation Entry"
	)

	target_sre.update(
		{
			"item_code": target_item.item_code,
			"warehouse": target_item.warehouse,
			"has_serial_no": has_serial_no,
			"has_batch_no": has_batch_no,
			"voucher_type": "Sales Order",
			"voucher_no": target_so.name,
			"voucher_detail_no": target_item.name,
			"voucher_qty": _ordered_qty(target_item),

			# IMPORTANT
			"available_qty": available_qty,
			"reserved_qty": qty_to_map,

			"company": target_so.company,
			"stock_uom": target_item.stock_uom,
			"project": target_so.project,
			"reservation_based_on": "Qty",
		}
	)

	target_sre.insert(ignore_permissions=True)

	return target_sre
