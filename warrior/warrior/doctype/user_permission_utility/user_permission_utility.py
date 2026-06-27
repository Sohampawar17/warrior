# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

UP_DOCTYPE = "User Permission"

# ✅ Put your exact doctype names here
CUSTOMER_GROUP_DOCTYPE = "Customer Group"
TEHSIL_DOCTYPE = "Tahshil"       # change to "Tahsil" if that's your actual DocType
MARKETPLACE_DOCTYPE = "Marketplace"


class UserPermissionUtility(Document):
	def before_save(self):
		if not self.user:
			return

		# -------------------------
		# Detect marker field once
		# -------------------------
		meta = frappe.get_meta(UP_DOCTYPE)
		has_marker = any(df.fieldname == "custom_created_by_utility" for df in meta.fields)

		# -------------------------
		# OLD state (from DB)
		# -------------------------
		old_user = None
		old_cg, old_t, old_m = set(), set(), set()

		if not self.is_new():
			old_doc = frappe.get_doc(self.doctype, self.name)
			old_user = old_doc.user

			old_cg = {r.customer_group for r in (old_doc.customer_groups or []) if r.customer_group}
			old_t  = {r.tehsil for r in (old_doc.tehsils or []) if r.tehsil}
			old_m  = {r.marketplace for r in (old_doc.marketplaces or []) if r.marketplace}

		# -------------------------
		# NEW state (current memory)
		# -------------------------
		new_cg = {r.customer_group for r in (self.customer_groups or []) if r.customer_group}
		new_t  = {r.tehsil for r in (self.tehsils or []) if r.tehsil}
		new_m  = {r.marketplace for r in (self.marketplaces or []) if r.marketplace}

		# -------------------------
		# If user changed, wipe old user's utility permissions
		# -------------------------
		if old_user and old_user != self.user:
			self._delete_all_utility_permissions_for_user(old_user, has_marker)
			# treat everything as new add for new user
			old_cg, old_t, old_m = set(), set(), set()

		# -------------------------
		# Compute diffs
		# -------------------------
		to_add_cg = new_cg - old_cg
		to_remove_cg = old_cg - new_cg

		to_add_t = new_t - old_t
		to_remove_t = old_t - new_t

		to_add_m = new_m - old_m
		to_remove_m = old_m - new_m

		# -------------------------
		# Apply changes
		# -------------------------
		for v in to_add_cg:
			self._ensure_permission(self.user, CUSTOMER_GROUP_DOCTYPE, v, has_marker)

		for v in to_add_t:
			self._ensure_permission(self.user, TEHSIL_DOCTYPE, v, has_marker)

		for v in to_add_m:
			self._ensure_permission(self.user, MARKETPLACE_DOCTYPE, v, has_marker)

		for v in to_remove_cg:
			self._delete_permission(self.user, CUSTOMER_GROUP_DOCTYPE, v, has_marker)

		for v in to_remove_t:
			self._delete_permission(self.user, TEHSIL_DOCTYPE, v, has_marker)

		for v in to_remove_m:
			self._delete_permission(self.user, MARKETPLACE_DOCTYPE, v, has_marker)

	# ---------------------------
	# Helpers
	# ---------------------------
	def _ensure_permission(self, user, allow, for_value, has_marker):
		if not for_value:
			return

		# already exists (manual or utility)
		if frappe.db.exists(UP_DOCTYPE, {"user": user, "allow": allow, "for_value": for_value}):
			return

		up = frappe.get_doc({
			"doctype": UP_DOCTYPE,
			"user": user,
			"allow": allow,
			"for_value": for_value,
			"apply_to_all_doctypes": 1,
		})

		if has_marker:
			up.custom_created_by_utility = 1

		up.insert(ignore_permissions=True)

	def _delete_permission(self, user, allow, for_value, has_marker):
		filters = {"user": user, "allow": allow, "for_value": for_value}
		if has_marker:
			filters["custom_created_by_utility"] = 1
		frappe.db.delete(UP_DOCTYPE, filters)

	def _delete_all_utility_permissions_for_user(self, user, has_marker):
		filters = {"user": user}
		if has_marker:
			filters["custom_created_by_utility"] = 1
		frappe.db.delete(UP_DOCTYPE, filters)


	def on_trash(self):
		"""
		When User Permission Utility is deleted,
		remove all permissions created by this utility for the user.
		"""
		if not self.user:
			return

		# detect marker field once
		meta = frappe.get_meta(UP_DOCTYPE)
		has_marker = any(df.fieldname == "custom_created_by_utility" for df in meta.fields)

		filters = {"user": self.user}

		# delete only utility-created permissions if marker exists
		if has_marker:
			filters["custom_created_by_utility"] = 1

		frappe.db.delete(UP_DOCTYPE, filters)
