import frappe
from core.services.carrum_client import old_carrum_client
from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username


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

    client = old_carrum_client(timeout=30)
    result = client.request(
        method="GET",
        path=f"/api/v1/hub/hub_details/{hubId}",
        log_tag="get-business-type-list",
    )
    if not result.get("success"):
        return {
            "success": False,
            "message": result.get("error") or "Failed to get hub details",
        }

    data = result.get("data") or {}
    responseData = data.get("results") if isinstance(data, dict) else None
    return {
        "success": True,
        "data": responseData,
    }
