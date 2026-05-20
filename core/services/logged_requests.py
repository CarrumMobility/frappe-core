import requests as _requests
import frappe


logger = frappe.logger("core.services.logged_requests")

exceptions = _requests.exceptions
RequestException = _requests.RequestException
utils = _requests.utils


def _request_body_from_kwargs(kwargs: dict):
	if "json" in kwargs:
		return kwargs.get("json")
	if "data" in kwargs:
		return kwargs.get("data")
	if "params" in kwargs:
		return {"params": kwargs.get("params")}
	if "files" in kwargs:
		files = kwargs.get("files") or {}
		if isinstance(files, dict):
			return {"files": list(files.keys())}
		return {"files": True}
	return None


def _log_api_request(method: str, url: str, request_body, response_status=None, exception=None):
	payload = {
		"message": "External API request",
		"method": (method or "").upper(),
		"url": url,
		"request_body": request_body,
		"response_status": response_status,
	}
	if exception:
		payload["exception"] = str(exception)
	logger.info(payload)


def request(method, url, **kwargs):
	request_body = _request_body_from_kwargs(kwargs)
	try:
		response = _requests.request(method=method, url=url, **kwargs)
	except _requests.RequestException as exc:
		_log_api_request(method, url, request_body, exception=exc)
		raise
	_log_api_request(method, url, request_body, response_status=response.status_code)
	return response


def get(url, **kwargs):
	return request("GET", url, **kwargs)


def post(url, **kwargs):
	return request("POST", url, **kwargs)


def put(url, **kwargs):
	return request("PUT", url, **kwargs)


def patch(url, **kwargs):
	return request("PATCH", url, **kwargs)


def delete(url, **kwargs):
	return request("DELETE", url, **kwargs)


def __getattr__(name):
	return getattr(_requests, name)
