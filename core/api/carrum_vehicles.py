import frappe
from frappe import _

from core.services.logged_requests import logged_requests
from core.services.util_service import util_service


@frappe.whitelist()
def get_car_types():
	base_url = frappe.conf.get('old_carrum_base_url')
	token = frappe.conf.get("old_carrum_token")

	if not base_url:
		frappe.throw(_("Carrum base URL is not configured (old_carrum_base_url)"))
	if not token:
		frappe.throw(_("Carrum token is not configured (old_carrum_token)"))

	url = f"{base_url}/api/v1/fleet/car_types/all"
	headers = {"Authorization": token}
	response = logged_requests.get(url, headers=headers)
	_debug = util_service.get_api_debug_info(response)

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
			"message": message or _("Failed to fetch car types (HTTP {0})").format(response.status_code),
			"data": {"car_types": []},
			"_debug": _debug,
		}

	# Portal wraps list under a `results` key; fall back to raw body if it's already a list
	if isinstance(body, dict):
		car_types = body.get("results", body)
	elif isinstance(body, list):
		car_types = body
	else:
		car_types = []

	return {
		"is_valid": True,
		"message": _("Car types fetched successfully"),
		"data": {"car_types": car_types},
		"_debug": _debug,
	}
