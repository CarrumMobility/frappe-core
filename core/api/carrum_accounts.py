from pydantic import BaseModel
import requests
import frappe

logger = frappe.logger("core::carrum_accounts")

class ChatwootConfigValidationSchema(BaseModel):
    token: str
    inboxId: int


def _fetch_carrum_user_data(username: str) -> dict:
    """
    GET Carrum user by Frappe username.
    Returns the `data` object from the API response, or {} if missing/invalid.
    """
    carrum_base_url = frappe.conf.get("carrum_base_url")
    carrum_token = frappe.conf.get("carrum_token")
    url = f"{carrum_base_url}/api/v1/users/by-frappe-username?username={username}"
    logger.info("Calling Carrum API for Frappe user: %s url: %s", username, url)

    response = requests.get(url, headers={"Authorization": carrum_token})
    carrum_response = response.json()
    logger.info("Carrum API response: %s", carrum_response)

    raw_data = carrum_response.get("data") if isinstance(carrum_response, dict) else None
    return raw_data if isinstance(raw_data, dict) else {}


def get_chatwoot_config_by_frappe_user(username: str):
    carrum_user = _fetch_carrum_user_data(username)
    chatwoot_config = carrum_user.get("chatwootCred")

    if not chatwoot_config:
        logger.error("No chatwoot config found for user: %s", username)
        return None

    return ChatwootConfigValidationSchema(**chatwoot_config)


def get_smartflo_account_by_frappe_user(username: str):
    # creds = {
    #     "email": "kapil.rohilla@carrum.co.in",
    #     "password": "TechTeam@12"
    # }
    return creds
    # carrum_user = _fetch_carrum_user_data(username)
    # smartflo_cred = carrum_user.get("smartfloCred")

    # if not smartflo_cred:
    #     logger.error("No smartfloCred config found for user: %s", username)
    #     return None

    # return smartflo_cred
