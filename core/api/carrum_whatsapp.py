
from core.api.carrum_accounts import fetch_carrum_user_data_using_frappe_username
from core.services.carrum_client import CarrumHttpClient
import frappe
from core.services import logged_requests as re

# used in chatwoot services
def fetch_whatsapp_templates_against_carrum_user_id(carrum_user_id: str):
    """
    Get the list of templates from Nest Service Api against carrum user id
    """
    carrum_client = CarrumHttpClient(base_url=frappe.conf.get("carrum_base_url"), token=frappe.conf.get("carrum_token"))

    data = carrum_client.request(method="GET", path=f"api/v1/whatsapp-templates?userId={carrum_user_id}")
    return data


def get_whatsapp_templates_by_user(frappe_user: str):
    data = fetch_carrum_user_data_using_frappe_username(username=frappe_user)
    carrum_user_id = data.get("id")
    return fetch_whatsapp_templates_against_carrum_user_id(carrum_user_id=carrum_user_id)

