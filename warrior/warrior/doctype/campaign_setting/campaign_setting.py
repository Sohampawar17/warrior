# Copyright (c) 2026, Abhishek Dubey and contributors
# For license information, please see license.txt
import frappe
import re
from frappe.desk.form.assign_to import add as add_assignment
from frappe.model.document import Document
from frappe.utils import add_days, nowdate, now_datetime
from frappe.utils.csvutils import get_csv_content_from_google_sheets, read_csv_content
from frappe import _


class CampaignSetting(Document):
	pass


CAMPAIGN_WHATSAPP_TEMPLATE_MAP = {
    # Seeder Lead
    "120241846425050669": "seeders_promotion",
    "120241845248240669": "seeders_promotion",
    "120241843505650669": "seeders_promotion",

    # Solar Camera Lead
    "120241846919630669": "solar_camera_promotion",
    "120241849640650669": "solar_camera_promotion",

    # Mobile Auto Lead
    "120241859851470669": "mobile_auto_promotion",
    "120241861719340669": "mobile_auto_promotion",

    # Spray Pump Lead
    "120241862230010669": "toofan_spray_pump_promotion",
}

CAMPAIGN_WHATSAPP_TEMPLATE_PAYLOAD = {
    "App_Link": "https://www.shoption.in/app",
}
@frappe.whitelist()
def import_leads_from_google_sheet():
    frappe.enqueue(
        "warrior.warrior.doctype.campaign_setting.campaign_setting._import_leads_job",
        queue="long",
        timeout=5000
    )
    return {"status": "started"}



def _import_leads_job():

    campaign_setting = frappe.get_single("Campaign Setting")
    google_sheet_url = campaign_setting.google_sheet_link

    if not google_sheet_url:
        frappe.throw("Google Sheet URL is not configured")

    content = get_csv_content_from_google_sheets(google_sheet_url)
    raw_rows = read_csv_content(content)

    if not raw_rows or len(raw_rows) < 2:
        return

    headers = raw_rows[0]
    data_rows = raw_rows[1:]

    inserted = 0
    updated = 0
    skipped = 0

    error_logs = []
    try:

        # 🔥 preload existing leads
        existing_leads = frappe.get_all(
            "Lead",
            filters={"campaign_name":["is","set"]},
            fields=["name", "mobile_no", "campaign_name", "lead_owner"],
            limit_page_length=0
        )

        existing_map = {
            (
                str(d.mobile_no).strip(),
                str(d.campaign_name).strip()
            ): d
            for d in existing_leads
            if d.mobile_no
        }

        for idx, row in enumerate(data_rows, start=1):

            try:

                row_dict = {
                    headers[i]: row[i] if i < len(row) else None
                    for i in range(len(headers))
                }
                phone = str(row_dict.get("Phone Number") or "").strip()

                if not phone:
                    skipped += 1
                    continue

                full_name = (row_dict.get("Full Name") or "").strip()
                email = (row_dict.get("Email") or "").strip().lower()
                source = (row_dict.get("Source") or "").strip()
                city = (row_dict.get("City") or "").strip()
                campaign_id = (row_dict.get("Campaign ID") or "").strip()

                lead_type = (
                    frappe.db.get_value(
                        "Campaign",
                        campaign_id,
                        "custom_campaign_for"
                    )
                    if campaign_id else None
                ) or "Lead"
                
                duplicate_key = (phone, campaign_id)

                # ==========================================================
                # UPDATE EXISTING LEAD
                # ==========================================================
                if duplicate_key in existing_map:

                    existing_lead = existing_map[duplicate_key]

                    lead_doc = frappe.get_doc("Lead", existing_lead.name)

                    # 🔥 update fields
                    lead_doc.first_name = full_name
                    lead_doc.lead_name = full_name
                    lead_doc.email_id = email
                    lead_doc.source = source
                    lead_doc.city = city
                    lead_doc.type = lead_type
                    lead_doc.custom_lead_stage = "Pending"
                    row_dict = normalize_row_dict(row_dict)
                    # ======================================================
                    # QUESTIONS
                    # ======================================================
                    for i in range(1, 11):
                        question = row_dict.get(f"q{i}")
                        answer = row_dict.get(f"answer{i}")

                        if question and answer:
                            lead_doc.append(
                                "custom_lead_questions_and_answers",
                                {
                                    "questions": str(question).strip(),
                                    "answers": str(answer).strip(),
                                },
                            )

                    # ✅ Columns
                    for i in range(1, 11):
                        value = row_dict.get(f"coloumn{i}")

                        if value:
                            lead_doc.append(
                                "custom_campaign_columns",
                                {
                                    "columns": f"Column {i}",
                                    "value": str(value).strip(),
                                },
                            )

                    lead_doc.save(ignore_permissions=True)

                    # ======================================================
                    # CLOSE OLD TODOS
                    # ======================================================
                    # ======================================================
                    # GET CURRENT ASSIGNED TODO
                    # ======================================================

                    assigned_todo = frappe.db.get_value(
                        "ToDo",
                        {
                            "reference_type": "Lead",
                            "reference_name": existing_lead.name,
                            "status": ["!=", "Closed"]
                        },
                        ["name", "allocated_to"],
                        as_dict=True
                    )

                    # ======================================================
                    # CLOSE OLD TODOS
                    # ======================================================

                    old_todos = frappe.get_all(
                        "ToDo",
                        filters={
                            "reference_type": "Lead",
                            "reference_name": lead_doc.name,
                            "status": ["!=", "Closed"]
                        },
                        pluck="name"
                    )

                    for todo_name in old_todos:

                        frappe.db.set_value(
                            "ToDo",
                            todo_name,
                            "status",
                            "Closed",
                            update_modified=False
                        )

                    # ======================================================
                    # REASSIGN TO SAME ASSIGNED USER
                    # ======================================================
                    _send_campaign_lead_whatsapp([lead_doc.name])

                    if assigned_todo and assigned_todo.allocated_to:

                        frappe.get_doc({
                            "doctype": "ToDo",
                            "allocated_to": assigned_todo.allocated_to,
                            "reference_type": "Lead",
                            "reference_name": lead_doc.name,
                            "description": f"Lead Reassigned: {lead_doc.lead_name}",
                            "status": "Open",
                            "date": now_datetime().date(),
                            "priority": "Medium",
                        }).insert(ignore_permissions=True)

                    updated += 1
                    continue

                # ==========================================================
                # CREATE NEW LEAD
                # ==========================================================
                lead_doc = frappe.get_doc({
                    "doctype": "Lead",
                    "first_name": full_name,
                    "lead_name": full_name,
                    "mobile_no": phone,
                    "email_id": email,
                    "source": source,
                    "city": city,
                    "campaign_name": campaign_id,
                    "type": lead_type
                })
                row_dict = normalize_row_dict(row_dict)
                # ==========================================================
                # QUESTIONS
                # ==========================================================
                for i in range(1, 11):
                    question = row_dict.get(f"q{i}")
                    answer = row_dict.get(f"answer{i}")

                    if question and answer:
                        lead_doc.append(
                            "custom_lead_questions_and_answers",
                            {
                                "questions": str(question).strip(),
                                "answers": str(answer).strip(),
                            },
                        )

                # ✅ Columns
                for i in range(1, 11):
                    value = row_dict.get(f"coloumn{i}")

                    if value:
                        lead_doc.append(
                            "custom_campaign_columns",
                            {
                                "columns": f"Column {i}",
                                "value": str(value).strip(),
                            },
                        )

                lead_doc.insert(ignore_permissions=True)

                inserted += 1

            except Exception:

                error_message = frappe.get_traceback()
                frappe.log_error(
                    title=f"Lead Import Row Error #{idx}",
                    message=error_message
                )

                skipped += 1

                continue

        frappe.db.commit()

        # ==============================================================
        # FINAL SUMMARY
        # ==============================================================
        summary = f"""
        Lead Import Completed

        Inserted: {inserted}
        Updated: {updated}
        Skipped: {skipped}
        """

        if error_logs:
            summary += "\n\nErrors:\n\n" + "\n\n".join(error_logs[:20])

        frappe.log_error(
            title="Lead Import Summary",
            message=summary
        )

        
    except Exception:
        frappe.db.rollback()
        error_message = frappe.get_traceback()
        frappe.log_error(
            title="Lead Import Failed",
            message=error_message
        )
        raise


