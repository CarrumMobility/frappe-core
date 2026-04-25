import time
from core.integrations.smartflo import constants
import requests
import frappe
import core.integrations.smartflo.auth as auth
from core.services.apihit_service import api_hit_service


def _response_body_for_log(response: requests.Response):
	if response is None:
		return None
	try:
		return response.json()
	except (ValueError, TypeError):
		return response.text


def _created_by_user(user: str | None) -> str | None:
	if user and user not in (None, "Guest"):
		return user
	u = None
	if getattr(frappe.local, "session", None):
		u = frappe.session.get("user")
	return u if u and u not in (None, "Guest") else None


def _ensure_smartflo_body_success(data, context: str = ""):
	"""
	Raise if JSON body indicates failure. Some Smartflo routes return HTTP 200 with ok: false.
	"""
	if not isinstance(data, dict) or "ok" not in data:
		return
	if data.get("ok") is not False:
		return
	msg = data.get("message") or data.get("error") or frappe._("Smartflo request failed")
	meta = {k: v for k, v in data.items() if k not in ("ok", "message", "error")}
	if meta:
		msg = f"{msg} | {meta}"
	if context:
		msg = f"{context}: {msg}"
	frappe.throw(msg)


def _raise_smartflo_error(response, context: str = ""):
	"""Raise with Smartflo error message and metadata when response is {ok: False, message: '...'}."""
	try:
		data = response.json()
	except Exception:
		data = None
	if isinstance(data, dict) and data.get("ok") is False and (
		data.get("message") or data.get("error")
	):
		msg = data.get("message") or data.get("error")
		meta = {k: v for k, v in data.items() if k not in ("ok", "message", "error")}
		if meta:
			msg = f"{msg} | {meta}"
		if context:
			msg = f"{context}: {msg}"
		frappe.throw(msg)
	try:
		detail = response.json() if data is None else data
	except Exception:
		detail = response.text
	err_msg = f"Smartflo API error: {response.status_code} - {detail}"
	if context:
		err_msg = f"{context} {err_msg}"
	frappe.throw(err_msg)


def _smartflo_api_client(
	url,
	headers,
	method,
	body,
	user: str | None = None,
	isAdmin: bool = False,
	*,
	api_operation: str = "request",
):
	"""
	Execute Smartflo API with token from cache or by generating one.
	On 401, refreshes token via get_token(..., refresh=True) and retries once.
	On other errors, raises. Returns the JSON response on success.
	Each call enqueues an Api hit log (request, response, status, duration).
	"""
	t0 = time.perf_counter()
	api_name = f"Smartflo:{api_operation}"
	by_user = _created_by_user(user)

	def _request(access_token: str):
		request_headers = dict(headers or {})
		request_headers["Authorization"] = f"Bearer {access_token}"
		return requests.request(
			method=method.upper(),
			url=url,
			headers=request_headers,
			json=body,
		)

	def _emit(
		http_res,
		*,
		parsed_json=None,
		err_message: str | None = None,
	):
		try:
			elapsed = round(time.perf_counter() - t0, 4)
			sc = int(http_res.status_code) if http_res is not None else 0
			out = parsed_json
			if out is None and http_res is not None:
				out = _response_body_for_log(http_res)
			api_hit_service.enqueue_log_api_hit(
				api_name,
				str(url),
				body,
				out,
				sc,
				err_message or None,
				elapsed,
				created_by=by_user,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Smartflo api_hit enqueue")

	if isAdmin:
		adminUser = frappe.conf.get("smartflo_admin_username")
		adminPassword = frappe.conf.get("smartflo_admin_password")
		access_token = str(auth.get_admin_token(adminUser, adminPassword)).strip()
	else:
		access_token = str(auth.get_token(user)).strip()
	response = _request(access_token)

	if response.ok:
		try:
			data = response.json()
		except ValueError:
			_emit(response, parsed_json={})
			return {}
		try:
			_ensure_smartflo_body_success(data)
		except Exception as ex:  # noqa: BLE001 — log then re-raise
			_emit(response, parsed_json=data, err_message=str(ex))
			raise
		_emit(response, parsed_json=data)
		return data

	if response.status_code == 401:
		if isAdmin:
			access_token = str(auth.get_admin_token(adminUser, adminPassword, refresh=True)).strip()
		else:
			access_token = str(auth.get_token(user, refresh=True)).strip()
		response2 = _request(access_token)
		if response2.ok:
			try:
				data = response2.json()
			except ValueError:
				_emit(response2, parsed_json={})
				return {}
			try:
				_ensure_smartflo_body_success(data, context="After token refresh")
			except Exception as ex:  # noqa: BLE001
				_emit(response2, parsed_json=data, err_message=str(ex))
				raise
			_emit(response2, parsed_json=data)
			return data
		_emit(response2, err_message="After token refresh: HTTP not OK")
		_raise_smartflo_error(response2, context="After token refresh")

	_emit(response, err_message="HTTP not OK" if not response.ok else None)
	_raise_smartflo_error(response)


def handle_click2call_start_api(
	agent_number: str,
	destination_number: str,
	caller_id: str,
	custom_identifier,
	user: str,
	*,
	use_async: bool = True,
):
	"""
	When ``use_async`` is False (e.g. manual lead / callback "Dial now"), the payload
	uses ``async: 0`` so Smartflo does not use the async dial / session path that
	can tie into a separate agent "session" flow. CRM Call Session is still required
	For ``custom_identifier`` / webhooks.
	"""
	url = constants.click2call_start_config["url"]
	method = constants.click2call_start_config["method"]
	payload = {
		"async": 1 if use_async else 0,
		"agent_number": agent_number,
		"destination_number": destination_number,
		"caller_id": caller_id,
		"custom_identifier": custom_identifier
	}
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="click2call_start"
	)


