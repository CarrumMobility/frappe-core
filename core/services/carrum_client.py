"""Central HTTP client for Carrum portal APIs (shared base URL, auth, response framing)."""

from urllib.parse import urlencode

import json

from core.services import logged_requests as requests

import frappe
from frappe import _

logger = frappe.logger("core::carrum_client")


class CarrumHttpClient:
	"""
	Thin client around ``requests`` with explicit before/after interceptors.

	- ``intercept_before_request``: builds URL, default JSON headers, timeout envelope.
	- ``intercept_after_response``: normalizes JSON body to ``{ success, status_code, data, request_url }``.

	Network / HTTP error handling stays in ``request`` so interceptors stay pure where possible.

	``request`` enforces that ``carrum_base_url`` / ``carrum_token`` (or overrides) are set before
	any outbound call; callers do not need to repeat that check.
	"""

	def __init__(self, *, base_url=None, token=None, timeout=30):
		"""
		``base_url`` / ``token`` default to ``carrum_base_url`` / ``carrum_token`` in conf
		when omitted (``None``). Pass a value to override the default.
		"""
		resolved_base = (
			base_url if base_url is not None else (frappe.conf.get("carrum_base_url") or "")
		)
		self.base_url = resolved_base.strip().rstrip("/")
		self.token = (
			token if token is not None else frappe.conf.get("carrum_token")
		)
		self.timeout = timeout

	def _missing_carrum_config_response(self):
		"""Return a framed error if Carrum URL or auth token is missing (no request sent)."""
		if not self.base_url:
			return {
				"success": False,
				"error": _("Carrum base URL is not configured (carrum_base_url)"),
				"request_url": None,
			}
		tok = self.token
		if tok is None or not str(tok).strip():
			return {
				"success": False,
				"error": _("Carrum token is not configured (carrum_token)"),
				"request_url": None,
			}
		return None

	def intercept_before_request(
		self,
		*,
		method,
		path,
		params=None,
		headers=None,
		json=None,
		data=None,
		files=None,
	):
		"""Before-request: URL + headers + payload envelope."""
		params = params or {}
		query = urlencode(params) if params else ""
		url = f"{self.base_url}/{path.lstrip('/')}"
		if query:
			url = f"{url}?{query}"
		framed_headers = {
			"Accept": "application/json",
			"Authorization": self.token,
		}
		if headers:
			framed_headers.update(headers)
		if json is not None:
			framed_headers.setdefault("Content-Type", "application/json")
		return {
			"method": (method or "GET").upper(),
			"url": url,
			"headers": framed_headers,
			"timeout": self.timeout,
			"json": json,
			"data": data,
			"files": files,
		}

	def _send_http_request(self, req, *, log_tag="carrum"):
		"""Execute prepared request; return ``(response, None)`` or ``(None, error_dict)``."""
		url = req["url"]
		kwargs = {
			"method": req["method"],
			"url": url,
			"headers": req["headers"],
			"timeout": req["timeout"],
		}
		if req.get("json") is not None:
			kwargs["json"] = req["json"]
		if req.get("data") is not None:
			kwargs["data"] = req["data"]
		if req.get("files") is not None:
			kwargs["files"] = req["files"]

		try:
			logger.info("Executing external API request: payload=%s, url=%s", kwargs, url)
			response = requests.request(**kwargs)
		except requests.exceptions.Timeout:
			logger.error("Carrum HTTP timeout [%s] url=%s", log_tag, url)
			return None, {
				"success": False,
				"error": _("Request to referral service timed out"),
				"request_url": url,
			}
		except requests.exceptions.ConnectionError as err:
			logger.error("Carrum HTTP connection error [%s]: %s", log_tag, err)
			return None, {
				"success": False,
				"error": _("Could not connect to referral service"),
				"request_url": url,
			}
		except requests.exceptions.RequestException as err:
			logger.error("Carrum HTTP request error [%s]: %s", log_tag, err)
			return None, {
				"success": False,
				"error": _("Referral service request failed: {0}").format(str(err)),
				"request_url": url,
			}

		try:
			response.raise_for_status()
		except requests.exceptions.HTTPError as err:
			text = ""
			status = getattr(err.response, "status_code", None)
			resp = err.response
			resolved_url = getattr(resp, "url", None) or url if resp is not None else url
			if resp is not None:
				try:
					text = (resp.text or "")[:2000]
				except Exception:
					text = ""
			logger.error(
				"Carrum HTTP error [%s] status=%s body=%s",
				log_tag,
				status,
				text,
			)
			return None, {
				"success": False,
				"status_code": status,
				"error": str(err),
				"response": text or None,
				"request_url": resolved_url,
			}

		return response, None

	def _resolved_request_url(self, response, request_url):
		return getattr(response, "url", None) or request_url

	def intercept_after_response(self, response, *, request_url, log_tag="carrum"):
		"""After-response: parse body and frame ``data`` consistently."""
		resolved_url = self._resolved_request_url(response, request_url)
		if response.status_code == 204 or not (response.text or "").strip():
			return {
				"success": True,
				"status_code": response.status_code,
				"data": {},
				"request_url": resolved_url,
			}
		try:
			body = response.json()
		except ValueError:
			logger.error(
				"Carrum HTTP invalid JSON [%s] status=%s",
				log_tag,
				response.status_code,
			)
			return {
				"success": False,
				"status_code": response.status_code,
				"error": _("Invalid JSON response from referral service"),
				"response": (response.text or "")[:2000] or None,
				"request_url": resolved_url,
			}
		if isinstance(body, dict):
			# Prefer wrapped ``data`` when present; otherwise return the full JSON object.
			payload = body["data"] if "data" in body else body
		else:
			payload = body
		return {
			"success": True,
			"status_code": response.status_code,
			"data": payload,
			"request_url": resolved_url,
		}

	def request(
		self,
		*,
		method,
		path,
		params=None,
		headers=None,
		json=None,
		data=None,
		files=None,
		log_tag="carrum",
	):
		config_err = self._missing_carrum_config_response()
		if config_err is not None:
			return config_err

		req = self.intercept_before_request(
			method=method,
			path=path,
			params=params,
			headers=headers,
			json=json,
			data=data,
			files=files,
		)
		response, err = self._send_http_request(req, log_tag=log_tag)
		if err is not None:
			return err

		return self.intercept_after_response(
			response,
			request_url=req["url"],
			log_tag=log_tag,
		)

	def request_binary(
		self,
		*,
		method,
		path,
		params=None,
		headers=None,
		log_tag="carrum",
	):
		"""Like ``request`` but returns raw response bytes (e.g. PDF downloads)."""
		config_err = self._missing_carrum_config_response()
		if config_err is not None:
			return config_err

		req = self.intercept_before_request(
			method=method,
			path=path,
			params=params,
			headers=headers,
		)
		response, err = self._send_http_request(req, log_tag=log_tag)
		if err is not None:
			return err

		resolved_url = self._resolved_request_url(response, req["url"])
		content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
		return {
			"success": True,
			"status_code": response.status_code,
			"content": response.content or b"",
			"content_type": content_type,
			"request_url": resolved_url,
		}