def normalize_row_dict(row_dict):
    normalized = {}

    for k, v in row_dict.items():
        if not k:
            continue

        clean_key = (
            str(k)
            .strip()
            .lower()
            .replace(" ", "")   # remove all spaces
        )

        normalized[clean_key] = v

    return normalized

def _split_mobile_numbers(mobile_no):
    if not mobile_no:
        return []

    mobile_values = []
    for value in re.split(r"[,;|/\n\r]+", str(mobile_no)):
        value = value.strip()
        if value:
            mobile_values.append(value)

    return mobile_values



def auto_assign_campaign_leads():
    """Assign today's unassigned leads with campaign-wise round robin."""
    try:
        start_of_day, end_of_day = _get_today_window()
        campaign_names = _get_campaigns_with_unassigned_leads(start_of_day, end_of_day)
        for campaign_name in campaign_names:
            _assign_campaign_leads_round_robin(campaign_name, start_of_day, end_of_day)

        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="Auto Assign Campaign Leads Failed",
            message=frappe.get_traceback()
        )


from frappe.utils import nowdate, add_days

def _get_today_window():
    today = nowdate()
    yesterday = add_days(today, -1)
    tomorrow = add_days(today, 1)

    return f"{yesterday} 00:00:00", f"{tomorrow} 00:00:00"


def _get_campaigns_with_unassigned_leads(start_of_day, end_of_day):
    rows = frappe.get_all(
        "Lead",
        filters=[
            ["creation", ">=", start_of_day],
            ["creation", "<", end_of_day],
            ["campaign_name", "is", "set"],
            ["_assign", "in", ["", None, "[]"]],
        ],
        fields=["campaign_name"],
        distinct=True,
        order_by="campaign_name asc",
    )
    return [row.campaign_name for row in rows]

from frappe.utils import now_datetime
import json

