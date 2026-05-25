from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
import frappe
from core.services import logged_requests as re

carrum_base_url = frappe.conf.get("old_carrum_base_url")
carrum_token = frappe.conf.get('old_carrum_token')


@frappe.whitelist()
def get_scheme_list():
	payload = frappe.request.get_json() or {}
	business_type_id = str(
		payload.get("businessTypeId") or payload.get("business_type_id") or ""
	).strip()
	if not business_type_id:
		return {
			"success": False,
		}

	print("====================business_type_id===================")
	print(business_type_id)
	print("================================================")
	url = f"{carrum_base_url}/api/v1/scheme/alias?hub_id={business_type_id}"

	response = re.get(url, headers={"Authorization": carrum_token})
	return {
		"success": True,
		"data": response.json(),
	}
