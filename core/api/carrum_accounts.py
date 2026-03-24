from pydantic import BaseModel
import requests
import frappe
class ChatwootConfigValidationSchema(BaseModel):
    api_access_token: str
    inbox_id: int

getCarrumApiHeaders = lambda apiAccessToken : {
    "api_access_token": apiAccessToken
}
def get_chatwoot_config_by_frappe_user(username: str):
    carrum_base_url = frappe.conf.carrum_base_url
    carrumToken = frappe.conf.carrum_token

    url = f"{carrum_base_url}/api/v2/accounts/by-frappe-user?frappe_user={username}"

    response = requests.get(url, headers=getCarrumApiHeaders(carrumToken))
    carrumUserData = response.json()

    chatwootConfig = carrumUserData.get("chatwoot_credentials")
    return ChatwootConfigValidationSchema(**chatwootConfig)