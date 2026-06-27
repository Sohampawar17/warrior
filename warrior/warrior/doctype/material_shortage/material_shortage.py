import frappe
from frappe.model.document import Document
from collections import defaultdict
from frappe.utils import flt
from warrior.public.sales_order import get_available_qty_to_reserve


class MaterialShortage(Document):

	def validate(self):
		if not any(row.supplier for row in self.summery_item):
			frappe.throw("Please set the default supplier item to create the PO.")
		if not any(row.select for row in self.summery_item):
			frappe.throw("Please select any one item to create the PO.")


	def before_save(self):
		for i in self.summery_item:
			if i.po_created:
				i.po_created = 0

	@frappe.whitelist()
	def calculate_shortage(self):
		"""
		Fetch pending Purchase Material Requests
		and populate Material Shortage items
		"""

		self.items = []

		mr_items = frappe.db.sql(
			"""
			SELECT
				mri.parent AS material_request,
				mri.item_code,
				mri.item_name,
				mri.warehouse,
				mri.qty,
				mri.ordered_qty,
				mri.name,
				mri.sales_order,
				mri.sales_order_item
			FROM `tabMaterial Request Item` mri
			INNER JOIN `tabMaterial Request` mr
				ON mr.name = mri.parent
			WHERE
				mr.docstatus = 1
				AND mri.warehouse = %s
				AND mr.material_request_type = 'Purchase'
				AND mr.custom_supplier IS NULL
				AND mri.ordered_qty < mri.qty
			""",
			(self.warehouse,),
			as_dict=True
		)

		if not mr_items:
			frappe.msgprint("No pending Material Requests found")
			return

		for row in mr_items:
			pending_qty = flt(row.qty) - flt(row.ordered_qty)
			if pending_qty <= 0:
				continue

			# balance_qty = get_available_qty_to_reserve(
			# 	item_code=row.item_code,
			# 	warehouse=row.warehouse)
			supplier = frappe.db.get_value(
				"Item Supplier",
				{
					"parent": row.item_code,
					# "custom_company": self.company,
					"custom_default_supplier": 1
				},
				"supplier"
			)
			order_qty=frappe.db.get_value("Sales Order Item",{"item_code":row.item_code,"parent":row.sales_order,"docstatus":["!=",2]},"SUM(qty)")
			invoice_qty=frappe.db.get_value("Sales Invoice Item",{"item_code":row.item_code,"sales_order":row.sales_order,"docstatus":["!=",2]},"SUM(qty)")

			self.append("items", {
				"material_request": row.material_request,
				"material_request_item": row.name,
				"sales_order_item": row.sales_order_item,
				"sales_order": row.sales_order,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"warehouse": row.warehouse,
				# "balance_qty": balance_qty,
				"shortage_qty": pending_qty,
				"order_qty":order_qty or 0,
				"invoice_qty":invoice_qty or 0,
				"supplier": supplier,
			})

		self.build_summary_table()
	# --------------------------------------------------
	@frappe.whitelist()
	def build_summary_table(self):
		"""
		Combine Material Shortage Items
		item + warehouse + supplier wise
		"""

		self.set("summery_item", [])

		grouped = defaultdict(lambda: {
			"total_qty": 0,
			"item_name": "",
			"mrs": set()
		})

		for row in self.items:
			key = (row.item_code, row.warehouse, row.supplier)

			grouped[key]["total_qty"] += flt(row.shortage_qty)
			grouped[key]["item_name"] = row.item_name
			grouped[key]["mrs"].add(row.material_request)

		for (item_code, warehouse, supplier), data in grouped.items():
			bin=frappe.db.get_value("Bin",{"item_code":item_code,"warehouse":warehouse},["actual_qty","reserved_stock"],as_dict=True)
			self.append("summery_item", {
				"item_code": item_code,
				"item_name": data["item_name"],
				"warehouse": warehouse,
				"supplier": supplier,
				"supplier_name":frappe.get_cached_value("Supplier",supplier,"supplier_name"),
				"total_shortage_qty": data["total_qty"],
				"warehouse_qty":bin.get("actual_qty") or 0,
				"reserved_qty":bin.get("reserved_stock") or 0,
				"available_qty":flt(bin.get("actual_qty") - bin.get("reserved_stock")),
				"source_items": ", ".join(sorted(data["mrs"])),
				"po_created": 0
			})
		# --------------------------------------------------
	def before_submit(self):
		self.create_purchase_orders()
		self.summery_item=[d for d in self.summery_item if d.select==1]
		checked_items = [d for d in self.summery_item if d.select==1]
		self.items=[d for d in self.items if d.item_code in [row.item_code for row in checked_items]]

	@frappe.whitelist()
	def create_purchase_orders(self):
		"""
		Create ONE Purchase Order per supplier
		from Material Shortage Summary Items
		"""

		supplier_map = defaultdict(list)
		affected_mrs = set()

		# STEP 1: GROUP BY SUPPLIER
		for row in self.summery_item:
			if row.select==0:
				continue
			if row.po_created:
				continue

			if not row.supplier:
				frappe.throw(f"Supplier missing for item {row.item_code}")

			supplier_map[row.supplier].append(row)

			if row.source_items:
				for mr in row.source_items.split(","):
					affected_mrs.add(mr.strip())

		if not supplier_map:
			frappe.msgprint("All items already converted to Purchase Orders")
			return

		# STEP 2: CREATE PO
		for supplier, rows in supplier_map.items():
			po = frappe.new_doc("Purchase Order")
			po.company = self.company
			po.supplier = supplier
			po.schedule_date = frappe.utils.nowdate()
			po.set_warehouse = self.warehouse

			# prevent auto email spam
			po.flags.ignore_email = True
			po.buying_price_list= frappe.db.get_value("Supplier", supplier, "default_price_list") or ""
			# IMPORTANT: traceability for cancel reversal
			po.remarks = f"Material Shortage:{self.name}"

			for row in rows:
				po.append("items", {
					"item_code": row.item_code,
					"qty": flt(row.total_shortage_qty),
					"warehouse": row.warehouse,
				})
			po.custom_reference_type = "Material Shortage"
			po.custom_reference_name = self.name
			po.tc_name="Terms And Condition"
			po.set_missing_values()
			po.insert(ignore_permissions=True)
			po.save(ignore_permissions=True)

			for row in rows:
				row.po_created = 1
			
		# STEP 3: UPDATE MR STATUS
		affected_mrs |= update_mr_ordered_qty_from_material_shortage(self)
		update_material_request_status(affected_mrs)

		frappe.msgprint("✅ Purchase Orders created successfully")

	def on_cancel(self):
		"""
		Reverse ONLY the effect of this Material Shortage
		- Cancel / delete linked Purchase Orders
		- Subtract total_shortage_qty from MR Item ordered_qty
		- Set Material Request status to Pending
		"""

		affected_mrs = set()

		# ------------------------------------------------
		# STEP 1: CANCEL / DELETE LINKED PURCHASE ORDERS
		# ------------------------------------------------
		pos = frappe.get_all(
			"Purchase Order",
			filters={
				"custom_reference_type": "Material Shortage",
				"custom_reference_name": self.name,
				"docstatus": ["!=", 2],  # not already cancelled
			},
			pluck="name",
		)

		for po_name in pos:
			po = frappe.get_doc("Purchase Order", po_name)

			# SAFETY CHECK: block if submitted Purchase Receipt exists
			pr_exists = frappe.db.exists(
				"Purchase Receipt Item",
				{
					"purchase_order": po.name,
					"docstatus": 1,  # submitted PR
				},
			)
			if pr_exists:
				frappe.throw(
					f"Cannot cancel Material Shortage. "
					f"Purchase Receipt exists for PO {po.name}"
				)

			if po.docstatus == 1:
				po.cancel()
			elif po.docstatus == 0:
				frappe.delete_doc("Purchase Order", po.name, force=1)

		# ------------------------------------------------
		# STEP 2: REVERSE MR ordered_qty (delta reversal)
		# ------------------------------------------------
		for row in self.items:
			mr = row.material_request
			mri = row.material_request_item  # tabMaterial Request Item.name

			if not mr or not mri:
				continue

			affected_mrs.add(mr)

			ordered_qty_added = flt(row.shortage_qty or 0)
			if ordered_qty_added:
				current_ordered = flt(
					frappe.db.get_value(
						"Material Request Item",
						mri,
						"ordered_qty",
					) or 0
				)

				new_ordered = max(current_ordered - ordered_qty_added, 0)

				frappe.db.set_value(
					"Material Request Item",
					mri,
					"ordered_qty",
					new_ordered,
					update_modified=False,
				)

			# reset summary flag
			row.po_created = 0

		# ------------------------------------------------
		# STEP 3: FORCE MATERIAL REQUEST STATUS → Pending
		# ------------------------------------------------
		for mr_name in affected_mrs:
			if frappe.db.get_value("Material Request", mr_name, "docstatus") != 1:
				continue

			frappe.db.set_value(
				"Material Request",
				mr_name,
				"status",
				"Pending",  # exact status value
				update_modified=False,
			)


		
