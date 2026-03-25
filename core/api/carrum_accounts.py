from pydantic import BaseModel
import requests
import frappe

logger = frappe.logger("core::carrum_accounts")
class ChatwootConfigValidationSchema(BaseModel):
    token: str
    inboxId: int

getCarrumApiHeaders = lambda apiAccessToken : {
    "api_access_token": apiAccessToken
}

def get_chatwoot_config_by_frappe_user(username: str):
    carrum_base_url = frappe.conf.carrum_base_url
    carrumToken = frappe.conf.carrum_token
    url = f"{carrum_base_url}/api/v1/users/by-frappe-username?username={username}"
    logger.info("Calling Carrum API to get chatwoot config for user: %s url: %s", username, url)

    response = requests.get(url, headers=getCarrumApiHeaders(carrumToken))
    carrum_response = response.json()
    logger.info("Carrum API response: %s", carrum_response)

    raw_data = carrum_response.get("data") if isinstance(carrum_response, dict) else None
    carrumUserData = raw_data if isinstance(raw_data, dict) else {}

    chatwootConfig = carrumUserData.get("chatwootCred")

    if not chatwootConfig:
        logger.error("No chatwoot config found for user: " + username)
        return None

    return ChatwootConfigValidationSchema(**chatwootConfig)