def _assign_campaign_leads_round_robin(campaign_name, start_of_day, end_of_day):

    campaign = frappe.get_doc("Campaign", campaign_name)
    warriors = [row.warrior for row in campaign.custom_campaign_warriors if row.warrior]

    if not warriors:
        return

    current_idx = _get_last_assignee_index(
        campaign_name, warriors, start_of_day, end_of_day
    )

    leads = frappe.get_all(
        "Lead",
        filters=[
            ["campaign_name", "=", campaign_name],
            ["creation", ">=", start_of_day],
            ["creation", "<", end_of_day],
            ["_assign", "in", ["", None, "[]"]],
        ],
        pluck="name",
        order_by="creation asc",
    )

    if not leads:
        return

    now = now_datetime()
    assign_map = {}
    values = []

    # -------------------------------
    # 🔁 ROUND ROBIN
    # -------------------------------
    for lead in leads:
        current_idx = (current_idx + 1) % len(warriors)
        assignee = warriors[current_idx]

        assign_map[lead] = assignee

        values.append((
            frappe.generate_hash(),   # name
            assignee,                 # allocated_to
            "Lead",                  # reference_type
            lead,                    # reference_name
            "Open",                  # status
            "Auto-assigned",         # description
            now,                     # creation
            now,                     # modified
            frappe.session.user      # owner
        ))

    # -------------------------------
    # ⚡ BULK INSERT
    # -------------------------------
    columns = [
        "name",
        "allocated_to",
        "reference_type",
        "reference_name",
        "status",
        "description",
        "creation",
        "modified",
        "owner",
    ]

    frappe.db.bulk_insert("ToDo", columns, values)

    # -------------------------------
    # ⚡ BULK UPDATE _assign
    # -------------------------------
    case_sql = " ".join(
        [f"WHEN '{l}' THEN '{json.dumps([assign_map[l]])}'" for l in leads]
    )

    frappe.db.sql(f"""
        UPDATE `tabLead`
        SET _assign = CASE name
            {case_sql}
        END
        WHERE name IN %(names)s
    """, {"names": leads})
    _send_campaign_lead_whatsapp(leads)

    frappe.db.commit()

    frappe.log_error(
        title="Bulk Assignment Done",
        message=f"{campaign_name} → {len(leads)} leads assigned"
    )

def _send_campaign_lead_whatsapp(leads, dedupe_prefix="campaign_lead"):
    if not leads:
        return

    lead_rows = frappe.get_all(
        "Lead",
        filters={"name": ["in", leads]},
        fields=["name", "mobile_no", "campaign_name"],
        limit_page_length=0,
    )

    for lead in lead_rows:
        campaign_id = str(lead.campaign_name or "").strip()
        template_name = CAMPAIGN_WHATSAPP_TEMPLATE_MAP.get(campaign_id)
        if not template_name or not lead.mobile_no:
            continue

        try:
            from shoption_api.whatsapp_events import _normalize_phone, _send_via_template

            for mobile_no in _split_mobile_numbers(lead.mobile_no):
                normalized_mobile = _normalize_phone(mobile_no)
                if not normalized_mobile:
                    frappe.log_error(
                        title=f"Campaign Lead WhatsApp Skipped: {lead.name}",
                        message=f"Invalid mobile number: {mobile_no}",
                    )
                    continue

                _send_via_template(
                    template_name,
                    mobile_no,
                    CAMPAIGN_WHATSAPP_TEMPLATE_PAYLOAD.copy(),
                    f"wa:{dedupe_prefix}:{campaign_id}:{template_name}:{lead.name}:{normalized_mobile}",
                )
        except Exception:
            frappe.log_error(
                title=f"Campaign Lead WhatsApp Failed: {lead.name}",
                message=frappe.get_traceback(),
            )


def _get_next_unassigned_lead_name(campaign_name, start_of_day, end_of_day):
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabLead`
        WHERE campaign_name = %(campaign_name)s
          AND creation >= %(start)s
          AND creation < %(end)s
          AND (
                COALESCE(TRIM(`_assign`), '') = ''
                OR TRIM(`_assign`) = '[]'
              )
        ORDER BY creation ASC, name ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
        """,
        {"campaign_name": campaign_name, "start": start_of_day, "end": end_of_day},
        as_dict=True,
    )
    return rows[0].name if rows else None


def _get_last_assignee_index(campaign_name, warriors, start_of_day, end_of_day):
    """Return last assigned warrior index for today's leads in this campaign."""
    rows = frappe.db.sql(
        """
        SELECT td.allocated_to
        FROM `tabToDo` td
        INNER JOIN `tabLead` l
            ON l.name = td.reference_name
        WHERE td.reference_type = 'Lead'
          AND l.campaign_name = %(campaign_name)s
          AND l.creation >= %(start)s
          AND l.creation < %(end)s
        ORDER BY td.creation DESC, td.name DESC
        LIMIT 1
        """,
        {"campaign_name": campaign_name, "start": start_of_day, "end": end_of_day},
        as_dict=True,
    )
    if not rows:
        return -1

    try:
        return warriors.index(rows[0].allocated_to)
    except ValueError:
        return -1