def old_carrum_client(timeout=30):
	"""HTTP client for legacy Carrum portal APIs (``old_carrum_base_url`` / ``old_carrum_token``)."""
	return CarrumHttpClient(
		base_url=frappe.conf.get("old_carrum_base_url"),
		token=frappe.conf.get("old_carrum_token"),
		timeout=timeout,
	)


def format_carrum_api_error(message=None, *, result=None, request_url=None, response=None):
	"""Build an error message including Carrum API URL and response body."""
	if result:
		message = message or result.get("error")
		if request_url is None:
			request_url = result.get("request_url")
		if response is None:
			response = result.get("response")
	message = message or _("Request failed")
	parts = [str(message)]
	if request_url:
		parts.append(_("URL: {0}").format(request_url))
	if response is not None:
		if not isinstance(response, str):
			try:
				response = json.dumps(response, default=str)[:2000]
			except Exception:
				response = str(response)[:2000]
		parts.append(_("Response: {0}").format(response))
	return "\n".join(parts)


def throw_carrum_api_error(message=None, *, result=None, request_url=None, response=None):
	"""Raise ``frappe.throw`` with URL and response details from a client result."""
	frappe.throw(
		format_carrum_api_error(
			message,
			result=result,
			request_url=request_url,
			response=response,
		)
	)
