"""
Authentication for Smartflo API (token get/generate).
REF: https://docs.smartflo.tatatelebusiness.com/reference/authentication-using-tokens
"""
import time

import frappe
from core.services import logged_requests as requests

from core.integrations.smartflo.constants import generate_token_config
from core.api.carrum_accounts import get_smartflo_credentials_for_frappe_user
from core.services.apihit_service import api_hit_service

_CACHE_KEY_PREFIX = "smartflo_token"
_CACHE_TTL_SECONDS = 50 * 60  # 50 minutes


def _session_user_for_log(explicit: str | None = None) -> str | None:
	if explicit and explicit not in (None, "Guest"):
		return explicit
	if getattr(frappe.local, "session", None):
		u = frappe.session.get("user")
		if u and u not in (None, "Guest"):
			return u
	return None


def _req_headers(res: requests.Response | None) -> dict | None:
	if res is None or not getattr(res, "request", None):
		return None
	try:
		return dict(res.request.headers)
	except (TypeError, ValueError):
		return None


def _emit_token_api_hit(
	url: str,
	headers: dict | None,
	request_log: object,
	response_log: object,
	status_code: int,
	err_message: str | None,
	elapsed_s: float,
	created_by: str | None,
	log_op: str,
) -> None:
	try:
		api_hit_service.enqueue_log_api_hit(
			f"Smartflo:{log_op}",
			str(url),
			headers,
			request_log,
			response_log,
			int(status_code),
			err_message or None,
			round(elapsed_s, 4),
			created_by=created_by,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Smartflo token api_hit enqueue")


def _login(
	email: str,
	password: str,
	*,
	created_by: str | None = None,
	log_op: str = "token_user",
) -> str:
	"""POST /v1/auth/login. Api hit log stores the same request/response bodies as sent/received."""
	if not email or not password:
		frappe.throw(frappe._("Smartflo login email and password are required"))
	url = generate_token_config["url"]
	t0 = time.perf_counter()
	request_body = {"email": email, "password": password}

	response = requests.post(
		url,
		json=request_body,
		timeout=30,
	)
	elapsed = time.perf_counter() - t0
	sc = int(response.status_code)

	if response.headers.get("content-type", "").startswith("application/json"):
		try:
			data = response.json() if response.content else {}
		except ValueError:
			data = None
	else:
		data = None

	if sc == 200 and isinstance(data, dict):
		access_token = data.get("access_token")
		if access_token:
			_emit_token_api_hit(
				url,
				_req_headers(response),
				request_body,
				data,
				sc,
				None,
				elapsed,
				created_by,
				log_op,
			)
			return access_token

	err_text = None
	if isinstance(data, dict):
		err_text = data.get("message")
	resp_log: object
	if data is not None:
		resp_log = data
	else:
		resp_log = response.text
	_emit_token_api_hit(
		url,
		_req_headers(response),
		request_body,
		resp_log,
		sc,
		err_text or f"Smartflo login failed: {sc}",
		elapsed,
		created_by,
		log_op,
	)
	msg = data.get("message") if isinstance(data, dict) else None
	raise Exception(msg or f"Smartflo login failed: {sc}")


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

	print("====user=== start")
	print(user)
	print("====user=== end")
	creds = get_smartflo_credentials_for_frappe_user(user)
	email = (creds or {}).get("email")
	password = (creds or {}).get("password")
	print(email, password)
	if not creds or not email or not password:
		frappe.throw(
			frappe._(
				"Smartflo is not configured for this user in Carrum (smartflowCred / smartfloCred is missing or incomplete). "
				"Ask an administrator to set Smartflo username and password on your Carrum user account."
			)
		)
	token = _login(email, password, created_by=user, log_op="token_user")
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
	created = _session_user_for_log()
	return _login(
		adminUser,
		adminPassword,
		created_by=created,
		log_op="token_admin",
	)
