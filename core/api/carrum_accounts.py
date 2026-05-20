from pydantic import BaseModel
from core.services import logged_requests as requests
import frappe

logger = frappe.logger("core::carrum_accounts")

CARRUM_USER_CACHE_PREFIX = "carrum_user_data"
SMARTFLO_CACHE_PREFIX = "smartflo_user_data"
CARRUM_API_CACHE_TTL_SECONDS = 2 * 60  # 2 minutes


class ChatwootConfigValidationSchema(BaseModel):
    token: str
    inboxId: int
    agentId: int


def _carrum_user_cache_key(username: str) -> str:
    return f"{CARRUM_USER_CACHE_PREFIX}:{username}"

def _smartflo_cache_key(smartflow_external_username: str) -> str:
    return f"{SMARTFLO_CACHE_PREFIX}:{str(smartflow_external_username or '').strip()}"

def fetch_carrum_user_data_using_frappe_username(username: str) -> dict:
    """
    GET Carrum user by Frappe username.

    Returns the ``data`` object from the API response, or ``{}`` if missing/invalid.
    Cached in Redis (per Frappe user) for ``CARRUM_API_CACHE_TTL_SECONDS`` seconds via
    ``frappe.cache().set_value`` so list-view filters (which call this on every request)
    don't hammer the Carrum service.

    response format
    {'success': True, 'data': {'id': '00e1e990-1f55-4910-b1be-fd021190fae0', 'name': 'New1 null', 'userType': 'DRIVER', 'status': 'active', 'autoDialerId': None, 'did': None, 'roles': [{'id': 'ea69530e-edfd-49ff-b159-f03276614703', 'name': 'driver'}], 'hubs': [{'id': '779db382-859d-48ee-ba17-d90ffa91cf24', 'name': 'bengaluru'}], 'defaultRole': {'id': 'ea69530e-edfd-49ff-b159-f03276614703', 'name': 'driver'}, 'defaultHub': {'id': '779db382-859d-48ee-ba17-d90ffa91cf24', 'name': 'bengaluru'}, 'lastLoginIdentityId': None, 'createdAt': '2026-03-17T13:44:53.994Z', 'updatedAt': '2026-03-17T13:47:07.359Z', 'chatwootCred': {'email': 'devops@carrum.co.in', 'token': 'pgRj2VtwRZQQaHjXdz4LgCTd', 'agentId': 1, 'inboxId': 1, 'password': '56056@Abcd', 'pubSubToken': 'FzQCAWTQ29XKM7vXUb8orgh1'}, 'frappeCred': {'username': 'Administrator', 'password': None}, 'smartflowCred': None, 'isActive': True, 'incomingCallDetails': None}, 'timestamp': '2026-04-03T15:51:20.599Z'}
    """
    if not username:
        return {}

    cache_key = _carrum_user_cache_key(username)
    try:
        cached = frappe.cache().get_value(cache_key)
    except Exception:
        cached = None
    if isinstance(cached, dict):
        logger.info("Carrum user cache hit for: %s", username)
        return cached

    carrum_base_url = frappe.conf.get("carrum_base_url")
    carrum_token = frappe.conf.get("carrum_token")
    url = f"{carrum_base_url}/api/v1/users/by-external-username"
    logger.info("Calling Carrum API for Frappe user: %s url: %s", username, url)
    requestBody = {
        "username": username,
        "credentialType": "frappe"
    }
    try:
        response = requests.post(
            url,
            headers={"Authorization": carrum_token},
            json=requestBody,
            timeout=10,
        )
        carrum_response = response.json()
    except Exception:
        logger.exception("Carrum API call failed for user: %s", username)
        return {}

    logger.info("Carrum API response: %s", carrum_response)
    raw_data = carrum_response.get("data") if isinstance(carrum_response, dict) else None
    data = raw_data if isinstance(raw_data, dict) else {}

    # Cache successful lookups only — empty payloads stay un-cached so transient API
    # outages don't poison the cache for the full TTL window.
    if data:
        try:
            frappe.cache().set_value(
                cache_key, data, expires_in_sec=CARRUM_API_CACHE_TTL_SECONDS
            )
        except Exception:
            logger.exception("Failed to cache Carrum user data for: %s", username)
    return data


def invalidate_carrum_user_cache(username: str) -> None:
    """Clear the cached Carrum user payload (e.g. when hub/role changes)."""
    if not username:
        return
    try:
        frappe.cache().delete_value(_carrum_user_cache_key(username))
    except Exception:
        logger.exception("Failed to invalidate Carrum user cache for: %s", username)


def get_chatwoot_config_by_frappe_user(username: str):
    carrum_user = fetch_carrum_user_data_using_frappe_username(username)
    chatwoot_config = carrum_user.get("chatwootCred")

    if not chatwoot_config:
        logger.error("No chatwoot config found for user: %s", username)
        return None

    return ChatwootConfigValidationSchema(**chatwoot_config)


