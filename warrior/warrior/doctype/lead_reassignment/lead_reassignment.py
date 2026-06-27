import json

import frappe
from frappe import _
from frappe.model.document import Document


class LeadReassignment(Document):
	def validate(self):
		self.validate_users()

	def before_submit(self):
		self.validate_reassignment()

	def on_submit(self):
		leads = get_reassignable_leads(self.user, self.get_selected_stages())
		if not leads:
			frappe.throw(_("No open leads found for selected stages."))

		reassign_leads(leads, self.user, self.lead_reassigned_to, self.lead_reassigned_stage)
		frappe.msgprint(_("{0} leads reassigned successfully.").format(len(leads)))

	def validate_users(self):
		open_lead_todo_users = set(get_open_lead_todo_users())
		if self.user and self.user not in open_lead_todo_users:
			frappe.throw(get_open_lead_todo_user_error(self.user))

		if self.lead_reassigned_to and self.lead_reassigned_to not in open_lead_todo_users:
			frappe.throw(get_open_lead_todo_user_error(self.lead_reassigned_to))

	def validate_reassignment(self):
		if self.user == self.lead_reassigned_to:
			frappe.throw(_("User and Lead Reassigned To cannot be same."))

		selected_stages = self.get_selected_stages()
		if not selected_stages:
			frappe.throw(_("Select at least one stage to reassign."))

		if not self.lead_reassigned_stage:
			frappe.throw(_("Select Lead Reassigned Stage."))

		available_counts = {
			row.lead_stage: row.lead_count
			for row in get_stage_counts(self.user)
		}
		for stage in selected_stages:
			if available_counts.get(stage, 0) <= 0:
				frappe.throw(_("No open leads available for stage {0}.").format(stage))

	def get_selected_stages(self):
		return [row.lead_stage for row in self.stages if row.select and row.lead_stage]


def get_open_lead_todo_user_error(user):
	return _("User {0} does not have any open Lead assignment.").format(user)


def get_open_lead_todo_users():
	return [
		row.name
		for row in frappe.db.sql(
			"""
			SELECT DISTINCT u.name
			FROM `tabUser` u
			INNER JOIN `tabToDo` t
				ON t.allocated_to = u.name
			WHERE
				u.enabled = 1
				AND t.reference_type = 'Lead'
				AND t.status = 'Open'
			""",
			as_dict=True,
		)
	]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_open_lead_todo_user_query(doctype, txt, searchfield, start, page_len, filters):
	params = {
		"txt": f"%{txt}%",
		"start": start,
		"page_len": page_len,
	}

	return frappe.db.sql(
		"""
		SELECT DISTINCT u.name, u.full_name
		FROM `tabUser` u
		INNER JOIN `tabToDo` t
			ON t.allocated_to = u.name
		WHERE
			u.enabled = 1
			AND t.reference_type = 'Lead'
			AND t.status = 'Open'
			AND (u.name LIKE %(txt)s OR u.full_name LIKE %(txt)s)
		ORDER BY u.full_name ASC, u.name ASC
		LIMIT %(start)s, %(page_len)s
		""",
		params,
	)


@frappe.whitelist()
def get_stage_counts(user):
	if not user:
		return []

	params = {"user": user}

	counts = {
		row.custom_lead_stage: row.lead_count
		for row in frappe.db.sql(
			"""
			SELECT l.custom_lead_stage, COUNT(DISTINCT l.name) AS lead_count
			FROM `tabLead` l
			INNER JOIN `tabToDo` t
				ON t.reference_type = 'Lead'
				AND t.reference_name = l.name
				AND t.allocated_to = %(user)s
				AND t.status = 'Open'
			WHERE
				IFNULL(l.custom_lead_stage, '') != ''
			GROUP BY l.custom_lead_stage
			""",
			params,
			as_dict=True,
		)
	}

	stages = frappe.get_all(
		"Lead Stages",
		filters={"disabled": 0},
		fields=["name"],
		order_by="creation asc",
	)

	return [
		frappe._dict({"lead_stage": stage.name, "lead_count": counts.get(stage.name, 0)})
		for stage in stages
	]


def get_reassignable_leads(user, stages):
	if not stages:
		return []

	params = {"user": user, "stages": tuple(stages)}

	return frappe.db.sql(
		"""
		SELECT DISTINCT l.name
		FROM `tabLead` l
		INNER JOIN `tabToDo` t
			ON t.reference_type = 'Lead'
			AND t.reference_name = l.name
			AND t.allocated_to = %(user)s
			AND t.status = 'Open'
		WHERE
			l.custom_lead_stage IN %(stages)s
		""",
		params,
		as_dict=True,
	)

from frappe.desk.form.assign_to import add as add_assignment


def reassign_leads(leads, old_user, new_user, new_stage):
	lead_names = [lead.name for lead in leads]
	if not lead_names:
		return

	new_user_enabled = frappe.db.get_value("User", new_user, "enabled") == 1
	assign_value = json.dumps([new_user]) if new_user_enabled else "[]"

	frappe.db.sql(
		"""
		UPDATE `tabToDo`
		SET
			status = 'Closed',
			modified = NOW(),
			modified_by = %(modified_by)s
		WHERE
			reference_type = 'Lead'
			AND reference_name IN %(lead_names)s
			AND status != 'Closed'
		""",
		{
			"lead_names": tuple(lead_names),
			"modified_by": frappe.session.user,
		},
	)

	if new_user_enabled:
		for lead_name in lead_names:
			add_assignment(
				{
					"assign_to": [new_user],
					"doctype": "Lead",
					"name": lead_name,
					"description": "Lead Reassigned",
				},
				ignore_permissions=True,
			)

	for lead in leads:
		frappe.db.set_value(
			"Lead",
			lead.name,
			"custom_lead_stage",
			new_stage,
			update_modified=True
		)
