import frappe
from frappe.utils import get_datetime, nowdate,flt,cint
from frappe.utils.file_manager import save_file
from warrior.common import api_auth, api_response,get_employee_by_user
from frappe.handler import upload_file

@frappe.whitelist()
def punch_employee(
    log_type=None,
    custom_today_agenda=None,
    custom_enter_km=None
):
    
    if log_type not in ["IN", "OUT"]:
        return api_response(False, "log_type must be IN or OUT")

    # -------------------------------
    # RESOLVE EMPLOYEE
    # -------------------------------
    employee = get_employee_by_user(frappe.session.user, "name")
    if not employee:
        return api_response(False, "No employee linked with this user")

    # -------------------------------
    # PUNCH SEQUENCE CHECK
    # -------------------------------
    last_checkin = frappe.get_all(
        "Employee Checkin",
        filters={"employee": employee.get("name"),
                         "time": ["between", [f"{nowdate()} 00:00:00", f"{nowdate()} 23:59:59"]]
},
        fields=["log_type"],
        order_by="time desc",
        limit=1
    )

    if log_type == "IN" and last_checkin and last_checkin[0].log_type == "IN":
        return api_response(False, "Employee already punched IN")

    if log_type == "OUT":
        if not last_checkin:
            return api_response(False, "No punch IN found for employee")
        if last_checkin[0].log_type == "OUT":
            return api_response(False, "Employee already punched OUT")

    checkin = frappe.new_doc("Employee Checkin")
    checkin.employee = employee
    checkin.log_type = log_type
    checkin.custom_today_agenda = custom_today_agenda
    checkin.custom_enter_km = custom_enter_km
    checkin.insert(ignore_permissions=True)
    # -------------------------------
    # SAVE KM PHOTO (OPTIONAL)
    selfie = attach_file(
        fieldname="custom_upload_selfie",
        doctype="Employee Checkin",
        docname=checkin.name
    )
    if selfie:
        checkin.custom_upload_selfie = selfie

    km_photo = attach_file(
        fieldname="custom_km_photo",
        doctype="Employee Checkin",
        docname=checkin.name
    )
    if km_photo:
        checkin.custom_km_photo = km_photo

    checkin.save(ignore_permissions=True)
    frappe.db.commit()

    return api_response(
        True,
        f"Punch {log_type} successful",
        {
            "checkin_id": checkin.name,
            "employee": employee.get("name"),
            "user_id": frappe.session.user,
            "log_type": log_type,
            "selfie": selfie,
            "km_photo": km_photo,
            "time": checkin.time
        }
    )

def attach_file(fieldname, doctype, docname):
    filename="selfie" if fieldname=="custom_upload_selfie" else "km_photo"
    uploaded_file = frappe.request.files.get(filename)
    if not uploaded_file:
        return None

    if not frappe.has_permission(doctype, "write", docname):
        frappe.throw("Not permitted")

    file_doc = save_file(
        fname=uploaded_file.filename,
        content=uploaded_file.stream.read(),
        dt=doctype,
        dn=docname,
        df=fieldname,
        is_private=0
    )

    return file_doc.file_url

# # import frappe
# # from frappe.utils import get_datetime, nowdate
# # from warrior.common import api_auth, api_response, require_post
@frappe.whitelist()
def get_today_punch_status():
    employee = get_employee_by_user(frappe.session.user, "name")
    if not employee:
        return api_response(False, "No employee linked with this user")

    today_start = frappe.utils.now_datetime().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_end = frappe.utils.add_days(today_start, 1)

    today_checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": employee.get("name"),
            "time": ["between", [today_start, today_end]]
        },
        fields=["log_type", "time"],
        order_by="time asc"
    )

    punch_in_time = None
    punch_out_time = None

    for c in today_checkins:
        if c.log_type == "IN" and punch_in_time is None:
            punch_in_time = c.time
        elif c.log_type == "OUT":
            punch_out_time = c.time  # always keep last OUT

    today_in = punch_in_time is not None
    today_out = punch_out_time is not None

    return api_response(
        True,
        "Today's punch status fetched",
        {
            "today_punch_in": today_in,
            "today_punch_in_time": punch_in_time,
            "today_punch_out": today_out,
            "today_punch_out_time": punch_out_time,
            "can_punch_in": not today_in,
            "can_punch_out": today_in and not today_out
        }
    )



@frappe.whitelist()
def get_attendance_list(from_date=None, to_date=None, page=1, page_size=30):
    try:
        if not from_date:
            from_date = nowdate()
        if not to_date:
            to_date = nowdate()
        emp_data = get_employee_by_user(frappe.session.user)
        present_count = 0
        absent_count = 0
        late_count = 0
        halfday_count=0
        onleave_count=0
        page = cint(page) or 1
        page_size = cint(page_size) or 30
        start = (page - 1) * page_size

        employee_attendance_list = frappe.get_all(
            "Attendance",
            filters={
                "employee": emp_data.get("name"),
                "docstatus":1,
                "attendance_date": [
                    "between",
                    [
                        from_date,
                        to_date
                    ],
                ],
            },
            fields=[
                "name",
                "attendance_date",
                "status",
                "working_hours",
                "time_format(in_time, '%h:%i%p') as in_time",
                "time_format(out_time, '%h:%i%p') as out_time",
                "late_entry",
            ],
            order_by="attendance_date desc",
            limit_start=start,
            limit_page_length=page_size,
        )

        if not employee_attendance_list:
            return api_response(False, "No attendance found for this date range", [])

        for attendance in employee_attendance_list:
            employee_checkin_details = frappe.get_all(
                "Employee Checkin",
                filters={"attendance": attendance.get("name")},
                fields=["log_type", "time_format(time, '%h:%i%p') as time"],
            )

            attendance["employee_checkin_detail"] = employee_checkin_details

            if attendance["status"] == "Present":
                present_count += 1

                if attendance["late_entry"] == 1:
                    late_count += 1

            elif attendance["status"] == "Absent":
                absent_count += 1
            
            elif attendance["status"] == "Half Day":
                halfday_count += 1
            
            elif attendance["status"] == "On Leave":
                onleave_count += 1

            del attendance["name"]
            # del attendance["status"]
            del attendance["late_entry"]

        attendance_details = {
            "present": present_count,
            "absent": absent_count,
            "late": late_count,
            "half day":halfday_count,
            "on leave":onleave_count
        }
        total_records = frappe.db.count("Attendance", filters={"employee": emp_data.get("name")})
        total_pages = (total_records + page_size - 1) // page_size

        attendance_data = {
            "total": total_records,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "attendance_details": attendance_details,
            "attendance_list": employee_attendance_list
           
        }
        return api_response(
            True, "Attendance data getting Successfully", attendance_data
        )

    except Exception as e:
        return api_response(False, str(e), [])
