"""Additional request logging helpers for API observability."""

from __future__ import annotations

import json
from typing import Any

import frappe

_DEFAULT_BODY_LIMIT = 10_000
_SECRET_KEYWORDS = ("password", "passwd", "secret", "token", "key", "pwd")
_BINARY_CONTENT_TYPES = (
	"application/octet-stream",
	"application/pdf",
	"audio/",
	"image/",
	"multipart/form-data",
	"video/",
)


def _is_api_request(request) -> bool:
	path = getattr(request, "path", "") or ""
	return path == "/api" or path.startswith("/api/")


def _request_body_limit() -> int:
	try:
		return int(getattr(frappe.local, "conf", {}).get("api_request_body_log_max_length", _DEFAULT_BODY_LIMIT))
	except Exception:
		return _DEFAULT_BODY_LIMIT


def _is_secret_key(key: Any) -> bool:
	key = str(key).lower()
	return any(secret_kw in key for secret_kw in _SECRET_KEYWORDS)


def _redact_secrets(value: Any) -> Any:
	if isinstance(value, dict):
		return {
			key: "********" if _is_secret_key(key) else _redact_secrets(item)
			for key, item in value.items()
		}
	if isinstance(value, list):
		return [_redact_secrets(item) for item in value]
	if isinstance(value, tuple):
		return tuple(_redact_secrets(item) for item in value)
	return value


def _truncate(value: str, limit: int) -> str:
	if limit <= 0 or len(value) <= limit:
		return value
	return f"{value[:limit]}... [truncated {len(value) - limit} chars]"


def _content_type(request) -> str:
	return (getattr(request, "content_type", None) or "").split(";", 1)[0].lower()


def _request_body_for_log(request) -> str:
	content_type = _content_type(request)
	if any(content_type == mime or content_type.startswith(mime) for mime in _BINARY_CONTENT_TYPES):
		return f"<{content_type or 'binary'} body omitted>"

	request_body = request.get_data(as_text=True) or ""
	if not request_body:
		return ""

	body: Any = request_body
	if getattr(request, "is_json", False):
		try:
			body = json.loads(request_body)
		except Exception:
			body = request_body
	elif content_type == "application/x-www-form-urlencoded":
		body = getattr(request, "form", None) or request_body
		if hasattr(body, "to_dict"):
			body = body.to_dict(flat=False)

	body = _redact_secrets(body)
	if isinstance(body, str):
		serialized_body = body
	else:
		serialized_body = json.dumps(body, default=str, ensure_ascii=False, separators=(",", ":"))

	return _truncate(serialized_body, _request_body_limit())


def log_api_request_body(response, request) -> None:
	"""Log the request body for API requests after the response is generated."""
	if not _is_api_request(request):
		return

	frappe.logger("frappe.web", allow_site=frappe.local.site).info(
		{
			"site": getattr(frappe.local, "site", None),
			"remote_addr": getattr(request, "remote_addr", "NOTFOUND"),
			"user": getattr(getattr(frappe.local, "session", None), "user", "NOTFOUND"),
			"base_url": getattr(request, "base_url", "NOTFOUND"),
			"full_path": getattr(request, "full_path", "NOTFOUND"),
			"method": getattr(request, "method", "NOTFOUND"),
			"http_status_code": getattr(response, "status_code", "NOTFOUND"),
			"request_body": _request_body_for_log(request),
		}
	)
