from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
import frappe
import requests as re

carrum_base_url = frappe.conf.get("old_carrum_base_url")
carrum_token = frappe.conf.get('old_carrum_token')
@frappe.whitelist()
def get_scheme_list():
    usr = frappe.session.user
    userData = fetch_carrum_user_data_using_frappe_username(usr)
    hubId = userData.get("defaultHub").get("id")
    if not hubId:
        return {
            "success": False
        }
    
    url = f"{carrum_base_url}/api/v1/scheme/alias?hub_id={hubId}"
    
    response = re.get(url, headers={"Authorization": carrum_token})
    return {
        "success": True,
        "data": response.json()
    }