"""
Authentication for Smartflo API (token get/generate).
REF: https://docs.smartflo.tatatelebusiness.com/reference/authentication-using-tokens
"""
import frappe
import requests
from core.integrations.smartflo.constants import generate_token_config

from core.api.carrum_accounts import get_smartflo_credentials_for_frappe_user

_CACHE_KEY_PREFIX = "smartflo_token"
_CACHE_TTL_SECONDS = 50 * 60  # 50 minutes


def _login(email: str, password: str) -> str:
    if not email or not password:
        frappe.throw(frappe._("Smartflo login email and password are required"))
    url = generate_token_config["url"]
    response = requests.post(
        url,
        json={"email": email, "password": password},
        timeout=30,
    )
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    if response.status_code == 200:
        access_token = data.get("access_token")
        if access_token:
            return access_token
    raise Exception(data.get("message") or f"Smartflo login failed: {response.status_code}")


def get_token(user: str, *, refresh: bool = False) -> str:
    """
    Return Smartflo access token for the given Frappe user.

    Uses a cached token when present and not expired. Pass refresh=True to drop the
    cache entry and obtain a new token (for example after HTTP 401).

    Credentials come from Carrum for this Frappe user
    (`get_smartflo_credentials_for_frappe_user`).
    """
    cache_key = f"{_CACHE_KEY_PREFIX}:{user}"
    if refresh:
        frappe.cache().delete_value(cache_key)
    else:
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached

    creds = get_smartflo_credentials_for_frappe_user(user)
    email = (creds or {}).get("email")
    password = (creds or {}).get("password")
    if not creds or not email or not password:
        frappe.throw(
            frappe._(
                "Smartflo is not configured for this user in Carrum (smartflowCred / smartfloCred is missing or incomplete). "
                "Ask an administrator to set Smartflo username and password on your Carrum user account."
            )
        )
    token = _login(email, password)
    frappe.cache().set_value(cache_key, token, expires_in_sec=_CACHE_TTL_SECONDS)
    return token

def get_admin_token(adminUser: str, adminPassword: str, refresh: bool = False) -> str:
    cache_key = f"{_CACHE_KEY_PREFIX}:{adminUser}"
    if refresh:
        frappe.cache().delete_value(cache_key)
    else:
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached
    return _login(adminUser, adminPassword)