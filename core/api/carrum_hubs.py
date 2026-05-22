import frappe
from core.services import logged_requests as re
from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username

carrum_base_url = frappe.conf.get("old_carrum_base_url")
carrum_token = frappe.conf.get("old_carrum_token")

@frappe.whitelist()
def get_business_type_list():
    usr = frappe.session.user
    userData = fetch_carrum_user_data_using_frappe_username(usr)

    if not userData:
        return {
            "success": False,
            "message": "Carrum user data not found"
        }

    hubId = userData.get("defaultHub").get("id")
    if not hubId:
        return {
            "success": False,
            "message": "Carrum hub id not found"
        }

    hubId = hubId

    url = f"{carrum_base_url}/api/v1/hub/hub_details/{hubId}"
    response = re.get(url, headers={"Authorization": carrum_token})
    if not response.ok:
        return {
            "success": False,
            "message": "Failed to get hub details"
        }

    data = response.json()
    responseData = data['results']
    return {
        "success": True,
        "data": responseData
    }