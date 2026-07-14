from core.constants.enums import EnumValues
from pydantic import BaseModel
from core.services.carrum_client import CarrumHttpClient, old_carrum_client
import frappe
from frappe import _

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
    logger.info(
        "Calling Carrum API for Frappe user: %s url: %s/api/v1/users/by-external-username",
        username,
        carrum_base_url,
    )
    client = CarrumHttpClient(timeout=10)
    result = client.request(
        method="POST",
        path="/api/v1/users/by-external-username",
        json={"username": username, "credentialType": "frappe"},
        log_tag="carrum-user-by-frappe-username",
    )
    if not result.get("success"):
        logger.error(
            "Carrum API call failed for user: %s url=%s error=%s response=%s",
            username,
            result.get("request_url"),
            result.get("error"),
            result.get("response"),
        )
        return {}

    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    logger.info("Carrum API response data for %s: %s", username, data)

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
    """Return Smartflo login + dialer fields for token API and agent calling, or None."""
    if not isinstance(cred, dict):
        return None
    # print("normailze_smartflo_cred_dict==========cred==========: "+ str(cred))
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

    client = CarrumHttpClient(timeout=40)
    result = client.request(
        method="POST",
        path="/api/v1/users/by-external-username",
        json={
            "username": smartflo_external_username,
            "credentialType": "smartflow",
        },
        log_tag="carrum-user-by-smartflo-username",
    )
    if not result.get("success"):
        logger.error(
            "Carrum Smartflo resolve API call failed for: %s url=%s error=%s response=%s",
            smartflo_external_username,
            result.get("request_url"),
            result.get("error"),
            result.get("response"),
        )
        return None

    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    logger.info("Carrum API response: %s", data)
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
    client = old_carrum_client(timeout=30)
    result = client.request(
        method="GET",
        path="/api/v1/account/all",
        params={"role_name": "driver_manager", "hub_id": hubId},
        log_tag="get-dms",
    )
    if not result.get("success"):
        frappe.throw(str(result.get("error") or _("Failed to fetch driver managers")))
    return {
        "success": True,
        "data": result.get("data"),
    }


def _get_telecaller_by_inbox_id(inbox_id: int):
    client = CarrumHttpClient(timeout=20)
    result = client.request(
        method="GET",
        path=f"/api/v1/users/inbox/{inbox_id}",
        log_tag="telecaller-by-inbox-id",
    )
    if not result.get("success"):
        return []
    data = result.get("data")
    return data if isinstance(data, list) else []

def get_users_by_inbox_id(inbox_id: int):
    data = _get_telecaller_by_inbox_id(inbox_id)
    
    data2Return = []
    for i in data:
        frappeUsername = i.get("frappeCred", {}).get("username")
        data2Return.append(frappeUsername)

    return data2Return 

def get_hub_telecallers(hub_id: str):
    client = CarrumHttpClient(timeout=20)
    result = client.request(
        method="GET",
        path="/api/v1/users",
        params={
            "hubId": hub_id,
            "limit": 100,
            "roleName": EnumValues.Roles.TELECALLER.lower(),
        },
        log_tag="hub-telecallers",
    )
    if not result.get("success"):
        return {}
    return result.get("data") or {}


def _carrum_user_rows(payload):
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("results") or payload.get("users") or payload.get("items")
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("results") or rows.get("users") or rows.get("items")
    else:
        rows = payload
    return rows if isinstance(rows, list) else []


def get_hub_telecaller_usernames(hub_id: str) -> list[str]:
    data = get_hub_telecallers(hub_id)
    usernames = []
    for user in _carrum_user_rows(data):
        if not isinstance(user, dict):
            continue
        frappe_cred = user.get("frappeCred") or user.get("frappe_cred") or {}
        username = ""
        if isinstance(frappe_cred, dict):
            username = frappe_cred.get("username") or frappe_cred.get("userName") or ""
        username = (username or "").strip()
        if username:
            usernames.append(username)
    return list(dict.fromkeys(usernames))


def get_hub_telecaller_users(hub_id: str) -> list[dict]:
    """Return Carrum hub telecaller user rows (id, frappeCred, etc.)."""
    return [
        row
        for row in _carrum_user_rows(get_hub_telecallers(hub_id))
        if isinstance(row, dict)
    ]


def _carrum_user_role_name(user_row: dict) -> str:
    if not isinstance(user_row, dict):
        return ""
    default_role = user_row.get("defaultRole") or {}
    if isinstance(default_role, dict):
        role_name = (default_role.get("name") or "").strip()
        if role_name:
            return role_name
    roles = user_row.get("roles") or []
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict):
                role_name = (role.get("name") or "").strip()
                if role_name:
                    return role_name
    return ""


def _carrum_user_frappe_username(user_row: dict) -> str:
    if not isinstance(user_row, dict):
        return ""
    frappe_cred = user_row.get("frappeCred") or user_row.get("frappe_cred") or {}
    if not isinstance(frappe_cred, dict):
        return ""
    return (frappe_cred.get("username") or frappe_cred.get("userName") or "").strip()


def resolve_carrum_user_id_to_frappe_username(
    carrum_user_id: str, hub_id: str | None = None
) -> str:
    """Map a Carrum user UUID to an enabled Frappe username within a hub."""
    carrum_user_id = (carrum_user_id or "").strip()
    if not carrum_user_id:
        return ""
    if frappe.db.exists("User", {"name": carrum_user_id, "enabled": 1}):
        return carrum_user_id

    hub_id = (hub_id or "").strip()
    if not hub_id:
        return ""

    for row in get_hub_active_users(hub_id):
        if (row.get("id") or "").strip() != carrum_user_id:
            continue
        username = _carrum_user_frappe_username(row)
        if username and frappe.db.exists("User", {"name": username, "enabled": 1}):
            return username
    return ""


def fetch_hub_active_users(
    hub_id: str, role_name: str | None = None, limit: int = 200
) -> dict:
    """Fetch active Carrum users for a hub via the portal API (framed response)."""
    hub_id = (hub_id or "").strip()
    if not hub_id:
        return {
            "success": False,
            "error": _("Hub id is required"),
            "request_url": None,
        }

    query_params = {
        "hubId": hub_id,
        "limit": limit,
        "status": "active",
    }
    if role_name:
        query_params["roleName"] = role_name

    client = CarrumHttpClient(timeout=20)
    result = client.request(
        method="GET",
        path="/api/v1/users",
        params=query_params,
        log_tag="hub-active-users",
    )
    if not result.get("success"):
        return result

    rows = [
        row for row in _carrum_user_rows(result.get("data")) if isinstance(row, dict)
    ]
    return {**result, "data": rows}


def get_hub_active_users(hub_id: str, role_name: str | None = None, limit: int = 200) -> list[dict]:
    """Return active Carrum users for a hub, optionally filtered by role."""
    result = fetch_hub_active_users(hub_id, role_name=role_name, limit=limit)
    if not result.get("success"):
        return []
    return result.get("data") or []

def get_dm_of_all_businessTypes(hubId: str):
    client = old_carrum_client(timeout=30)
    result = client.request(
        method="GET",
        path="/api/v1/account/driver_manager_for_frappe",
        params={"hubId": hubId},
        log_tag="get-dm-for-hub",
    )
    if not result.get("success"):
        frappe.throw(str(result.get("error") or _("Failed to fetch driver managers")))
    return result.get("data")