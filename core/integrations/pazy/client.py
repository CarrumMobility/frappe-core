"""Pazy Invoice Creation API (https://docs.pazy.io/apis/invoice-creation).

POST {base_url}/invoice, multipart/form-data: file (PDF, max 50 MB), remarks.
Auth: Authorization: Api-Key <site_config.pazy_api_key>.
Success: 200 {"ok": true, "data": {"id", "status", "processingId", "isReady"}}.

The API has no idempotency key and no external reference field, so callers
must guarantee one upload per bill; our reference travels in `remarks`.
Every call is logged to Api hit log (without the file bytes or the API key).
"""

from __future__ import annotations

import time

import frappe
import requests

from core.services.apihit_service import api_hit_service, created_by_user, response_body_for_log

PAZY_DEFAULT_BASE_URL = "https://api.pazy.io/v1.0"
PAZY_DEFAULT_TIMEOUT_SECONDS = 60
PAZY_MAX_INVOICE_FILE_BYTES = 50 * 1024 * 1024

_API_NAME = "Pazy:create_invoice"


class PazyApiError(Exception):
	def __init__(
		self,
		message: str,
		*,
		status_code: int | None = None,
		code: str | None = None,
		response_body=None,
	):
		super().__init__(message)
		self.status_code = status_code
		self.code = code
		self.response_body = response_body


def get_pazy_api_key() -> str:
	return (frappe.conf.get("pazy_api_key") or "").strip()


def _error_from_response(response, body) -> PazyApiError:
	"""Map a non-success response to PazyApiError, keeping Pazy's error code when present."""
	code = message = None
	if isinstance(body, dict):
		error = body.get("error")
		if isinstance(error, dict):
			code = error.get("code")
			message = error.get("message")
		else:
			code = body.get("code") or (error if isinstance(error, str) else None)
			message = body.get("message")
	if response.status_code == 413:
		code = code or "PAYLOAD_TOO_LARGE"
	detail = message or (str(body)[:300] if body else response.reason)
	return PazyApiError(
		f"Pazy invoice upload failed: HTTP {response.status_code} {code or ''} {detail}".strip(),
		status_code=response.status_code,
		code=code,
		response_body=body,
	)


class PazyClient:
	"""Thin HTTP wrapper for the Pazy Invoice Creation API."""

	def __init__(
		self,
		api_key: str | None = None,
		*,
		base_url: str | None = None,
		timeout_seconds: int | None = None,
	):
		self.api_key = (api_key if api_key is not None else get_pazy_api_key()) or ""
		self.base_url = (base_url or PAZY_DEFAULT_BASE_URL).rstrip("/")
		self.timeout_seconds = timeout_seconds or PAZY_DEFAULT_TIMEOUT_SECONDS

	def create_invoice(
		self, pdf_bytes: bytes, filename: str, remarks: str, *, user: str | None = None
	) -> dict:
		"""Upload one invoice PDF. Returns Pazy's `data` dict (has `id`); raises PazyApiError."""
		if not self.api_key:
			raise PazyApiError("pazy_api_key is not set in site config")
		if len(pdf_bytes) > PAZY_MAX_INVOICE_FILE_BYTES:
			raise PazyApiError(
				f"PDF is {len(pdf_bytes)} bytes; Pazy accepts at most {PAZY_MAX_INVOICE_FILE_BYTES}"
			)

		url = f"{self.base_url}/invoice"
		log_payload = {"file": filename, "file_size": len(pdf_bytes), "remarks": remarks}
		response = None
		error_message = None
		started = time.monotonic()
		try:
			response = requests.post(
				url,
				headers={"Authorization": f"Api-Key {self.api_key}"},
				files={"file": (filename, pdf_bytes, "application/pdf")},
				data={"remarks": remarks},
				timeout=self.timeout_seconds,
			)
		except requests.Timeout as e:
			error_message = f"Pazy invoice upload timed out after {self.timeout_seconds}s: {e}"
			raise PazyApiError(error_message, code="TIMEOUT") from e
		except requests.RequestException as e:
			error_message = f"Pazy invoice upload request failed: {e}"
			raise PazyApiError(error_message, code="REQUEST_FAILED") from e
		finally:
			api_hit_service.log_api_request(
				_API_NAME,
				url,
				log_payload,
				response_body_for_log(response),
				response.status_code if response is not None else 0,
				time.monotonic() - started,
				error_message=error_message,
				created_by=created_by_user(user),
			)

		body = response_body_for_log(response)
		if response.status_code != 200:
			raise _error_from_response(response, body)

		data = body.get("data") if isinstance(body, dict) else None
		if not (isinstance(body, dict) and body.get("ok") and isinstance(data, dict) and data.get("id")):
			raise PazyApiError(
				f"Pazy invoice upload returned 200 without ok/data.id: {str(body)[:300]}",
				status_code=200,
				code="UNEXPECTED_RESPONSE",
				response_body=body,
			)
		return data