def _normalize_smartflo_cred_dict(cred) -> dict | None:
    """Return Smartflo login + dialer fields for token API and click-to-call, or None."""
    if not isinstance(cred, dict):
        return None
    print("normailze_smartflo_cred_dict==========cred==========: "+ str(cred))
    username = cred.get("username")
    password = cred.get("password") or "TechTeam@12"
    defaultCampaignId = cred.get("defaultCampaignId") or cred.get("default_campaign_id") or "442227"
    defaultCampaignName = cred.get("defaultCampaignName") or cred.get("default_campaign_name")

    if not username:
        return None
    out = {"email": username, "password": str(password), "defaultCampaignId": defaultCampaignId}
    if defaultCampaignName is not None and str(defaultCampaignName).strip():
        out["defaultCampaignName"] = str(defaultCampaignName).strip()
    calling = cred.get("callingNumber") or cred.get("calling_number")
    if calling is not None and str(calling).strip():
        out["callingNumber"] = str(calling).strip()
    ext = cred.get("extensionId") or cred.get("extension_id")
    if ext is not None and str(ext).strip():
        out["extensionId"] = str(ext).strip()
    return out


def get_smartflo_credentials_for_frappe_user(frappe_username: str):
    """
    Smartflo API login email + password for the given Frappe user.

    Uses Carrum POST `users/by-external-username` with JSON body
    ``username`` and ``credentialType: frappe``.
    and reads smartflowCred / smartfloCred from the user payload.
    """
    if not frappe_username:
        return None
    data = fetch_carrum_user_data_using_frappe_username(frappe_username)
    
    if not data:
        return None
    
    cred = data.get("smartfloCred") or data.get("smartflowCred")
    return _normalize_smartflo_cred_dict(cred)


def get_frappe_user_by_smartflo_account(smartflo_external_username: str):
    if not str(smartflo_external_username or "").strip():
        return None

    cache_key = _smartflo_cache_key(smartflo_external_username)
    try:
        cached = frappe.cache().get_value(cache_key)
    except Exception:
        cached = None

    if isinstance(cached, dict) and "frappe_user" in cached:
        return cached

    carrum_base_url = frappe.conf.get("carrum_base_url")
    carrum_token = frappe.conf.get("carrum_token")

    url = f"{carrum_base_url}/api/v1/users/by-external-username"
    try:
        requestBody = {
            "username": smartflo_external_username,
            "credentialType": "smartflow"
        }
        response = requests.post(
            url,
            headers={"Authorization": carrum_token},
            json=requestBody,
            timeout=40,
        )
        carrum_response = response.json()
    except Exception:
        logger.exception("Carrum Smartflo resolve API call failed for: %s", smartflo_external_username)
        return None
    logger.info("Carrum API response: %s", carrum_response)
    raw_data = carrum_response.get("data") if isinstance(carrum_response, dict) else None
    data = raw_data if isinstance(raw_data, dict) else {}
    frappe_cred = data.get("frappeCred")

    if not isinstance(frappe_cred, dict):
        return None
    frappe_user = str(frappe_cred.get("username") or "").strip()
    if not frappe_user:
        return None
    out = {"frappe_user": frappe_user}
    try:
        frappe.cache().set_value(
            cache_key, out, expires_in_sec=CARRUM_API_CACHE_TTL_SECONDS
        )
    except Exception:
        logger.exception("Failed to cache Smartflo→Frappe mapping for: %s", smartflo_external_username)
    return out

@frappe.whitelist()
def get_dms():
    carrum_user = fetch_carrum_user_data_using_frappe_username(frappe.session.user)
    hubId = carrum_user.get("defaultHub").get("id")
    old_carrum_base_url = frappe.conf.get("old_carrum_base_url")
    old_carrum_token = frappe.conf.get("old_carrum_token")
    url = f"{old_carrum_base_url}/api/v1/account/all?role_name=driver_manager&hub_id={hubId}"
    response = requests.get(url, headers={"Authorization": old_carrum_token})
    data = response.json()
    # data = data.get("results") or []

    return {
        "success": True,
        "data": data
    }


def _get_telecaller_by_inbox_id(inbox_id: int):
    carrum_base_url = frappe.conf.get("carrum_base_url")
    carrum_token = frappe.conf.get("carrum_token")
    url = f"{carrum_base_url}/api/v1/users/inbox/{inbox_id}"

    response = requests.get(url, headers={"Authorization": carrum_token})
    jsonData = response.json()

    return jsonData.get("data") or []

def get_users_by_inbox_id(inbox_id: int):
    data = _get_telecaller_by_inbox_id(inbox_id)
    
    data2Return = []
    for i in data:
        frappeUsername = i.get("frappeCred", {}).get("username")
        data2Return.append(frappeUsername)

    return data2Return 