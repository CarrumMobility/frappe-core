from pydantic import BaseModel
import requests
import frappe

logger = frappe.logger("core::carrum_accounts")

class ChatwootConfigValidationSchema(BaseModel):
    token: str
    inboxId: int
    agentId: int


def fetch_carrum_user_data_using_frappe_username(username: str) -> dict:
    """
    GET Carrum user by Frappe username.
    Returns the `data` object from the API response, or {} if missing/invalid.

    response format
    {'success': True, 'data': {'id': '00e1e990-1f55-4910-b1be-fd021190fae0', 'name': 'New1 null', 'userType': 'DRIVER', 'status': 'active', 'autoDialerId': None, 'did': None, 'roles': [{'id': 'ea69530e-edfd-49ff-b159-f03276614703', 'name': 'driver'}], 'hubs': [{'id': '779db382-859d-48ee-ba17-d90ffa91cf24', 'name': 'bengaluru'}], 'defaultRole': {'id': 'ea69530e-edfd-49ff-b159-f03276614703', 'name': 'driver'}, 'defaultHub': {'id': '779db382-859d-48ee-ba17-d90ffa91cf24', 'name': 'bengaluru'}, 'lastLoginIdentityId': None, 'createdAt': '2026-03-17T13:44:53.994Z', 'updatedAt': '2026-03-17T13:47:07.359Z', 'chatwootCred': {'email': 'devops@carrum.co.in', 'token': 'pgRj2VtwRZQQaHjXdz4LgCTd', 'agentId': 1, 'inboxId': 1, 'password': '56056@Abcd', 'pubSubToken': 'FzQCAWTQ29XKM7vXUb8orgh1'}, 'frappeCred': {'username': 'Administrator', 'password': None}, 'smartflowCred': None, 'isActive': True, 'incomingCallDetails': None}, 'timestamp': '2026-04-03T15:51:20.599Z'}
    """
    carrum_base_url = frappe.conf.get("carrum_base_url")
    carrum_token = frappe.conf.get("carrum_token")
    # i/v1/users/by-external-username?credentialType=smartflow&username=kapil.roh…
    url = f"{carrum_base_url}/api/v1/users/by-external-username?credentialType=frappe&username={username}"
    # print("==========url==========")
    # print(url)
    # print("==========url==========")
    logger.info("Calling Carrum API for Frappe user: %s url: %s", username, url)

    response = requests.get(url, headers={"Authorization": carrum_token})
    carrum_response = response.json()
    logger.info("Carrum API response: %s", carrum_response)
    # print("==========carrum_response==========")
    # print(carrum_response)
    # print("==========carrum_response==========")
    raw_data = carrum_response.get("data") if isinstance(carrum_response, dict) else None
    return raw_data if isinstance(raw_data, dict) else {}


def get_chatwoot_config_by_frappe_user(username: str):
    carrum_user = fetch_carrum_user_data_using_frappe_username(username)
    chatwoot_config = carrum_user.get("chatwootCred")

    if not chatwoot_config:
        logger.error("No chatwoot config found for user: %s", username)
        return None

    return ChatwootConfigValidationSchema(**chatwoot_config)


def _normalize_smartflo_cred_dict(cred) -> dict | None:
    """Return {'email': login_id, 'password': str} for Smartflo token API, or None."""
    if not isinstance(cred, dict):
        return None
    print("normailze_smartflo_cred_dict==========cred==========: "+ str(cred)) 
    username = cred.get("username")
    password = cred.get("password") or "TechTeam@12"
    return {"email": username, "password": str(password)}


def get_smartflo_credentials_for_frappe_user(frappe_username: str):
    """
    Smartflo API login email + password for the given Frappe user.

    Uses Carrum `users/by-external-username?credentialType=frappe&username=...`
    and reads smartflowCred / smartfloCred from the user payload.
    """
    if not frappe_username:
        return None
    data = fetch_carrum_user_data_using_frappe_username(frappe_username)
    
    if not data:
        return None
    print("get_smartflo_credentials_for_frappe_user==========data==========: "+ str(data))
    cred = data.get("smartfloCred") or data.get("smartflowCred")
    return _normalize_smartflo_cred_dict(cred)


def get_frappe_user_by_smartflo_account(smartflow_external_username: str):
    """
    Resolve Frappe user id for a Smartflo-linked external id (e.g. agent email from webhooks).

    Uses Carrum `users/by-external-username?credentialType=smartflow&username=...`
    and returns frappeCred.username for realtime routing — not Smartflo login credentials.

    Returns:
        {"frappe_user": "<Frappe user name>"} or None
    """
    if not str(smartflow_external_username or "").strip():
        return None
    carrum_base_url = frappe.conf.get("carrum_base_url")
    carrum_token = frappe.conf.get("carrum_token")
    user_part = requests.utils.quote(str(smartflow_external_username).strip(), safe="")
    url = f"{carrum_base_url}/api/v1/users/by-external-username?credentialType=smartflow&username={user_part}"
    logger.info("Carrum resolve Smartflo→Frappe for external user: %s", smartflow_external_username)
    # print("get_frappe_user_by_smartflo_account==========url==========")
    # print(url)
    # print("==========url==========")
    response = requests.get(url, headers={"Authorization": carrum_token})
    carrum_response = response.json()
    logger.info("Carrum API response: %s", carrum_response)
    # print("==========carrum_response==========")
    # print(carrum_response)
    # print("==========carrum_response==========")
    raw_data = carrum_response.get("data") if isinstance(carrum_response, dict) else None
    # print("==========raw_data==========")
    # print(raw_data)
    # print("==========raw_data==========")
    data = raw_data if isinstance(raw_data, dict) else {}
    frappe_cred = data.get("frappeCred")
    # print("==========frappeCred==========")
    # print(frappe_cred)
    # print("==========frappeCred==========")

    if not isinstance(frappe_cred, dict):
        return None
    frappe_user = str(frappe_cred.get("username") or "").strip()
    if not frappe_user:
        return None
    return {"frappe_user": frappe_user}

