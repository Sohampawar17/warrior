import frappe
from frappe import STANDARD_USERS, _
from frappe.core.doctype.user.user import User
from frappe.model.rename_doc import rename_doc
from frappe.sessions import clear_sessions
from frappe.utils import cint


class CustomUser(User):
	def check_enable_disable(self):
		# Preserve standard guard rails
		if not cint(self.enabled) and self.name in STANDARD_USERS:
			frappe.throw(_("User {0} cannot be disabled").format(self.name))

		# Preserve standard logout behavior for disabled users
		if not cint(self.enabled) and getattr(frappe.local, "login_manager", None):
			frappe.local.login_manager.logout(user=self.name)

		# Avoid permission failure when editing another user's User doc
		if frappe.db.exists("Notification Settings", self.name):
			frappe.db.set_value(
				"Notification Settings",
				self.name,
				"enabled",
				cint(self.enabled),
				update_modified=False,
			)

	def after_rename(self, old_name, new_name, merge=False):
		tables = frappe.db.get_tables()
		for tab in tables:
			desc = frappe.db.get_table_columns_description(tab)
			has_fields = [d.get("name") for d in desc if d.get("name") in ["owner", "modified_by"]]
			for field in has_fields:
				frappe.db.sql(
					"""UPDATE `{}`
					SET `{}` = {}
					WHERE `{}` = {}""".format(tab, field, "%s", field, "%s"),
					(new_name, old_name),
				)

		# Notification Settings is one-to-one with User and should be renamed as system action.
		if frappe.db.exists("Notification Settings", old_name):
			rename_doc(
				"Notification Settings",
				old_name,
				new_name,
				force=True,
				show_alert=False,
				ignore_permissions=True,
			)

		frappe.db.set_value("User", new_name, "email", new_name)
		clear_sessions(user=old_name, force=True)
		clear_sessions(user=new_name, force=True)