# ======================================================
# HELPER
# ======================================================
def recompute_mr_ordered_qty_from_po(material_requests):
	"""
	Recalculate Material Request Item.ordered_qty from active (not cancelled) Purchase Orders.
	"""
	for mr_name in material_requests:
		if frappe.db.get_value("Material Request", mr_name, "docstatus") != 1:
			continue

		mr_items = frappe.db.get_all(
			"Material Request Item",
			filters={"parent": mr_name, "parenttype": "Material Request"},
			fields=["name"],
		)

		for mri in mr_items:
			ordered_qty = frappe.db.sql(
				"""
				select ifnull(sum(poi.qty), 0)
				from `tabPurchase Order Item` poi
				inner join `tabPurchase Order` po on po.name = poi.parent
				where po.docstatus != 2
				  and poi.material_request = %s
				  and poi.material_request_item = %s
				""",
				(mr_name, mri.name),
			)[0][0] or 0

			frappe.db.set_value(
				"Material Request Item",
				mri.name,
				"ordered_qty",
				flt(ordered_qty),
				update_modified=False,
			)



def update_mr_ordered_qty_from_material_shortage(doc):
	"""
	Use Material Shortage summery_item to update MR Item.ordered_qty.
	Rule: ordered_qty = summary total_shortage_qty (capped by requested qty).
	"""
	if not doc.get("summery_item"):
		return set()

	affected_mrs = set()

	for s in doc.summery_item:
		if not s.select:
			continue
		if not s.source_items:
			continue

		summary_qty = flt(s.total_shortage_qty)
		if summary_qty <= 0:
			continue

		item_code = (s.item_code or "").strip()
		if not item_code:
			continue

		for mr_name in s.source_items.split(","):
			mr_name = (mr_name or "").strip()
			if not mr_name:
				continue

			# update only submitted MRs
			docstatus = frappe.db.get_value("Material Request", mr_name, "docstatus")
			if docstatus != 1:
				continue

			affected_mrs.add(mr_name)

			# update all matching item rows in that MR (in case item repeats)
			mr_items = frappe.db.get_all(
				"Material Request Item",
				filters={"parent": mr_name, "parenttype": "Material Request", "item_code": item_code},
				fields=["name", "qty", "ordered_qty"],
			)

			for it in mr_items:
				req_qty = flt(it.qty)
				new_ordered = min(req_qty, summary_qty)  # safe cap

				if flt(it.ordered_qty) != new_ordered:
					frappe.db.set_value(
						"Material Request Item",
						it.name,
						"ordered_qty",
						new_ordered,
						update_modified=False,
					)

	return affected_mrs
def update_material_request_status(material_requests):
	for mr_name in material_requests:
		docstatus = frappe.db.get_value("Material Request", mr_name, "docstatus")
		if docstatus != 1:
			continue

		items = frappe.db.get_all(
			"Material Request Item",
			filters={"parent": mr_name, "parenttype": "Material Request"},
			fields=["qty", "ordered_qty"],
		)

		total_qty = sum(flt(i.qty) for i in items)
		ordered_qty = sum(flt(i.ordered_qty) for i in items)

		if ordered_qty == 0:
			status = "Pending"
		elif ordered_qty < total_qty:
			status = "Partially Ordered"
		else:
			status = "Ordered"

		frappe.db.set_value("Material Request", mr_name, "status", status, update_modified=True)
