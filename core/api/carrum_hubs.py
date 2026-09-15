import frappe
from frappe import _

from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
from core.services import logged_requests as re
from core.services.util_service import util_service

logger = frappe.logger("core::carrum_hubs")

@frappe.whitelist()
def get_business_type_list():
    usr = frappe.session.user
    userData = fetch_carrum_user_data_using_frappe_username(usr)

    if not userData:
        return {
            "success": False,
            "message": "Carrum user data not found"
        }

    default_hub = userData.get("defaultHub") or {}
    hubId = default_hub.get("id")
    if not hubId:
        return {
            "success": False,
            "message": "Carrum hub id not found"
        }

    base_url = frappe.conf.get("old_carrum_base_url")
    token = frappe.conf.get("old_carrum_token")
    url = f"{base_url}/api/v1/hub/hub_details/{hubId}"
    response = re.get(url, headers={"Authorization": token})
    if not response.ok:
        return {
            "success": False,
            "message": "Failed to get hub details"
        }

    data = response.json()
    responseData = data.get('results')
    return {
        "success": True,
        "data": responseData
    }

@frappe.whitelist()
def get_satellite_hubs(hub_id: str | None = None, lsq_id: str | None = None):
    """``hub_id`` is optional; when provided it filters to that hub's satellites."""
    base_url = frappe.conf.get("old_carrum_base_url")
    token = frappe.conf.get("old_carrum_token")
    if lsq_id:
        logger.info(f"get_satellite_hubs: lsq_id: {lsq_id}")

    if not base_url:
        frappe.throw(_("Carrum base URL is not configured (old_carrum_base_url)"))
    if not token:
        frappe.throw(_("Carrum token is not configured (old_carrum_token)"))

    url = f"{base_url}/api/v1/hub/satellite"
    params = {
        "limit": 1000,
        "page": 1
    }

    if hub_id and str(hub_id).strip():
        params["hub_id"] = str(hub_id).strip()

    response = re.get(url, params=params, headers={"Authorization": token})

    try:
        body = response.json()
    except ValueError:
        body = {}

    if not response.ok:
        message = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error")
        return {
            "is_valid": False,
            "message": message or _("Failed to get satellite hubs (HTTP {0})").format(response.status_code),
            "data": {},
        }

    debug_info = util_service.get_api_debug_info(response)

    results = body.get('results')
    return {
        "is_valid": True,
        "message": _("Satellite hubs fetched successfully"),
        "data": results,
        "_debug": debug_info,
    }
