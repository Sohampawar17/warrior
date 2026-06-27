
import frappe
from warrior.common import api_auth, api_response,get_employee_by_user,validate_method,get_global_defaults,get_print_url

# API 2: Get states
@frappe.whitelist()
def get_states(name=None):
    if not name:
        return api_response(False, "name is required")

    rows = frappe.get_list(
        "Territory",
        filters={"custom_country": name},   # LINK FIELD to Country
        fields=["name as id", "territory_name as name"],
        order_by="territory_name asc"
    )

    return api_response(True, "States fetched", rows)



# API 3: Districts
@frappe.whitelist()
def get_districts(state_id=None):
    if not state_id:
        return api_response(False, "state_id is required")

    rows = frappe.get_list(
        "District",
        filters={"state": state_id},
        fields=["name as id", "district_name as name"],
        order_by="district_name asc"
    )

    return api_response(True, "Districts fetched", rows)


# API 4: Tahshils
@frappe.whitelist()
def get_tahsils(district_id=None):
    if not district_id:
        return api_response(False,  "district_id is required")

    rows = frappe.get_list(
        "Tahshil",
        filters={"district": district_id},
        fields=["name as id", "tahshil as name"],
        order_by="tahshil asc"
    )

    return api_response(True, "Tahshils fetched", rows)

# API 5: Marketplaces
@frappe.whitelist()
def get_marketplaces(tehsil_id=None):
    if not tehsil_id:
        return api_response(False, "tehsil_id is required")

    # since Tehsil ID = DocName
    tehsil_name = tehsil_id

    rows = frappe.get_list(
        "Marketplace",
        filters={"tahshil": tehsil_name, "status": "Approved"},
        fields=["name as id", "marketplace_name as name"],
        order_by="marketplace_name asc"
    )

    return api_response(True, "Marketplaces fetched", rows)
