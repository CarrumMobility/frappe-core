import json

import requests
from frappe import _

import frappe
from core.api.carrum_accounts import (
    fetch_carrum_user_data_using_frappe_username,
)

logger = frappe.logger("core::carrum_config")

configs = {
    "hubFeeConfig": "HUB_FEE_CONFIG",
    "smartfloCampaignList": "SMARTFLO_CAMPAIGN_LIST",
}


def _carrum_config_url_for_key(key: str) -> str:
    base = frappe.conf.get("carrum_base_url")
    if not base:
        frappe.throw(_("Carrum base URL is not configured (carrum_base_url)"))
    return f"{str(base).rstrip('/')}/api/v1/config/key/{key}"


def _fetch_carrum_config_by_key(key: str) -> dict:
    """
    GET Carrum config by key. Plain Python (no frappe.request); safe to call from
    other whitelisted methods without losing the key argument.
    """
    if not key or not str(key).strip():
        frappe.throw(_("Key is required"))
    key = str(key).strip()

    token = frappe.conf.get("carrum_token")
    if not token:
        frappe.throw(_("Carrum token is not configured (carrum_token)"))

    url = _carrum_config_url_for_key(key)
    headers = {"Authorization": token}

    try:
        res = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        logger.exception("Carrum config request failed for key=%s url=%s", key, url)
        frappe.throw(_("Could not reach Carrum config API: {0}").format(str(e)))

    if res.status_code >= 400:
        body = (res.text or "")[:500]
        logger.warning(
            "Carrum config API HTTP %s for key=%s: %s",
            res.status_code,
            key,
            body or res.reason,
        )
        frappe.throw(
            _("Carrum config API error ({0}): {1}").format(
                res.status_code,
                body or res.reason,
            )
        )

    try:
        value = res.json()
    except ValueError:
        logger.warning("Non-JSON Carrum config response for key=%s", key)
        frappe.throw(_("Invalid JSON from Carrum config API"))

    if not isinstance(value, dict):
        frappe.throw(_("Unexpected Carrum config response shape"))

    logger.info("getCarrumConfigByKey(%s): %s", key, json.dumps(value, default=str))
    return value


@frappe.whitelist()
def getConfigByKey(key: str | None = None):
    """Whitelisted: resolve key from argument, JSON body, or form_dict, then fetch."""
    data = frappe.request.get_json(silent=True) or {}
    resolved = key or data.get("key") or frappe.form_dict.get("key")
    args = data.get("args")
    if not resolved and isinstance(args, (list, tuple)) and args:
        resolved = args[0]
    return _fetch_carrum_config_by_key(resolved)

@frappe.whitelist()
def getHubFeeConfig() -> dict:
    user = frappe.session.user
    carrum_user = fetch_carrum_user_data_using_frappe_username(user)
    print("==========carrum_user==========")
    print(carrum_user)
    print("==========carrum_user==========")
    default_hub = carrum_user.get("defaultHub")
    default_hub_id = default_hub.get("id") if default_hub is not None else None

    hub_key = configs.get("hubFeeConfig")
    data = _fetch_carrum_config_by_key(hub_key)

    hub_fee_config = data.get("data") if isinstance(data, dict) else None

    val_root = (hub_fee_config or {}).get("value")
    if not isinstance(val_root, dict):
        return {"fee": []}

    value = val_root.get(default_hub_id) if default_hub_id else None
    if value is None:
        return {"fee": []}
    if not isinstance(value, list):
        return {"fee": [value]}

    return {"fee": value}


@frappe.whitelist(allow_guest=True)
def getCarrumUserData() -> dict:
	user = frappe.session.user
	# carrum_user = fetch_carrum_user_data_using_frappe_username("admin")
	print(
		"----------user1--------------",
		user,
		"----------user1--------------",
	)
	print(
		"----------user2--------------",
		frappe.session,
		"----------user2--------------",
	)
	carrum_user = fetch_carrum_user_data_using_frappe_username(user)
	print("carrum_user", carrum_user, "frappeUser", frappe.session)
	return {"success": True, "data": carrum_user}