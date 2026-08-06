from __future__ import annotations

import json
from datetime import date, datetime

import frappe
import requests

_REDIS_KEY_PREFIX = "olx_auth"
_REDIS_KEY_TTL = 14 * 60  # token valid 15 minutes; refresh slightly early
_DEFAULT_API_VERSION = "134"


class OlxApiError(Exception):
	def __init__(self, message: str, *, status_code: int | None = None, response_body=None):
		super().__init__(message)
		self.status_code = status_code
		self.response_body = response_body


def get_olx_error_message(response_body, fallback: str = "") -> str:
	"""Extract a human-readable message from an OLX API error payload."""
	if not response_body:
		return fallback

	body = response_body
	if isinstance(body, str):
		try:
			body = json.loads(body)
		except json.JSONDecodeError:
			return body or fallback

	if isinstance(body, dict):
		return (
			str(body.get("localized_message") or "").strip()
			or str(body.get("message") or "").strip()
			or fallback
		)

	return fallback


class OlxClient:
	"""Thin HTTP wrapper for the OLX Dealer Lead Sharing API."""

	def __init__(
		self,
		username: str,
		password: str,
		*,
		base_url: str | None = None,
		api_version: str = _DEFAULT_API_VERSION,
	):
		self.username = (username or "").strip()
		self.password = password or ""
		if not self.username or not self.password:
			frappe.throw(frappe._("OLX username and password are required"))

		self.api_version = api_version
		self.base_url = str(base_url or frappe.conf.get("olx_base_url") or "https://business.olx.in").rstrip(
			"/"
		)

	def login(self) -> tuple[str, str]:
		"""Authenticate and return ``(access_token, user_id)``."""
		cached = self._get_cached_auth()
		if cached:
			return cached

		url = f"{self.base_url}/api/v1/auth/login"
		headers = {
			"Content-Type": "text/plain",
			"client-language": "en-IN",
			"Api-Version": self.api_version,
		}
		payload = {"login": self.username, "password": self.password}

		response = requests.post(url, headers=headers, json=payload, timeout=60)
		if response.status_code == 403:
			self.clear_auth_cache()
		if not response.ok:
			raise OlxApiError(
				frappe._("OLX login failed: {0}").format(response.text),
				status_code=response.status_code,
				response_body=_safe_json(response),
			)

		data = response.json() or {}
		access_token = (data.get("access_token") or "").strip()
		user_id = str(data.get("user_id") or "").strip()
		if not access_token or not user_id:
			raise OlxApiError(frappe._("OLX login response missing access_token or user_id"))

		self._set_cached_auth(access_token, user_id)
		return access_token, user_id

	def get_leads(
		self,
		*,
		start_date: date | datetime | str,
		end_date: date | datetime | str,
		page: int = 1,
		page_size: int = 100,
		ad_ids: list[str] | None = None,
	) -> dict:
		"""Fetch one page of leads. Returns parsed API payload fields only."""
		start = _format_api_date(start_date)
		end = _format_api_date(end_date)
		page_size = min(max(int(page_size or 20), 1), 100)

		return self._request_leads_page(
			start_date=start,
			end_date=end,
			page=page,
			page_size=page_size,
			ad_ids=ad_ids,
			retry_on_auth_failure=True,
		)

	def clear_auth_cache(self) -> None:
		frappe.cache().delete_value(self._redis_key())

	def _request_leads_page(
		self,
		*,
		start_date: str,
		end_date: str,
		page: int,
		page_size: int,
		ad_ids: list[str] | None,
		retry_on_auth_failure: bool,
	) -> dict:
		access_token, user_id = self.login()
		url = f"{self.base_url}/api/v1/leads"
		headers = {
			"Authorization": f"Bearer {access_token}",
			"Client-Language": "en-in",
			"Api-Version": self.api_version,
		}
		params: dict = {
			"startDate": start_date,
			"endDate": end_date,
			"userId": user_id,
			"page": page,
			"pageSize": page_size,
		}
		if ad_ids:
			params["adIds"] = ad_ids

		response = requests.get(url, headers=headers, params=params, timeout=60)

		if response.status_code == 403 and retry_on_auth_failure:
			self.clear_auth_cache()
			return self._request_leads_page(
				start_date=start_date,
				end_date=end_date,
				page=page,
				page_size=page_size,
				ad_ids=ad_ids,
				retry_on_auth_failure=False,
			)

		if response.status_code == 404:
			return {
				"leads": [],
				"ads": [],
				"pagination": {
					"page": page,
					"pageSize": page_size,
					"totalPages": 0,
					"totalRecords": 0,
				},
				"raw": _safe_json(response),
			}

		if not response.ok:
			raise OlxApiError(
				frappe._("OLX get leads failed: {0}").format(response.text),
				status_code=response.status_code,
				response_body=_safe_json(response),
			)

		raw = response.json() or {}
		data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
		return {
			"leads": (data or {}).get("leads") or [],
			"ads": (data or {}).get("ads") or [],
			"pagination": raw.get("pagination") or (data or {}).get("pagination") or {},
			"raw": raw,
		}

	def _redis_key(self) -> str:
		return f"{_REDIS_KEY_PREFIX}:{self.username}"

	def _get_cached_auth(self) -> tuple[str, str] | None:
		raw = frappe.cache().get_value(self._redis_key())
		if not raw:
			return None
		if isinstance(raw, bytes):
			raw = raw.decode()
		if isinstance(raw, str):
			try:
				raw = json.loads(raw)
			except json.JSONDecodeError:
				return None
		if not isinstance(raw, dict):
			return None
		token = str(raw.get("access_token") or "").strip()
		user_id = str(raw.get("user_id") or "").strip()
		return (token, user_id) if token and user_id else None

	def _set_cached_auth(self, access_token: str, user_id: str) -> None:
		frappe.cache().set_value(
			self._redis_key(),
			json.dumps({"access_token": access_token, "user_id": user_id}),
			expires_in_sec=_REDIS_KEY_TTL,
		)


def _format_api_date(value: date | datetime | str) -> str:
	"""Format values for OLX ``startDate`` / ``endDate`` query params."""
	if isinstance(value, datetime):
		return value.strftime("%Y-%m-%d")
	if isinstance(value, date):
		return value.isoformat()
	text = str(value or "").strip()
	if not text:
		frappe.throw(frappe._("OLX date range requires startDate and endDate"))
	# Drop time component when a datetime string is passed through.
	if " " in text:
		text = text.split(" ", 1)[0]
	if "T" in text:
		text = text.split("T", 1)[0]
	return text


def _safe_json(response: requests.Response):
	try:
		return response.json()
	except ValueError:
		return {"raw": response.text}