def handle_click2call_end_api(*, user: str, telephony_call_id: str):
	"""
	Hang up a click-to-call leg. Smartflo expects JSON `call_id` = telephony session id
	(e.g. 1775719461.306731) — the same value stored as Call Session `agent_call_id`, not the Frappe session name.
	"""
	url = constants.click2call_end_config["url"]
	method = constants.click2call_end_config["method"]
	payload = {"call_id": (telephony_call_id or "").strip()}
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="click2call_end"
	)


def handle_get_live_call_detail_api():
	url = constants.get_live_call_detail_config["url"]
	method = constants.get_live_call_detail_config["method"]
	payload = {}
	return _smartflo_api_client(
		url, None, method, payload, user=None, isAdmin=True, api_operation="get_live_call_detail"
	)

def handle_login_session_api(user: str, campaign_id):
	url = constants.login_session_config['url']
	method = constants.login_session_config['method']
	try:
		campaign_id_int = int(str(campaign_id).strip())
	except (TypeError, ValueError):
		frappe.throw(frappe._("Invalid Smartflo campaign_id: {0}").format(campaign_id))
	payload = {
		"campaign_id": campaign_id_int,
	}
	response = _smartflo_api_client(
		url, None, method, payload, user, api_operation="login_session"
	)
	# Some Smartflo routes use "ok", others "success" (HTTP 200 body).
	result = {
		"is_valid": response.get("ok") is True or response.get("success") is True,
		"reason": None,
	}
	return result

def handle_logout(user: str, campaign_id: str):
	url = constants.agent_logout_config["url"]
	method = constants.agent_logout_config["method"]
	payload = {"campaign_id": campaign_id}
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="agent_logout"
	)


def handle_start_or_end_session_api(user: str, campaign_id: str, startOrEnd: bool):
	url = constants.session_call_config["url"]
	method = constants.session_call_config["method"]
	payload = {
		"startOrEnd": startOrEnd,
		"campaignId": campaign_id,
		"logout": True if startOrEnd == False else False,
	}
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="start_or_end_session"
	)


def handle_start_dialer_break(user: str, break_code: str | None = None):
	url = constants.start_session_break_config["url"]
	method = constants.start_session_break_config["method"]
	payload = {}
	if break_code:
		payload["break_code"] = break_code
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="start_dialer_break"
	)


def handle_end_dialer_break(user: str):
	url = constants.end_session_break_config["url"]
	method = constants.end_session_break_config["method"]
	payload = {}
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="end_dialer_break"
	)


def handle_dialer_hangup_api(user: str, call_session_id: str):
	url = constants.dialer_hangup_config["url"]
	method = constants.dialer_hangup_config["method"]
	payload = {"call_id": call_session_id}
	return _smartflo_api_client(
		url, None, method, payload, user, api_operation="dialer_hangup"
	)


def handle_store_disposition_api(user: str, call_id: str, disposition_code: str):
	url = constants.store_disposition_config['url']
	method = constants.store_disposition_config['method']
	payload = {
		"unique_id": call_id,
		"disposition_status": disposition_code,
	}
	data = _smartflo_api_client(
		url, None, method, payload, user, api_operation="store_disposition"
	)
	
	if not data.get("ok"):
		raise ValueError(data.get("reason"))

	return {"is_valid": True, "reason": None}